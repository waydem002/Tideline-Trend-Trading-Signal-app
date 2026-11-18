"""Live scanner. Run it once per closed 4h candle. It sends Telegram alerts and follows
every signal to its real outcome, using the same engine as the backtest."""
import json
import os
import time
from datetime import datetime, timedelta, timezone
import pandas as pd
import requests
from . import config as C
from .data import load
from .engine import P, Pos, build_orders, fill_price, prepare
from .report import render
from .research import VARIANTS
from .status import levels

STATE = C.OUT_DIR / "state.json"
# Which system runs live. "daily" = the 100-day breakout trend system (the one that held up best in testing).
SYSTEMS = {"daily": ("1d", 24, VARIANTS[3][2]), "classic4h": ("4h", 4, P())}
TF, TFH, p = SYSTEMS[os.environ.get("TIDELINE_SYSTEM", "daily")]


def fmt(x):
    return f"{x:,.2f}" if x >= 100 else f"{x:,.4f}" if x >= 1 else f"{x:,.6f}"


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return dict(last={}, orders=[], positions=[], closed=[])


def save_state(st):
    C.OUT_DIR.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st))
    os.replace(tmp, STATE)  # atomic write: a crash can never leave a half-written file


def send(text):
    print(text + "\n")
    if not (C.TELEGRAM_BOT_TOKEN and C.TELEGRAM_CHAT_ID):
        print("[Telegram is NOT set up: put TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the file named .env]\n")
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{C.TELEGRAM_BOT_TOKEN}/sendMessage",
                          data=dict(chat_id=C.TELEGRAM_CHAT_ID, text=text), timeout=15)
        if r.status_code == 200:
            print("[sent to Telegram]\n")
            return True
        print(f"[Telegram refused the message, code {r.status_code}. 401 = wrong bot token, 400 = wrong chat id, "
              "403 = you have not pressed Start in your bot's chat]\n")
    except Exception as e:  # never print the exception text: it contains the bot token URL
        print("[Telegram message failed:", e.__class__.__name__ + "]\n")
    return False


def sizing(entry, stop):
    dist = abs(entry - stop)
    risk_amt = C.ACCOUNT_BALANCE * C.RISK_PER_TRADE
    qty = risk_amt / dist
    note = ""
    if qty * entry > C.ACCOUNT_BALANCE:
        qty, note = C.ACCOUNT_BALANCE / entry, " (capped to your balance, so you risk less than planned)"
    return qty, qty * entry, risk_amt, note


def signal_text(sym, od):
    if p.mode == "donchian":
        qty, usd, risk_amt, note = sizing(od["ref"], od["stop"])
        word = "BUY" if od["side"] == 1 else "SELL"
        return (f"Tideline signal: {word} {sym} ({p.don_n}-candle breakout)\n"
                f"{word.title()} at market now (about {fmt(od['ref'])}, the last close). Skip it if the price has already run more than 1 ATR ({fmt(od['atr'])}) beyond that.\n"
                f"Stop-loss: {fmt(od['stop'])}\n"
                f"There is no fixed take-profit. The stop trails behind the price, and I will message you each time to raise it. You exit when the stop is hit.\n"
                f"Risk {C.RISK_PER_TRADE*100:g}% = ${risk_amt:,.2f}. Size about {qty:.6g} {sym[:-4]} (${usd:,.0f}){note}")
    word = "BUY" if od["side"] == 1 else "SELL"
    s = od["side"]
    risk = abs(od["ref"] - od["stop"])
    tp1, tp2 = od["ref"] + s * p.tp1_r * risk, od["ref"] + s * p.tp2_r * risk
    qty, usd, risk_amt, note = sizing(od["ref"], od["stop"])
    how = (f"Place a {word.lower()}-stop at {fmt(od['trigger'])}" if od["kind"] == "pullback"
           else f"{word.title()} at market now (breakout confirmed, about {fmt(od['ref'])})")
    return (f"Tideline signal: {word} {sym} ({od['kind']})\n{how}\n"
            f"Stop-loss: {fmt(od['stop'])}\nTP1 {fmt(tp1)}: sell {int(p.w1*100)}%, move stop to entry\n"
            f"TP2 {fmt(tp2)}: sell {int(p.w2*100)}%\nRest: trail the stop {p.trail_atr:g} ATR behind the best price\n"
            f"Risk {C.RISK_PER_TRADE*100:g}% = ${risk_amt:,.2f}. Size about {qty:.6g} {sym[:-4]} (${usd:,.0f}){note}\n"
            f"Cancel the order if it has not filled by {od['expires_t'][:16]} UTC.")


def cool(st, sym, t, reason):
    """Same rule as the backtest: no new signal on the exit candle, and 2 more candles after a stop-out."""
    extra = pd.Timedelta(hours=2 * TFH) if reason == "stop" else pd.Timedelta(0)
    st.setdefault("cool", {})[sym] = str(pd.Timestamp(t) + extra)


def process(sym, st):
    d = prepare(load(sym, TF))
    n, idx = len(d), d.index
    last = st["last"].get(sym)
    start = n - 1 if last is None else int(idx.searchsorted(pd.Timestamp(last), side="right"))
    sig = {o["i"]: o for o in build_orders(d, p)}
    for k in range(start, n):
        r, t = d.iloc[k], str(idx[k])
        o_, h_, l_, c_, e50, a_ = r.open, r.high, r.low, r.close, r.ema50, r.atr
        prec = next((x for x in st["positions"] if x["symbol"] == sym), None)
        orec = next((x for x in st["orders"] if x["symbol"] == sym), None)
        if prec:
            pos = Pos.from_dict(prec["pos"])
            old_stop = pos.stop
            ev = pos.step(p, o_, h_, l_, c_, e50, a_)
            if not pos.closed and pos.side * (pos.stop - old_stop) > 1e-12:
                send(f"Tideline: raise your stop-loss on {sym} to {fmt(pos.stop)}. Never lower it.")
            prec["pos"] = pos.to_dict()
            for e in ev:
                if e in ("TP1", "TP2"):
                    send(f"Tideline: {sym} hit {e}. " + ("Stop is now at entry." if e == "TP1" else "Runner stays open."))
            if pos.closed:
                st["positions"].remove(prec)
                st["closed"].append(dict(symbol=sym, kind=prec["kind"], opened=prec["opened"], closed=t,
                                         r=round(pos.net_r(), 3), outcome=pos.reason, tp1=pos.t1, tp2=pos.t2))
                cool(st, sym, t, pos.reason)
                send(f"Tideline: {sym} closed ({pos.reason}). Result {pos.net_r():+.2f}R after costs.")
        elif orec and k > 0:
            od = orec["od"]
            if t > od["expires_t"]:
                st["orders"].remove(orec)
                st["closed"].append(dict(symbol=sym, kind=od["kind"], opened=od["time"], closed=t, r=0, outcome="not filled", tp1=False, tp2=False))
                send(f"Tideline: {sym} entry order expired without filling. Nothing to do.")
            else:
                f = fill_price(od, o_, h_, l_, p)
                if f is False:
                    st["orders"].remove(orec)
                    st["closed"].append(dict(symbol=sym, kind=od["kind"], opened=od["time"], closed=t, r=0, outcome="cancelled", tp1=False, tp2=False))
                    send(f"Tideline: {sym} order cancelled. Price jumped past the stop level.")
                elif f is not None:
                    s = od["side"]
                    pos = Pos(s, f * (1 + s * C.SLIPPAGE), od["stop"])
                    st["orders"].remove(orec)
                    send(f"Tideline: {sym} entered near {fmt(pos.entry)}. Stop {fmt(pos.stop)}.")
                    ev = pos.step(p, o_, h_, l_, c_, e50, a_)
                    if pos.closed:
                        st["closed"].append(dict(symbol=sym, kind=od["kind"], opened=t, closed=t, r=round(pos.net_r(), 3), outcome=pos.reason, tp1=pos.t1, tp2=pos.t2))
                        cool(st, sym, t, pos.reason)
                        send(f"Tideline: {sym} closed ({pos.reason}). Result {pos.net_r():+.2f}R after costs.")
                    else:
                        st["positions"].append(dict(symbol=sym, kind=od["kind"], opened=t, pos=pos.to_dict()))
        busy = any(x["symbol"] == sym for x in st["positions"] + st["orders"])
        if k == n - 1 and k in sig and not busy and t > st.get("cool", {}).get(sym, "") and len(st["positions"]) + len(st["orders"]) < p.max_open:
            od = dict(sig[k])
            od["expires_t"] = str(idx[k] + pd.Timedelta(hours=TFH * (od["expires"] - k)))
            st["orders"].append(dict(symbol=sym, od=od))
            send(signal_text(sym, od))
    st["last"][sym] = str(idx[-1])
    return levels(d, p) if p.mode == "donchian" else None


def digest_text(rows, st):
    """One short daily message: what is open, and how close the market is to a signal."""
    held = ", ".join(x["symbol"][:-4] for x in st["positions"]) or "none"
    text = f"Tideline daily check done. Open trades: {held}. Waiting entries: {len(st['orders'])}."
    if rows:
        best = min(rows, key=lambda r: max(r["need"], r["ema_gap"]))
        away = max(best["need"], best["ema_gap"]) * 100
        above = sum(1 for r in rows if r["trend"])
        text += (f"\nClosest to a signal: {best['sym'][:-4]}, about {away:+.1f}% away. "
                 f"Coins above their 200-day average: {above} of {len(rows)}.")
    return text


def cycle():
    st = load_state()
    rows = []
    for sym in C.SYMBOLS:
        try:
            lv = process(sym, st)
            if lv:
                rows.append(dict(lv, sym=sym))
        except Exception as e:
            print(f"{sym}: skipped this round ({e.__class__.__name__}: {str(e)[:120]})")
    save_state(st)
    render()
    if TFH == 24:  # one short daily message so you know the check ran
        send(digest_text(rows, st))
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC  waiting orders {len(st['orders'])}, open {len(st['positions'])}, finished {len(st['closed'])}")


def loop():
    send(f"{C.APP_NAME} scanner started. Watching {', '.join(s[:-4] for s in C.SYMBOLS)} on {TF} candles.")
    while True:
        cycle()
        now = datetime.now(timezone.utc)
        nxt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=TFH - now.hour % TFH, seconds=45)
        time.sleep(max(30, (nxt - now).total_seconds()))

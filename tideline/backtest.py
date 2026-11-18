"""Backtest: replay history candle by candle with fees, slippage and portfolio limits."""
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from . import config as C
from .engine import P, Pos, build_orders, fill_price, prepare


def run_symbol(sym, d, p):
    O, H, L, Cl = d.open.values, d.high.values, d.low.values, d.close.values
    E50, A, n, idx = d.ema50.values, d.atr.values, len(d), d.index
    trades, busy = [], -1
    for od in build_orders(d, p):
        if od["i"] <= busy or od["i"] >= n - 1:
            continue  # one position per symbol at a time
        j = px = None
        for k in range(od["i"] + 1, min(od["expires"], n - 1) + 1):
            f = fill_price(od, O[k], H[k], L[k], p)
            if f is False:
                break
            if f is not None:
                j, px = k, f
                break
        if j is None:
            continue
        s = od["side"]
        pos = Pos(s, px * (1 + s * C.SLIPPAGE), od["stop"])
        k = j
        while True:
            pos.step(p, O[k], H[k], L[k], Cl[k], E50[k], A[k])
            if pos.closed or k == n - 1:
                break
            k += 1
        if not pos.closed:
            break  # still open at the end of data: leave it out, and take no later signals on this coin
        trades.append(dict(symbol=sym, entry_time=idx[j], exit_time=idx[k], side=s, kind=od["kind"],
                           r=pos.net_r(p.funding_per_bar), reason=pos.reason, bars=pos.bars, tp1=pos.t1, tp2=pos.t2))
        busy = k + (2 if pos.reason == "stop" else 0)  # 2-candle cooldown after a stop-out
    return trades


def portfolio(tr, max_open=None):
    """Apply the max-open-trades limit across all symbols."""
    max_open = max_open or C.MAX_OPEN
    tr = tr.sort_values("entry_time").reset_index(drop=True)
    keep, ex = [], []
    for r in tr.itertuples():
        ex = [e for e in ex if e > r.entry_time]
        if len(ex) < max_open:
            keep.append(r.Index)
            ex.append(r.exit_time)
    return tr.loc[keep].reset_index(drop=True)


def equity_curve(tr):
    t = tr.sort_values("exit_time")
    risk = t["risk"].values if "risk" in t.columns else C.RISK_PER_TRADE
    eq = C.START_EQUITY * np.cumprod(1 + risk * t.r.values)
    return pd.Series(eq, index=t.exit_time.values)


def metrics(tr):
    if len(tr) == 0:
        return dict(n=0, win=0, avg_r=0, pf=0, ret=0, mdd=0, streak=0, tp1=0)
    eq = equity_curve(tr)
    wins, loss = tr.r[tr.r > 0].sum(), -tr.r[tr.r < 0].sum()
    streak = cur = 0
    for x in tr.sort_values("exit_time").r:
        cur = cur + 1 if x <= 0 else 0
        streak = max(streak, cur)
    return dict(n=int(len(tr)), win=float((tr.r > 0).mean()), avg_r=float(tr.r.mean()),
                pf=float(wins / loss) if loss > 0 else 99.0, ret=float(eq.iloc[-1] / C.START_EQUITY - 1),
                mdd=float((eq / eq.cummax() - 1).min()), streak=int(streak), tp1=float(tr.tp1.mean()))


def run_all(prepared, p):
    rows = []
    for sym, d in prepared.items():
        rows += run_symbol(sym, d, p)
    if not rows:
        return pd.DataFrame(columns=["symbol", "entry_time", "exit_time", "r", "tp1"])
    return portfolio(pd.DataFrame(rows), p.max_open)


def full_report(prepared, p=None):
    p = p or P()
    tr = run_all(prepared, p)
    m = metrics(tr)
    out = dict(metrics=m, params=p.__dict__, symbols=list(prepared),
               generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               costs=dict(fee=C.FEE, slippage=C.SLIPPAGE, risk=C.RISK_PER_TRADE, max_open=C.MAX_OPEN),
               start=str(min(d.index[0] for d in prepared.values()).date()),
               end=str(max(d.index[-1] for d in prepared.values()).date()))
    if m["n"] == 0:
        out.update(equity=[], yearly=[], by_symbol=[], grid=[], split={}, checks=[], verdict="fail")
        return out, tr
    eq = equity_curve(tr)
    step = max(1, len(eq) // 400)
    out["equity"] = [[str(t)[:10], round(float(v), 2)] for t, v in list(eq.items())[::step]] + \
                    [[str(eq.index[-1])[:10], round(float(eq.iloc[-1]), 2)]]
    tr["year"] = pd.to_datetime(tr.exit_time).dt.year
    out["yearly"] = [dict(year=int(y), n=int(len(g)), avg_r=float(g.r.mean()),
                          ret=float((1 + C.RISK_PER_TRADE * g.r).prod() - 1)) for y, g in tr.groupby("year")]
    out["by_symbol"] = [dict(symbol=s, n=int(len(g)), avg_r=float(g.r.mean()), win=float((g.r > 0).mean()))
                        for s, g in tr.groupby("symbol")]
    cut = tr.entry_time.quantile(0.6)
    out["split"] = dict(early=metrics(tr[tr.entry_time <= cut]), recent=metrics(tr[tr.entry_time > cut]))
    # Robustness: nudge two key settings and see if the edge survives.
    grid = []
    for adx_min in (16, 20, 24):
        for stop_atr in (1.6, 2.0, 2.4):
            q = P(**{**p.__dict__, "adx_min": adx_min, "stop_atr": stop_atr})
            g = metrics(run_all(prepared, q))
            grid.append(dict(adx=adx_min, stop=stop_atr, n=g["n"], avg_r=g["avg_r"], pf=g["pf"]))
    out["grid"] = grid
    share = sum(1 for g in grid if g["avg_r"] > 0) / len(grid)
    checks = [
        ("At least 200 trades, so luck matters less", m["n"] >= 200),
        ("Profit factor above 1.3 after fees and slippage", m["pf"] > 1.3),
        ("Average trade above +0.15R", m["avg_r"] > 0.15),
        ("Still profitable in the most recent 40% of the test", out["split"]["recent"]["avg_r"] > 0),
        ("Profitable in at least 7 of 9 nearby settings", share >= 7 / 9),
        ("Worst drawdown smaller than 25%", m["mdd"] > -0.25),
    ]
    out["checks"] = [dict(label=a, ok=bool(b)) for a, b in checks]
    met = sum(b for _, b in checks)
    out["verdict"] = "pass" if met == len(checks) else "close" if met >= 4 else "fail"
    return out, tr


def save(out, tr):
    C.OUT_DIR.mkdir(exist_ok=True)
    (C.OUT_DIR / "backtest.json").write_text(json.dumps(out))
    tr.to_csv(C.OUT_DIR / "backtest_trades.csv", index=False)

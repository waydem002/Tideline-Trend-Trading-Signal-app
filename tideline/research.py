"""Rule search with honest bookkeeping.

How this avoids fooling you:
  1. The list of rule sets below was written BEFORE looking at 2024+ results, using what the first backtest showed.
  2. A winner is chosen using only the learning period (before 2024).
  3. The winner is then judged once on the untouched period (2024 onward).
  4. The number of combinations tried is shown, because the more you try, the likelier one wins by luck.
"""
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from . import config as C
from .backtest import equity_curve, metrics, run_all
from .data import load
from .engine import P, prepare

WIDE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "LINKUSDT", "LTCUSDT", "AVAXUSDT"]
CORE = C.SYMBOLS
CUT = pd.Timestamp("2024-01-01", tz="UTC")   # learning period ends here


def _trend(**kw):
    base = dict(mode="donchian", stop_atr=3.0, stop_max=4.0, trail_atr=3.0, trail_from_start=True,
                tp1_r=99.0, tp2_r=99.0, w1=0.0, w2=0.0, trend_exit=False, stale_bars=10**6,
                max_open=5, adx_min=0.0)
    base.update(kw)
    return P(**base)


# Each entry: (name, timeframe, rules). Reasons come from the first backtest: only trailing exits made money,
# so these ride trends with no partial targets, on slower candles where fees matter less.
VARIANTS = [
    ("Baseline: 4h pullback and breakout", "4h", P()),
    ("Daily 55-day breakout, trail 3 ATR", "1d", _trend(don_n=55)),
    ("Daily 20-day breakout, trail 3 ATR", "1d", _trend(don_n=20)),
    ("Daily 100-day breakout, trail 4 ATR", "1d", _trend(don_n=100, trail_atr=4.0)),
    ("Daily 55-day breakout, trend strength 20+", "1d", _trend(don_n=55, adx_min=20.0)),
    ("4h 20-day breakout, trail 4 ATR", "4h", _trend(don_n=120, trail_atr=4.0)),
]


def summarize(tr):
    m = metrics(tr)
    return {k: (round(float(v), 4) if isinstance(v, float) else v) for k, v in m.items()}


def bootstrap_interval(r, n=5000, seed=7):
    if len(r) < 5:
        return None
    rng = np.random.default_rng(seed)
    means = rng.choice(np.asarray(r), size=(n, len(r))).mean(axis=1)
    return [round(float(np.percentile(means, 5)), 3), round(float(np.percentile(means, 95)), 3)]


def judge(sel, hold):
    o, i = sel["oos"], sel["learn"]
    lo, hi = sel.get("oos_interval") or [None, None]
    if o["n"] < 20:
        v, head = "close", "Too few trades in the untouched period to judge."
    elif o["avg_r"] > 0.1 and o["pf"] > 1.3 and lo is not None and lo > 0:
        v, head = "pass", "The chosen rules also worked on data they never saw. Paper trade next."
    elif o["avg_r"] > 0:
        v, head = "close", "Positive on unseen data, but not strong enough to be sure it isn't luck."
    else:
        v, head = "fail", "The chosen rules failed on unseen data. Do not trade them."
    detail = (f"Chosen on {i['n']} learning-period trades (average {i['avg_r']:+.2f}R, profit factor {i['pf']:.2f}). "
              f"On the untouched period: {o['n']} trades, average {o['avg_r']:+.2f}R, profit factor {o['pf']:.2f}"
              + (f", likely range {lo:+.2f}R to {hi:+.2f}R per trade." if lo is not None else "."))
    if hold:
        detail += (f" For comparison, simply holding BTC over the same stretch changed by {hold['ret']*100:+.0f}% "
                   f"with a worst fall of {hold['mdd']*100:.0f}%.")
    return v, head, detail


def fetch(refresh=True):
    prepared = {"4h": {}, "1d": {}}
    for tf in ("4h", "1d"):
        for s in WIDE:
            print(f"Downloading {s} {tf} ...")
            try:
                prepared[tf][s] = prepare(load(s, tf, refresh=refresh))
            except Exception as e:
                print(f"  skipped {s} {tf}: {e.__class__.__name__}")
    return prepared


def run(refresh=True):
    return analyse(fetch(refresh))


def analyse(prepared):
    results, trials = [], 0
    for name, tf, p in VARIANTS:
        for uni_name, uni in (("5 coins", CORE), ("10 coins", WIDE)):
            data = {s: prepared[tf][s] for s in uni if s in prepared[tf]}
            if not data:
                continue
            trials += 1
            tr = run_all(data, p)
            tr_l = tr[tr.entry_time < CUT] if len(tr) else tr
            tr_o = tr[tr.entry_time >= CUT] if len(tr) else tr
            results.append(dict(name=name, universe=uni_name, tf=tf, learn=summarize(tr_l), oos=summarize(tr_o),
                                all=summarize(tr), trades=tr, rules=p))
            print(f"  {name} / {uni_name}: learning {results[-1]['learn']['n']} trades "
                  f"avg {results[-1]['learn']['avg_r']:+.2f}R, untouched {results[-1]['oos']['n']} trades "
                  f"avg {results[-1]['oos']['avg_r']:+.2f}R")
    eligible = [r for r in results if r["learn"]["n"] >= 40]
    sel = max(eligible, key=lambda r: r["learn"]["pf"]) if eligible else None
    out = dict(trials=trials, cut=str(CUT.date()), generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               table=[{k: r[k] for k in ("name", "universe", "tf", "learn", "oos", "all")} | dict(chosen=r is sel)
                      for r in sorted(results, key=lambda r: -r["learn"]["pf"])])
    if sel is None:
        out.update(verdict="fail", headline="No rule set produced enough trades in the learning period to judge.",
                   detail="Try again with a longer history or looser rules.", equity=[], hold=None)
        return out
    tro = sel["trades"][sel["trades"].entry_time >= CUT]
    sel["oos_interval"] = bootstrap_interval(tro.r.values) if len(tro) else None
    btc = prepared["1d"].get("BTCUSDT")
    hold = None
    if btc is not None and len(tro):
        c = btc.close[btc.index >= tro.entry_time.min().normalize()]
        if len(c) > 2:
            hold = dict(ret=float(c.iloc[-1] / c.iloc[0] - 1), mdd=float((c / c.cummax() - 1).min()))
    v, head, detail = judge(sel, hold)
    eq = equity_curve(sel["trades"])
    step = max(1, len(eq) // 300)
    out.update(verdict=v, headline=head, detail=detail, hold=hold, interval=sel["oos_interval"],
               chosen=dict(name=sel["name"], universe=sel["universe"], tf=sel["tf"]),
               equity=[[str(t)[:10], round(float(x), 2)] for t, x in list(eq.items())[::step]])
    sel["trades"].to_csv(C.OUT_DIR / "research_chosen_trades.csv", index=False)
    return out


def save(out):
    C.OUT_DIR.mkdir(exist_ok=True)
    (C.OUT_DIR / "research.json").write_text(json.dumps(out))

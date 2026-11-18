"""Swing and rotation research, long AND short, with futures costs.

Two families, both declared before looking at results, both judged the same fair way as everything else:
choose using only the learning period (before 2024), then judge once on the untouched period.
  1. Trade systems: the trend rules run long and short, paying funding while a position is open.
  2. Weekly rotation: each week hold the strongest coins, optionally short the weakest.
Warnings that apply to rotation: the coin list is made of coins that are big today (survivors), which flatters
'long the strongest'. Coins that collapsed are missing, which understates what shorting the weakest would have made.
Weights are held constant between weekly rebalances, a simplification."""
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from . import config as C
from .backtest import run_all
from .engine import P
from .research import CUT, WIDE, _trend, fetch, summarize

FUND_4H = 0.00005    # 0.01% funding per 8 hours is 0.005% per 4h candle; charged on both sides (pessimistic for shorts)
FUND_1D = 0.0003
TRADE_SYSTEMS = [
    ("4h pullback and breakout, long and short", "4h", P(shorts=True, funding_per_bar=FUND_4H)),
    ("Daily 100-day breakout, long and short", "1d", _trend(don_n=100, trail_atr=4.0, shorts=True, funding_per_bar=FUND_1D)),
    ("Daily 55-day breakout, long and short", "1d", _trend(don_n=55, shorts=True, funding_per_bar=FUND_1D)),
    ("4h 20-day breakout, long and short", "4h", _trend(don_n=120, trail_atr=4.0, shorts=True, funding_per_bar=FUND_4H)),
]
ROTATIONS = [
    ("Weekly: long the 2 strongest of 30 days (spot)", 30, 2, False),
    ("Weekly: long the 2 strongest of 90 days (spot)", 90, 2, False),
    ("Weekly: long 2 strongest, short 2 weakest, 30 days (futures)", 30, 2, True),
    ("Weekly: long 2 strongest, short 2 weakest, 90 days (futures)", 90, 2, True),
]


def rotate(closes, lookback, k, short, rebalance=7, cost=0.0015, funding=FUND_1D):
    """Daily profit series (fraction of the account, gross exposure 100%). Weights chosen at day i's close use only data up to i."""
    ret = closes.pct_change().fillna(0.0)
    mom = closes.pct_change(lookback)
    n, cols = len(closes), list(closes.columns)
    cur, pnl, start = np.zeros(len(cols)), np.zeros(n), lookback + 1
    for i in range(start, n - 1):
        cost_today = 0.0
        if (i - start) % rebalance == 0:
            m = mom.iloc[i].dropna()
            new = np.zeros(len(cols))
            if len(m) >= 2 * k:
                for c in m.nlargest(k).index:
                    new[cols.index(c)] = (0.5 if short else 1.0) / k
                if short:
                    for c in m.nsmallest(k).index:
                        new[cols.index(c)] = -0.5 / k
            cost_today = float(np.abs(new - cur).sum()) * cost
            cur = new
        fund = funding * float(np.abs(cur).sum()) if short else 0.0
        pnl[i + 1] = float((cur * ret.iloc[i + 1].values).sum()) - cost_today - fund
    return pd.Series(pnl, index=closes.index), start


def curve(p):
    if len(p) < 30:
        return dict(ann=0.0, mdd=0.0, calmar=0.0, ret=0.0)
    eq = (1 + p).cumprod()
    ret = float(eq.iloc[-1] - 1)
    mdd = float((eq / eq.cummax() - 1).min())
    ann = float((1 + ret) ** (365.0 / len(p)) - 1) if ret > -1 else -1.0
    return dict(ann=round(ann, 4), mdd=round(mdd, 4), calmar=round(ann / abs(mdd), 2) if mdd < 0 else 0.0, ret=round(ret, 4))


def side_stats(tr):
    out = {}
    for name, s in (("long", 1), ("short", -1)):
        g = tr[tr.side == s] if len(tr) else tr
        out[name] = dict(n=int(len(g)), avg_r=round(float(g.r.mean()), 3) if len(g) else 0.0)
    return out


def analyse(prepared):
    trials = 0
    # ---- trade systems ----
    trows = []
    for name, tf, p in TRADE_SYSTEMS:
        data = {s: prepared[tf][s] for s in WIDE if s in prepared[tf]}
        tr = run_all(data, p)
        trials += 1
        parts = {}
        for key, sub in (("learn", tr[tr.entry_time < CUT] if len(tr) else tr), ("oos", tr[tr.entry_time >= CUT] if len(tr) else tr)):
            parts[key] = dict(summarize(sub), **side_stats(sub))
        trows.append(dict(name=name, **parts))
    elig = [r for r in trows if r["learn"]["n"] >= 40]
    tsel = max(elig, key=lambda r: r["learn"]["pf"]) if elig else None
    for r in trows:
        r["chosen"] = r is tsel
    if tsel is None:
        tv, th, td = "fail", "No long-and-short trade system had enough trades to judge.", ""
    else:
        o, sh = tsel["oos"], tsel["oos"]["short"]
        short_lost = sh["n"] >= 15 and sh["avg_r"] <= 0
        if o["n"] >= 20 and o["avg_r"] > 0.1 and o["pf"] > 1.3 and short_lost:
            tv, th = "close", "Positive overall, but the short trades lost money, so the long trades did all the work. Shorting added nothing."
        elif o["n"] >= 20 and o["avg_r"] > 0.1 and o["pf"] > 1.3:
            tv, th = "pass", "The chosen long-and-short trade system held up on the untouched period."
        elif o["avg_r"] > 0:
            tv, th = "close", "The chosen long-and-short trade system was positive on the untouched period, but not convincingly."
        else:
            tv, th = "fail", "The chosen long-and-short trade system failed on the untouched period."
        td = (f"{tsel['name']}: untouched period {o['n']} trades, average {o['avg_r']:+.2f}R, profit factor {o['pf']:.2f}. "
              f"Its short trades alone: {sh['n']} trades averaging {sh['avg_r']:+.2f}R.")
    # ---- rotation ----
    closes = pd.concat({s: prepared["1d"][s].close for s in WIDE if s in prepared["1d"]}, axis=1).sort_index()
    rrows = []
    for name, lb, k, short in ROTATIONS:
        trials += 1
        pnl, st = rotate(closes, lb, k, short)
        pnl = pnl.iloc[st:]
        rrows.append(dict(name=name, learn=curve(pnl[pnl.index < CUT]), oos=curve(pnl[pnl.index >= CUT])))
    relig = [r for r in rrows if r["learn"]["ann"] > 0]
    rsel = max(relig, key=lambda r: r["learn"]["calmar"]) if relig else None
    for r in rrows:
        r["chosen"] = r is rsel
    first = max(l for _, l, _, _ in ROTATIONS) + 1
    btc = closes["BTCUSDT"].pct_change().fillna(0.0).iloc[first:]
    hold = dict(learn=curve(btc[btc.index < CUT]), oos=curve(btc[btc.index >= CUT]))
    if rsel is None:
        rv, rh, rd = "fail", "No rotation variant made money in the learning period.", ""
    else:
        o = rsel["oos"]
        if o["ann"] > 0 and o["calmar"] >= 1.0:
            rv, rh = "pass", "The chosen rotation held up on the untouched period."
        elif o["ann"] > 0:
            rv, rh = "close", "The chosen rotation made money on the untouched period, but with a poor gain for the fall."
        else:
            rv, rh = "fail", "The chosen rotation lost money on the untouched period."
        rd = (f"{rsel['name']}: untouched period about {o['ann']*100:+.0f}% a year with a worst fall of {o['mdd']*100:.0f}%. "
              f"Holding BTC over the same stretch: {hold['oos']['ann']*100:+.0f}% a year with a worst fall of {hold['oos']['mdd']*100:.0f}%.")
    return dict(trials=trials, cut=str(CUT.date()), generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                trade_verdict=tv, trade_headline=th, trade_detail=td, trade_table=trows,
                rot_verdict=rv, rot_headline=rh, rot_detail=rd, rot_table=rrows, hold=hold)


def run(refresh=True):
    return analyse(fetch(refresh))


def save(out):
    C.OUT_DIR.mkdir(exist_ok=True)
    (C.OUT_DIR / "swing.json").write_text(json.dumps(out))

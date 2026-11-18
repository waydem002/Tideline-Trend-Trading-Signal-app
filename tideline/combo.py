"""Do two trend speeds together beat either one alone?

Declared before looking at results: every portfolio shares the SAME total risk cap (2.5% of the account
open at once), so a combination cannot look better just by risking more. Judged on gain divided by worst
fall, in the learning period and in the untouched period separately."""
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from . import config as C
from .backtest import metrics, run_symbol
from .research import CORE, CUT, VARIANTS, WIDE, _trend, fetch

SLOW = ("Daily 100-day", "1d", VARIANTS[3][2])
FAST = ("4h 20-day", "4h", _trend(don_n=120, trail_atr=4.0))
HEAT = 0.025


def raw(prepared, p, risk):
    rows = []
    for s, d in prepared.items():
        rows += run_symbol(s, d, p)
    if not rows:
        return pd.DataFrame(columns=["symbol", "entry_time", "exit_time", "r", "risk", "tp1"])
    df = pd.DataFrame(rows)
    df["risk"] = risk
    return df


def heat_cap(tr, cap=HEAT):
    """Skip trades that would push total open risk above the cap."""
    tr = tr.sort_values("entry_time").reset_index(drop=True)
    keep, live = [], []
    for r in tr.itertuples():
        live = [(e, x) for e, x in live if e > r.entry_time]
        if sum(x for _, x in live) + r.risk <= cap + 1e-12:
            keep.append(r.Index)
            live.append((r.exit_time, r.risk))
    return tr.loc[keep].reset_index(drop=True)


def summ(tr):
    m = metrics(tr)
    ratio = m["ret"] / abs(m["mdd"]) if m["mdd"] < 0 else 0.0
    return dict(n=m["n"], ret=round(m["ret"], 4), mdd=round(m["mdd"], 4), ratio=round(ratio, 2),
                avg_r=round(m["avg_r"], 3), pf=round(m["pf"], 2), streak=m["streak"])


def monthly(tr):
    t = tr.copy()
    t["m"] = pd.to_datetime(t.exit_time).dt.tz_localize(None).dt.to_period("M")
    return (t.r * t.risk).groupby(t.m).sum()


def analyse(prepared):
    rows, corr = [], None
    for uni_name, uni in (("5 coins", CORE), ("10 coins", WIDE)):
        a = raw({s: prepared["1d"][s] for s in uni if s in prepared["1d"]}, SLOW[2], 0.005)
        b = raw({s: prepared["4h"][s] for s in uni if s in prepared["4h"]}, FAST[2], 0.005)
        half = lambda df: df.assign(risk=0.0025)
        ports = [
            (f"{SLOW[0]} alone, 0.5% per trade", heat_cap(a)),
            (f"{FAST[0]} alone, 0.5% per trade", heat_cap(b)),
            ("Both together, 0.25% per trade each", heat_cap(pd.concat([half(a), half(b)]))),
            ("Both together, 0.5% per trade each", heat_cap(pd.concat([a, b]))),
        ]
        for name, tr in ports:
            rows.append(dict(name=name, universe=uni_name, learn=summ(tr[tr.entry_time < CUT]), oos=summ(tr[tr.entry_time >= CUT])))
        if uni_name == "5 coins" and len(a) and len(b):
            m = pd.concat([monthly(a), monthly(b)], axis=1).fillna(0)
            corr = round(float(m.corr().iloc[0, 1]), 2)
    five = [r for r in rows if r["universe"] == "5 coins"]
    sa, sb, sc = five[0], five[1], five[2]
    better = {k: sc[k]["ratio"] > max(sa[k]["ratio"], sb[k]["ratio"]) for k in ("learn", "oos")}
    if all(better.values()):
        v, head = "pass", "Running both speeds together beat either one alone in both periods."
    elif any(better.values()):
        v, head = "close", "Running both speeds together helped in one period but not the other, so the benefit is unclear."
    else:
        v, head = "fail", "Running both speeds together did not beat the better single system. Keep it simple and use one."
    detail = (f"Month-to-month results of the two systems had a correlation of {corr}. " if corr is not None else "")
    detail += ("Closer to 0 means they behave differently and cover each other's weak spells; closer to 1 means little is gained. "
               f"On the untouched period, with 5 coins, the mix scored a gain-to-fall ratio of {sc['oos']['ratio']}, "
               f"against {sa['oos']['ratio']} for the daily system and {sb['oos']['ratio']} for the 4h system.")
    return dict(trials=len(rows), cut=str(CUT.date()), generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                verdict=v, headline=head, detail=detail, corr=corr, table=rows)


def run(refresh=True):
    return analyse(fetch(refresh))


def save(out):
    C.OUT_DIR.mkdir(exist_ok=True)
    (C.OUT_DIR / "combo.json").write_text(json.dumps(out))

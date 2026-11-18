"""Risk dial: what each risk-per-trade setting could have earned, and how bad bad luck could get.

Returns and drawdowns scale together. This turns the dial for you on the daily system's real trades, and
simulates 3 years forward by redrawing those trades at random 5,000 times. The simulation shrinks the winners
so the average matches the weaker recent edge (2024 onward) instead of the flattering full history."""
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from . import config as C
from .backtest import run_all
from .research import CORE, CUT, VARIANTS, fetch

LEVELS = [0.005, 0.01, 0.015, 0.02, 0.03]
SYSTEM = VARIANTS[3]   # the daily 100-day breakout


def path_stats(r, risk):
    if len(r) == 0:
        return dict(ret=0.0, mdd=0.0)
    eq = np.cumprod(1 + risk * np.asarray(r))
    peak = np.maximum.accumulate(np.r_[1.0, eq])[1:]
    return dict(ret=float(eq[-1] - 1), mdd=float((eq / peak - 1).min()))


def haircut(r, target):
    """Shrink the winners so the average matches `target`, leaving losing trades at their true size."""
    r = np.asarray(r, dtype=float)
    win, lose = r[r > 0], r[r <= 0]
    if len(win) == 0 or target >= r.mean():
        return r
    k = max((target * len(r) - lose.sum()) / win.sum(), 0.0)
    return np.where(r > 0, r * k, r)


def simulate(pool, n, risk, sims=5000, seed=11):
    rng = np.random.default_rng(seed)
    r = rng.choice(np.asarray(pool), size=(sims, n))
    eq = np.cumprod(1 + risk * r, axis=1)
    mdd = (eq / np.maximum.accumulate(eq, axis=1) - 1).min(axis=1)
    ret = eq[:, -1] - 1
    return dict(median=float(np.median(ret)), bad=float(np.percentile(ret, 5)), fall=float(np.percentile(mdd, 5)),
                lose=float((ret < 0).mean()))


def analyse(prepared):
    data = {s: prepared["1d"][s] for s in CORE if s in prepared["1d"]}
    tr = run_all(data, SYSTEM[2]).sort_values("exit_time")
    oos = tr[tr.entry_time >= CUT]
    years = max(0.5, (tr.exit_time.max() - tr.entry_time.min()).days / 365.25)
    n3 = max(5, int(round(3 * len(tr) / years)))
    pool = haircut(tr.r.values, oos.r.mean()) if len(oos) else tr.r.values  # same trades, weaker recent average
    rows = []
    for risk in LEVELS:
        rows.append(dict(risk=risk, full=path_stats(tr.r.values, risk), oos=path_stats(oos.r.values, risk),
                         sim={k: round(v, 4) for k, v in simulate(pool, n3, risk).items()}))
    return dict(generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), cut=str(CUT.date()),
                system=SYSTEM[0], trades=int(len(tr)), oos_trades=int(len(oos)), per_year=round(len(tr) / years, 1),
                avg_r=round(float(tr.r.mean()), 3), oos_avg_r=round(float(oos.r.mean()), 3) if len(oos) else None,
                horizon_trades=n3, rows=rows)


def run(refresh=True):
    return analyse(fetch(refresh))


def save(out):
    C.OUT_DIR.mkdir(exist_ok=True)
    (C.OUT_DIR / "risk.json").write_text(json.dumps(out))

"""Earlier-years test. The daily 100-day rules were chosen using data from 2019 onward. Anything before 2019
is therefore fresh evidence: the rules were never fitted to it. Data: Bitstamp's free public daily candles
(BTC/USD from 2012, ETH/USD from late 2017). Early years were a tiny, thin market, so read them as a warning
light, not as proof."""
import json
import time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests
from . import config as C
from .backtest import run_all
from .engine import prepare
from .research import VARIANTS, bootstrap_interval, summarize

CUT0 = pd.Timestamp("2019-01-01", tz="UTC")
SOURCES = {"BTCUSD": ("btcusd", "2012-01-01"), "ETHUSD": ("ethusd", "2017-08-01")}
CHOSEN = VARIANTS[3]
TESTED = [VARIANTS[3], VARIANTS[1], VARIANTS[2]]   # the chosen rules and its two nearest daily neighbours


def _get(url, params):
    r = requests.get(url, params=params, timeout=30, headers={"User-Agent": "tideline/1.0"})
    r.raise_for_status()
    return r.json()


def fetch(pair, refresh=True):
    slug, start = SOURCES[pair]
    C.DATA_DIR.mkdir(exist_ok=True)
    f = C.DATA_DIR / f"{pair}_bitstamp_1d.csv"
    old = None
    if f.exists():
        old = pd.read_csv(f, index_col=0)
        old.index = pd.to_datetime(old.index, utc=True)
    if refresh or old is None:
        now = int(time.time())
        t = int(old.index[-1].timestamp()) + 86400 if old is not None else int(pd.Timestamp(start, tz="UTC").timestamp())
        rows = []
        while t < now - 86400:
            try:
                data = _get(f"https://www.bitstamp.net/api/v2/ohlc/{slug}/", dict(step=86400, limit=1000, start=t))["data"]["ohlc"]
            except Exception as e:
                raise RuntimeError(f"Could not download {pair} from Bitstamp ({e.__class__.__name__}). Check your internet or VPN.")
            if not data:
                break
            rows += data
            nxt = int(data[-1]["timestamp"]) + 86400
            if nxt <= t:
                break   # no progress; otherwise keep paging until we reach today
            t = nxt
            time.sleep(0.2)
        rows = [r for r in rows if int(r["timestamp"]) + 86400 <= now]   # closed days only
        if rows:
            new = pd.DataFrame(rows)[["timestamp", "open", "high", "low", "close", "volume"]].astype(float)
            new.index = pd.to_datetime(new.pop("timestamp"), unit="s", utc=True)
            old = new if old is None else pd.concat([old, new])
            old = old[~old.index.duplicated(keep="last")].sort_index()
            old.to_csv(f)
    return old


def fill_gaps(df):
    """Early years have days with no trades. Fill them with flat candles so '100 days' means 100 days."""
    full = pd.date_range(df.index[0], df.index[-1], freq="D", tz="UTC")
    missing = len(full) - len(df)
    d = df.reindex(full)
    d["close"] = d.close.ffill()
    for c in ("open", "high", "low"):
        d[c] = d[c].fillna(d.close)
    d["volume"] = d.volume.fillna(0.0)
    return d, missing


def judge(ch, hold):
    n, a, pf, iv = ch["n"], ch["avg_r"], ch["pf"], ch.get("interval")
    lo = iv[0] if iv else None
    if n < 15:
        v, head = "close", "Too few trades before 2019 to judge."
    elif a > 0.1 and pf > 1.3 and lo is not None and lo > 0:
        v, head = "pass", "The same rules also worked on years they were never fitted to."
    elif a > 0:
        v, head = "close", "Positive on the earlier years, but not strongly enough to rule out luck."
    else:
        v, head = "fail", "The rules did not work on the earlier years. That is a warning sign for the live system."
    detail = f"Before 2019 on BTC and ETH: {n} trades, average {a:+.2f}R, profit factor {pf:.2f}"
    detail += f", likely range {iv[0]:+.2f}R to {iv[1]:+.2f}R per trade." if iv else "."
    if hold:
        detail += f" Holding BTC over the same stretch changed by {hold['ret']*100:+.0f}% with a worst fall of {hold['mdd']*100:.0f}%."
    return v, head, detail


def analyse(prepared, filled):
    rows = []
    for name, tf, p in TESTED:
        for label, coins in [("BTC and ETH", list(prepared))] + [(c.replace("USD", ""), [c]) for c in prepared]:
            keys = [c for c in prepared if c in coins or c.replace("USD", "") == label]
            tr = run_all({c: prepared[c] for c in keys}, p)
            if len(tr):
                tr = tr[tr.entry_time < CUT0]
            s = summarize(tr)
            s["interval"] = bootstrap_interval(tr.r.values) if len(tr) else None
            rows.append(dict(name=name, coin=label, **s))
    ch = next(r for r in rows if r["name"] == CHOSEN[0] and r["coin"] == "BTC and ETH")
    hold = None
    btc = prepared.get("BTCUSD")
    if btc is not None:
        c = btc.close[(btc.index >= btc.index[min(250, len(btc) - 1)]) & (btc.index < CUT0)]
        if len(c) > 2:
            hold = dict(ret=float(c.iloc[-1] / c.iloc[0] - 1), mdd=float((c / c.cummax() - 1).min()))
    v, head, detail = judge(ch, hold)
    return dict(generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), cutoff=str(CUT0.date()),
                verdict=v, headline=head, detail=detail, hold=hold, rows=rows,
                coins={c: dict(start=str(prepared[c].index[0].date()), end=str(prepared[c].index[-1].date()), filled_days=filled[c]) for c in prepared})


def run(refresh=True):
    prepared, filled = {}, {}
    for pair in SOURCES:
        print(f"Downloading {pair} ...")
        d, filled[pair] = fill_gaps(fetch(pair, refresh))
        prepared[pair] = prepare(d)
    return analyse(prepared, filled)


def save(out):
    C.OUT_DIR.mkdir(exist_ok=True)
    (C.OUT_DIR / "history.json").write_text(json.dumps(out))

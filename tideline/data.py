"""Free Binance public candles. No API key. Only closed candles are kept."""
import time
import pandas as pd
import requests
from . import config as C

HOSTS = ["https://data-api.binance.vision", "https://api.binance.com"]
MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def _get(params):
    last = None
    for h in HOSTS:
        try:
            r = requests.get(h + "/api/v3/klines", params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # try the next host
            last = e
    raise RuntimeError(f"Could not reach Binance market data ({last}). Check your internet connection or VPN.")


def load(symbol, interval=None, start=None, refresh=True):
    interval = interval or C.TIMEFRAME
    start = start or C.HISTORY_START
    C.DATA_DIR.mkdir(exist_ok=True)
    f = C.DATA_DIR / f"{symbol}_{interval}.csv"
    old = None
    if f.exists():
        old = pd.read_csv(f, index_col=0)
        old.index = pd.to_datetime(old.index, utc=True)
    if refresh or old is None:
        if old is not None:
            nxt = int(old.index[-1].timestamp() * 1000) + MS[interval]
        else:
            nxt = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
        now = int(time.time() * 1000)
        rows = []
        while nxt < now:
            b = _get(dict(symbol=symbol, interval=interval, startTime=nxt, limit=1000))
            if not b:
                break
            rows += b
            nxt = b[-1][0] + MS[interval]
            if len(b) < 1000:
                break
            time.sleep(0.1)
        rows = [r for r in rows if r[6] < now]  # close time in the past = closed candle
        if rows:
            new = pd.DataFrame(rows).iloc[:, :6]
            new.columns = ["t", "open", "high", "low", "close", "volume"]
            new.index = pd.to_datetime(new.pop("t"), unit="ms", utc=True)
            new = new.astype(float)
            old = new if old is None else pd.concat([old, new])
            old = old[~old.index.duplicated(keep="last")].sort_index()
            old.to_csv(f)
    return old

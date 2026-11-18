"""Tideline core. The backtest and the live scanner both use this file,
so what you test is exactly what you trade."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from . import config as C


@dataclass
class P:
    adx_min: float = 20.0        # minimum trend strength
    atr_lo: float = 0.20         # volatility must sit between these percentiles
    atr_hi: float = 0.90         # of the last 250 candles
    pull_rsi: float = 45.0       # pullback: RSI dips to this, then recovers (shorts use 100 - this)
    stop_atr: float = 2.0        # stop distance from entry, in ATR
    stop_min: float = 1.0        # skip trade if stop closer than this many ATR
    stop_max: float = 3.0        # skip trade if stop farther than this many ATR
    trig_atr: float = 0.1        # buy-stop sits this far beyond the signal candle
    entry_valid: int = 3         # candles the entry order stays alive
    tp1_r: float = 1.0
    tp2_r: float = 2.0
    w1: float = 0.40             # share closed at TP1
    w2: float = 0.30             # share closed at TP2 (the rest is the runner)
    trail_atr: float = 3.0       # runner trails highest high minus this many ATR
    stale_bars: int = 30         # exit if +1R is not reached within this many candles
    shorts: bool = False         # spot cannot short; enable only for futures
    use_breakout: bool = True
    mode: str = "classic"        # "classic" = pullback + breakout, "donchian" = pure trend breakout
    don_n: int = 55              # donchian: breakout lookback in candles
    trail_from_start: bool = False  # trail the stop from entry instead of only after TP1
    trend_exit: bool = True      # exit on two closes beyond the 50 average
    max_open: int = 3            # concurrent trades allowed across all coins
    funding_per_bar: float = 0.0 # futures funding paid per candle held, as a fraction of position value


# ---------- indicators ----------
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def atr(d, n=14):
    pc = d.close.shift()
    tr = pd.concat([d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(d, n=14):
    up, dn = d.high.diff(), -d.low.diff()
    plus = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=d.index)
    minus = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=d.index)
    a = atr(d, n)
    pdi = 100 * plus.ewm(alpha=1 / n, adjust=False).mean() / a
    mdi = 100 * minus.ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def prepare(df):
    """Add indicators. Every value at row i only uses data up to row i."""
    d = df[["open", "high", "low", "close", "volume"]].copy()
    for n in (20, 50, 200):
        d[f"ema{n}"] = ema(d.close, n)
    d["rsi"], d["atr"], d["adx"] = rsi(d.close), atr(d), adx(d)
    d["rank"] = d.atr.rolling(250).apply(lambda x: (x <= x[-1]).mean(), raw=True)
    d["dh"] = d.high.rolling(20).max().shift(1)
    d["dl"] = d.low.rolling(20).min().shift(1)
    d["vma"] = d.volume.rolling(20).mean()
    d["rng"] = d.high - d.low
    # Daily trend bias, taken from the previous COMPLETED day only.
    day = d.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    e50, e200 = ema(day.close, 50), ema(day.close, 200)
    warm = pd.Series(np.arange(len(day)) >= 200, index=day.index)
    reg = pd.DataFrame({"dup": (day.close > e200) & (e50 > e200) & warm,
                        "ddn": (day.close < e200) & (e50 < e200) & warm}).shift(1, fill_value=False)
    reg = reg.astype(int).reindex(d.index, method="ffill").fillna(0).astype(bool)
    d["dup"], d["ddn"] = reg.dup, reg.ddn
    return d


# ---------- signals ----------
def build_orders(d, p):
    """Return entry orders found on closed candles, oldest first."""
    found = []
    for side in ((1, -1) if p.shorts else (1,)):
        if p.mode == "donchian":
            hi = d.high.rolling(p.don_n).max().shift(1)
            lo = d.low.rolling(p.don_n).min().shift(1)
            if side == 1:
                m = (d.close > hi) & (d.close > d.ema200) & (d.adx >= p.adx_min)
            else:
                m = (d.close < lo) & (d.close < d.ema200) & (d.adx >= p.adx_min)
            found += [(int(i), side, "breakout") for i in np.flatnonzero(m.values)]
            continue
        if side == 1:
            reg = d.dup & (d.ema50 > d.ema200)
            zone = (d.low <= d.ema20) & (d.low >= d.ema50 - 0.3 * d.atr)
            mom = (d.rsi.rolling(5).min() <= p.pull_rsi) & (d.rsi > p.pull_rsi)
            cand = (d.close > d.open) & (d.close > d.ema20)
            brk = d.close > d.dh
        else:
            reg = d.ddn & (d.ema50 < d.ema200)
            zone = (d.high >= d.ema20) & (d.high <= d.ema50 + 0.3 * d.atr)
            mom = (d.rsi.rolling(5).max() >= 100 - p.pull_rsi) & (d.rsi < 100 - p.pull_rsi)
            cand = (d.close < d.open) & (d.close < d.ema20)
            brk = d.close < d.dl
        reg = reg & (d.adx >= p.adx_min) & d["rank"].between(p.atr_lo, p.atr_hi)
        pull = reg & zone & mom & cand & (d.rng <= 2 * d.atr)
        quiet = d.rng.shift(1).rolling(10).mean() < 0.8 * d.atr
        bo = reg & brk & quiet & (d.adx > d.adx.shift(3)) & (d.volume >= 1.5 * d.vma) & ~pull
        if not p.use_breakout:
            bo = bo & False
        for kind, mask in (("pullback", pull), ("breakout", bo)):
            for i in np.flatnonzero(mask.values):
                found.append((int(i), side, kind))
    found.sort()
    orders, taken = [], set()
    for i, side, kind in found:
        if i in taken:
            continue
        r, a = d.iloc[i], float(d.atr.iloc[i])
        if kind == "pullback":
            trig = float(r.high + p.trig_atr * a) if side == 1 else float(r.low - p.trig_atr * a)
            ref, exp = trig, i + p.entry_valid
        else:
            trig, ref, exp = None, float(r.close), i + 1
        if p.mode == "donchian":
            stop = ref - side * p.stop_atr * a
        elif side == 1:
            swing = float(d.low.iloc[max(0, i - 4):i + 1].min())
            stop = min(swing, ref - p.stop_atr * a) - 0.2 * a
        else:
            swing = float(d.high.iloc[max(0, i - 4):i + 1].max())
            stop = max(swing, ref + p.stop_atr * a) + 0.2 * a
        dist = abs(ref - stop)
        if not (p.stop_min * a <= dist <= p.stop_max * a):
            continue
        taken.add(i)
        orders.append(dict(i=i, time=str(d.index[i]), side=side, kind=kind, trigger=trig,
                           stop=float(stop), atr=a, expires=exp, ref=float(ref)))
    return orders


def fill_price(od, o, h, l, p):
    """Price an order fills at on a candle: a number, None (no fill) or False (cancel)."""
    s = od["side"]
    if od["kind"] == "breakout":
        px = o
    elif s == 1:
        px = max(o, od["trigger"]) if h >= od["trigger"] else None
    else:
        px = min(o, od["trigger"]) if l <= od["trigger"] else None
    if px is None:
        return None
    if s * (px - od["stop"]) <= 0 or abs(px - od["stop"]) > p.stop_max * od["atr"]:
        return False  # stop already breached, or stop now too wide
    return px


# ---------- trade management ----------
class Pos:
    def __init__(self, side, entry, stop):
        self.side, self.entry, self.stop, self.stop0 = side, float(entry), float(stop), float(stop)
        self.risk = abs(self.entry - self.stop)
        self.legs, self.left = [], 1.0
        self.t1 = self.t2 = self.closed = False
        self.ext, self.bars, self.below, self.reason = self.entry, 0, 0, None

    def targets(self, p):
        return (self.entry + self.side * p.tp1_r * self.risk, self.entry + self.side * p.tp2_r * self.risk)

    def _leg(self, w, px, label):
        w = min(w, self.left)
        self.legs.append([w, float(px), label])
        self.left -= w

    def close(self, px, label):
        if self.left > 1e-12:
            self.legs.append([self.left, float(px), label])
        self.left, self.closed, self.reason = 0.0, True, label

    def step(self, p, o, h, l, c, e50, a):
        """Feed one CLOSED candle. Returns a list of events. Stops are checked first (pessimistic)."""
        s, ev = self.side, []
        self.bars += 1
        tp1, tp2 = self.targets(p)
        adverse, fav = (l, h) if s == 1 else (h, l)
        if s * (adverse - self.stop) <= 0:
            px = self.stop if s * (o - self.stop) > 0 else o
            lab = "trail" if abs(self.stop - self.stop0) > 1e-12 else "stop"
            self.close(px, lab)
            return [lab]
        if not self.t1 and s * (fav - tp1) >= 0:
            self._leg(p.w1, tp1, "TP1"); self.t1 = True; ev.append("TP1")
            if s * (self.entry - self.stop) > 0:
                self.stop = self.entry  # move stop to break-even
        if self.t1 and not self.t2 and s * (fav - tp2) >= 0:
            self._leg(p.w2, tp2, "TP2"); self.t2 = True; ev.append("TP2")
        self.ext = max(self.ext, h) if s == 1 else min(self.ext, l)
        if self.t1 or p.trail_from_start:
            trail = self.ext - s * p.trail_atr * a
            if s * (trail - self.stop) > 0:
                self.stop = trail
        self.below = self.below + 1 if s * (c - e50) < 0 else 0
        if p.trend_exit and self.below >= 2:
            self.close(c, "trend"); ev.append("trend")
        elif not self.t1 and self.bars >= p.stale_bars:
            self.close(c, "stale"); ev.append("stale")
        return ev

    def net_r(self, funding=0.0):
        """Result in R after fees, slippage and (for futures) funding paid while the position was open."""
        s = self.side
        gross = sum(w * s * (px * (1 - s * C.SLIPPAGE) - self.entry) for w, px, _ in self.legs)
        fees = C.FEE * (self.entry + sum(w * px for w, px, _ in self.legs))
        fund = funding * self.bars * self.entry
        return (gross - fees - fund) / self.risk

    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d):
        o = cls.__new__(cls)
        o.__dict__.update(d)
        return o

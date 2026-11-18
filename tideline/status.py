"""Shows how close each coin is to triggering a signal. Run it any time; it changes nothing."""
from . import config as C
from .data import load
from .engine import prepare


def levels(d, p):
    """What tomorrow's daily close must beat for a breakout signal, using only closed candles."""
    last = d.iloc[-1]
    level = float(d.high.rolling(p.don_n).max().iloc[-1])
    return dict(close=float(last.close), level=level, need=level / float(last.close) - 1,
                trend=float(last.close) > float(last.ema200), ema_gap=float(last.ema200) / float(last.close) - 1, ema200=float(last.ema200), atr=float(last.atr), day=str(d.index[-1])[:10])


def run():
    from .scanner import TF, TFH, p, load_state
    if p.mode != "donchian":
        print("Status view is for the daily breakout system.")
        return
    print(f"Signal rule: a daily close above the {p.don_n}-day high AND above the 200-day average.\n")
    print(f"{'Coin':6} {'Last close':>12} {'Must beat':>12} {'Needs':>8}  Above 200-day average?")
    for s in C.SYMBOLS:
        try:
            lv = levels(prepare(load(s, TF)), p)
        except Exception as e:
            print(f"{s[:-4]:6} could not load ({e.__class__.__name__})")
            continue
        f = lambda x: f"{x:,.2f}" if x >= 100 else f"{x:,.4f}" if x >= 1 else f"{x:,.6f}"
        state = "yes" if lv["trend"] else f"no ({f(lv['ema200'])})"
        print(f"{s[:-4]:6} {f(lv['close']):>12} {f(lv['level']):>12} {lv['need']*100:>+7.1f}%  {state}")
    print(f"\nLatest closed candle: {lv['day']}. A coin only triggers when it closes above its level AND is above its 200-day average.")
    st = load_state()
    print(f"Open paper trades: {', '.join(x['symbol'][:-4] for x in st['positions']) or 'none'}. Waiting entries: {len(st['orders'])}. Finished: {len(st['closed'])}.")

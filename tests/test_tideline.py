import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from tideline.engine import P, Pos, prepare, build_orders
from tideline.backtest import full_report


def synth(n=9000, seed=1):
    """Fake 4h candles with drifting regimes. For plumbing tests only; results mean nothing."""
    rng = np.random.default_rng(seed)
    drift = np.repeat(rng.normal(0.0003, 0.0012, n // 300 + 1), 300)[:n]
    ret = drift + rng.normal(0, 0.012, n)
    close = 100 * np.exp(np.cumsum(ret))
    open_ = np.r_[close[0], close[:-1]]
    hi = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.005, n)))
    lo = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.005, n)))
    vol = rng.lognormal(10, 0.5, n) * (1 + 2 * (np.abs(ret) > 0.02))
    idx = pd.date_range("2019-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame(dict(open=open_, high=hi, low=lo, close=close, volume=vol), index=idx)


def test_no_lookahead():
    """Signals found with only past data must equal signals found with the full history."""
    p = P(shorts=True)
    df = synth(4000)
    full = {o["i"]: o for o in build_orders(prepare(df), p)}
    for cut in (2500, 3100, 3800):
        part = prepare(df.iloc[:cut])
        for o in build_orders(part, p):
            if o["i"] < cut - 5:
                f = full[o["i"]]
                assert abs(f["stop"] - o["stop"]) < 1e-9 and f["kind"] == o["kind"] and f["side"] == o["side"]


def test_donchian_no_lookahead():
    from tideline.research import VARIANTS
    p = VARIANTS[1][2]
    df = synth(4000, seed=3)
    full = {o["i"]: o for o in build_orders(prepare(df), p)}
    assert len(full) > 5
    for cut in (2500, 3100, 3800):
        for o in build_orders(prepare(df.iloc[:cut]), p):
            if o["i"] < cut - 2:
                assert abs(full[o["i"]]["stop"] - o["stop"]) < 1e-9


def test_trend_mode_never_takes_partial_profit():
    from tideline.research import VARIANTS
    p = VARIANTS[1][2]
    pos = Pos(1, 100.0, 91.0)
    pos.step(p, 100, 130, 99, 128, 90, 3)   # big up candle: no TP1/TP2, stop starts trailing
    assert not pos.t1 and pos.stop > 91.0 and not pos.closed


def test_heat_cap_limits_open_risk():
    from tideline.combo import heat_cap
    t = pd.DataFrame(dict(entry_time=pd.date_range("2024-01-01", periods=8, freq="D", tz="UTC"),
                          exit_time=pd.date_range("2024-01-10", periods=8, freq="D", tz="UTC"), r=1.0, risk=0.005))
    assert len(heat_cap(t)) == 5   # 2.5% cap / 0.5% each


def test_open_trade_at_end_blocks_later_signals():
    from tideline.research import VARIANTS
    from tideline.backtest import run_symbol
    p = VARIANTS[3][2]
    for seed in range(1, 25):
        d = prepare(synth(9000, seed).resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna())
        tr = sorted(run_symbol("X", d, p), key=lambda t: t["entry_time"])
        for a, b in zip(tr, tr[1:]):
            assert b["entry_time"] > a["exit_time"], "overlapping trades on one coin"


def test_haircut_keeps_losers_true_size():
    from tideline.risk import haircut
    r = np.array([-1.0, -1.0, -1.0, 4.0, 6.0, 8.0, 3.0])
    h = haircut(r, 0.5)
    assert abs(h.mean() - 0.5) < 1e-9 and (h[r < 0] == -1.0).all() and (h[r > 0] < r[r > 0]).all()


def test_telegram_setup_helpers():
    import tempfile, pathlib
    from tideline.setup_telegram import set_keys, chat_id_from
    d = pathlib.Path(tempfile.mkdtemp())
    (d / ".env.example").write_text("# note\nTELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=\nACCOUNT_BALANCE=1000\n")
    set_keys(d / ".env", d / ".env.example", {"TELEGRAM_BOT_TOKEN": "abc", "TELEGRAM_CHAT_ID": "42", "ACCOUNT_BALANCE": "500"})
    t = (d / ".env").read_text()
    assert "TELEGRAM_BOT_TOKEN=abc" in t and "TELEGRAM_CHAT_ID=42" in t and "ACCOUNT_BALANCE=500" in t and "# note" in t
    assert chat_id_from({"result": [{"message": {"chat": {"id": 7}}}]}) == "7" and chat_id_from({"result": []}) is None


def test_history_download_pagination_and_gap_fill():
    import tempfile, pathlib, time
    from tideline import config as C
    import tideline.history as hs
    C.DATA_DIR = pathlib.Path(tempfile.mkdtemp())
    start = int(pd.Timestamp("2020-01-01", tz="UTC").timestamp())
    days = [start + 86400 * i for i in range(2400) if i not in (5, 6, 7)]   # three missing days
    def fake(url, params):
        got = [d for d in days if d >= params["start"]][:min(params["limit"], 700)]   # short pages must not stop the download
        return {"data": {"ohlc": [dict(timestamp=str(d), open="10", high="12", low="9", close="11", volume="5") for d in got]}}
    hs._get = fake
    df = hs.fetch("BTCUSD")
    assert len(df) == 2400 - 3 and df.index.is_monotonic_increasing and df.index.is_unique   # needed 3 pages
    full, missing = hs.fill_gaps(df)
    assert missing == 3 and len(full) == 2400 and (full.volume == 0).sum() == 3 and full.close.notna().all()


def test_funding_lowers_result_and_rotation_has_no_lookahead():
    pos = Pos(1, 100.0, 95.0)
    pos.step(P(), 100, 106, 99, 105, 90, 3)
    pos.close(110.0, "x")
    assert pos.net_r(0.001) < pos.net_r(0.0)
    from tideline.swing import rotate
    rng = np.random.default_rng(5)
    idx = pd.date_range("2022-01-01", periods=600, freq="D", tz="UTC")
    closes = pd.DataFrame({c: 100 * np.exp(np.cumsum(rng.normal(m, 0.02, 600))) for c, m in zip("ABCDEF", (.003, .002, .0, -.001, -.002, -.003))}, index=idx)
    full, _ = rotate(closes, 30, 2, True)
    part, _ = rotate(closes.iloc[:400], 30, 2, True)
    assert np.allclose(full.iloc[:399].values, part.iloc[:399].values)   # past results never change when the future arrives
    up, _ = rotate(closes, 30, 2, False)
    assert up.sum() != 0 and np.isfinite(up.values).all()


def test_status_levels():
    from tideline.status import levels
    from tideline.research import VARIANTS
    p = VARIANTS[3][2]
    d = prepare(synth(9000, 2).resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna())
    lv = levels(d, p)
    assert lv["level"] >= d.high.iloc[-p.don_n:].max() - 1e-9 and lv["need"] == lv["level"] / lv["close"] - 1


def test_daily_message_names_closest_coin():
    from tideline.scanner import digest_text
    rows = [dict(sym="BTCUSDT", need=0.346, ema_gap=0.168, trend=False), dict(sym="SOLUSDT", need=0.05, ema_gap=-0.02, trend=True)]
    t = digest_text(rows, dict(positions=[], orders=[]))
    assert "SOL" in t and "+5.0%" in t and "1 of 2" in t and "Open trades: none" in t


def test_stop_checked_first():
    pos = Pos(1, 100.0, 95.0)  # risk 5, TP1 at 105
    ev = pos.step(P(), o=100, h=110, l=94, c=108, e50=90, a=3)  # same candle touches stop and TP1
    assert ev == ["stop"] and pos.closed and pos.net_r() < -1.0


def test_tp1_moves_stop_to_breakeven_and_pays_partial():
    p = P()
    pos = Pos(1, 100.0, 95.0)
    assert pos.step(p, 100, 106, 99, 105, 90, 3) == ["TP1"]
    assert pos.stop >= 100.0 and not pos.closed
    pos.step(p, 105, 106, 99.5, 100, 90, 3)
    ev = pos.step(p, 100, 101, 99, 99.5, 90, 3)  # falls back through break-even
    assert pos.closed and pos.net_r() > 0.3  # 40% banked at +1R


def test_short_mirror():
    pos = Pos(-1, 100.0, 105.0)
    assert pos.step(P(), 100, 101, 94, 95, 110, 3) == ["TP1"] and pos.stop <= 100.0


def test_backtest_runs():
    prepared = {"AAA": prepare(synth(9000, 1)), "BBB": prepare(synth(9000, 2))}
    out, tr = full_report(prepared, P(shorts=True))
    assert out["verdict"] in ("pass", "close", "fail") and out["metrics"]["n"] >= 0
    if len(tr):
        assert (tr.exit_time >= tr.entry_time).all()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok ", name)

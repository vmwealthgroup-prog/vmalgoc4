import asyncio, os
import numpy as np, pandas as pd, pytest
from conftest import EMA
from app.engine.rules import eval_group, positions, validate_spec, TEMPLATES
from app.engine.backtest import run_backtest
from app.engine.risk import Limits, check_order
from app.data import demo_candles
from app.security import decrypt, encrypt, hash_password, make_token, decode_token, verify_password

K = dict(symbol="X", side="BUY", qty=1, price=100, position_qty=0, orders_today=0, daily_pnl=0, hhmm="10:00")


def frame(close):
    c = np.array(close, float); return pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c}, index=pd.date_range("2025-01-01", periods=len(c), freq="D"))


def test_cross_and_no_lookahead():
    df = frame([5, 5, 5, 20, 20, 20, 20, 5, 5, 5])
    spec = {"symbol": "X", "exchange": "NSE", "interval": "1d", "entry": {"all": [{"left": {"ind": "close"}, "op": "crosses_above", "right": {"value": 10}}]},
            "exit": {"all": [{"left": {"ind": "close"}, "op": "crosses_below", "right": {"value": 10}}]}}
    assert list(positions(df, spec)) == [0, 0, 0, 1, 1, 1, 1, 0, 0, 0]
    r = run_backtest(df, spec, cost_bps=0, interval="1d")
    # Signals are decided at the close and traded on the NEXT bar: the 5->20 entry gap is NOT captured, while the exit
    # (signalled after the 20->5 crash) is only executed a bar later, so the loss is taken. A lookahead bug would show a big gain.
    assert r["metrics"]["trades"] == 1 and r["metrics"]["total_return_pct"] == -75.0


def test_stop_loss_and_short():
    df = frame([100, 100, 100, 97, 90, 90])
    spec = {"symbol": "X", "exchange": "NSE", "interval": "1d", "risk": {"stop_pct": 2}, "entry": {"all": [{"left": {"ind": "close"}, "op": ">=", "right": {"value": 100}}]}}
    p = list(positions(df, spec)); assert p[:3] == [1, 1, 1] and p[3] == 0
    assert list(positions(df, {**spec, "side": "short", "risk": {}}))[2] == -1


def test_validation():
    for bad in [{}, {**EMA, "side": "x"}, {**EMA, "entry": {}}, {**EMA, "risk": {"stop_pct": -1}}]:
        with pytest.raises(ValueError): validate_spec(bad)
    for t in TEMPLATES: validate_spec({"symbol": "X", "exchange": "NSE", "interval": "1d", **t["spec"]})


def test_risk_gate_rules():
    L = Limits(max_qty=10, max_order_value=1000, max_position_value=1500, max_orders_per_day=2, max_daily_loss=100)
    assert check_order(L, **K)[0]
    cases = [(dict(qty=11), "qty"), (dict(qty=9, price=200), "order value"), (dict(side="SELL"), "short"), (dict(position_qty=15), "position value"),
             (dict(orders_today=2), "daily order"), (dict(daily_pnl=-100), "daily loss"), (dict(hhmm="16:00"), "window"), (dict(duplicate_recent=True), "duplicate"),
             (dict(symbol="Z"), None), (dict(qty=0), "malformed")]
    for kw, frag in cases[:7] + cases[7:8] + cases[9:]:
        ok, why = check_order(L, **{**K, **kw}); assert not ok and frag in why, (kw, why)
    assert not check_order(Limits(blocked=["X"]), **K)[0] and not check_order(Limits(kill_switch=True), **K)[0]
    assert check_order(L, **{**K, "hhmm": "03:00"}, enforce_window=False)[0] is True


def test_risk_gate_never_traps_you_in_a_position():
    hard = Limits(kill_switch=True, max_daily_loss=10, max_orders_per_day=1, window_start="09:20", window_end="09:21", blocked=["X"], allow_short=True)
    state = dict(symbol="X", price=100, orders_today=5, daily_pnl=-9999, hhmm="23:00")
    ok, why = check_order(hard, side="SELL", qty=10, position_qty=10, **state); assert ok and "reduces" in why               # full exit: everything else is ignored
    assert check_order(hard, side="SELL", qty=4, position_qty=10, **state)[0]                                              # partial trim
    assert check_order(hard, side="BUY", qty=10, position_qty=-10, **state)[0]                                             # cover a short
    assert not check_order(hard, side="BUY", qty=1, position_qty=10, **state)[0]                                           # increasing is blocked
    assert not check_order(hard, side="SELL", qty=15, position_qty=10, **state)[0]                                         # flipping to short opens new risk: blocked
    assert not check_order(hard, side="SELL", qty=10, position_qty=0, **state)[0]                                          # opening from flat: blocked
    ok, why = check_order(hard, side="SELL", qty=10, position_qty=10, duplicate_recent=True, **state); assert not ok and "duplicate" in why   # still no double-sends
    assert not check_order(hard, side="SELL", qty=0, position_qty=10, **state)[0]                                          # malformed is always rejected


def test_demo_data_deterministic():
    a, b = demo_candles("TCS", "5m", 100), demo_candles("TCS", "5m", 100)
    assert a["close"].equals(b["close"]) and not a["close"].equals(demo_candles("INFY", "5m", 100)["close"]) and {"open", "high", "low", "close", "volume"} <= set(a.columns)
    assert (a["high"] >= a["low"]).all()


def test_demo_price_independent_of_bar_count():
    last = {n: round(float(demo_candles("TCS", "5m", n)["close"].iloc[-1]), 6) for n in (5, 50, 300, 1000)}
    assert len(set(last.values())) == 1, last           # regression: paper P&L used to jump because these disagreed


def test_security():
    h = hash_password("hunter22!"); assert h != "hunter22!" and verify_password("hunter22!", h) and not verify_password("x", h)
    assert decode_token(make_token(7, "user"))["sub"] == "7"
    with pytest.raises(Exception): decode_token(make_token(7, "user") + "x")
    e = encrypt("api-key-123"); assert "api-key" not in e and decrypt(e) == "api-key-123"


def test_production_refuses_weak_config(monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear(); monkeypatch.setenv("ENV", "production"); monkeypatch.setenv("SECRET_KEY", "dev-secret-change-me")
    with pytest.raises(RuntimeError): get_settings()
    get_settings.cache_clear(); monkeypatch.setenv("SECRET_KEY", "x" * 40); monkeypatch.setenv("ENCRYPTION_KEY", "")
    with pytest.raises(RuntimeError): get_settings()
    monkeypatch.undo(); get_settings.cache_clear()


def test_redis_pubsub_with_fakeredis():
    import fakeredis
    from app.pubsub import RedisPubSub
    async def go():
        ps = RedisPubSub("", client=fakeredis.FakeAsyncRedis(decode_responses=True)); got = []
        async def listen():
            async for ch, m in ps.subscribe(["ticks"]):
                got.append((ch, m)); return
        t = asyncio.create_task(listen()); await asyncio.sleep(0.1); await ps.publish("ticks", {"symbol": "A", "ltp": 1}); await asyncio.wait_for(t, 3)
        assert got == [("ticks", {"symbol": "A", "ltp": 1})] and await ps.ping()
    asyncio.run(go())

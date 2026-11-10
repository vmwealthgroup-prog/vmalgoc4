import datetime as dt
from types import SimpleNamespace as NS
import httpx, pytest
from conftest import ALWAYS, signup
from app import charges, guard, market, notify, quotes
from app.config import get_settings
from app.db import SessionLocal
from app.heartbeat import age_seconds, beat
from app.models import Order, Strategy
from app.runner import run_once

IST = market.IST


@pytest.fixture()
def env(monkeypatch):
    def setter(**kw):
        for k, v in kw.items(): monkeypatch.setenv(k.upper(), str(v))
        get_settings.cache_clear()
    yield setter
    monkeypatch.undo(); get_settings.cache_clear()


def open_window(c, h, **kw):
    lim = c.get("/api/risk-limits", headers=h).json(); lim.update(window_start="00:00", window_end="23:59", **kw); assert c.put("/api/risk-limits", headers=h, json=lim).status_code == 200


# ---------------- charges: worked examples checked by hand
def test_charges_equity_intraday_sell_and_buy():
    s = charges.calc("NSE", "TCS", "SELL", 100, 500, "MIS")          # turnover 50,000
    assert (s["brokerage"], s["stt"], s["stamp_duty"], s["total"]) == (15.0, 12.5, 0.0, 32.01)
    b = charges.calc("NSE", "TCS", "BUY", 100, 500, "MIS")
    assert (b["stt"], b["stamp_duty"], b["total"]) == (0.0, 1.5, 21.01)


def test_charges_delivery_options_and_untracked():
    assert charges.calc("NSE", "TCS", "BUY", 10, 1000, "CNC")["total"] == 11.86          # no brokerage, STT 10, stamp 1.5
    o = charges.calc("NFO", "NIFTY24500CE", "SELL", 50, 100); assert o["instrument"] == "options" and o["total"] == 8.84
    assert charges.calc("NFO", "NIFTYNOVFUT", "BUY", 50, 24000)["instrument"] == "futures"
    assert charges.calc("CRYPTO", "BTC/USD", "BUY", 1, 60000)["total"] == 0.0 and charges.calc("NSE", "X", "BUY", 0, 100)["total"] == 0.0


def test_charges_override_and_validation(env):
    env(charges_json='{"gst_pct": 0, "brokerage_flat": 0}')
    assert charges.calc("NSE", "TCS", "SELL", 100, 500)["total"] == 12.5 + 1.49 + 0.05 + 0.0 or abs(charges.calc("NSE", "TCS", "SELL", 100, 500)["total"] - 14.04) < 0.02
    env(charges_json='{"nonsense": 1}')
    with pytest.raises(ValueError): charges.get_rates()


def test_paper_broker_charges_reduce_cash_and_net_pnl(client, h):
    open_window(client, h); quotes.set_last("CHG", 500.0)
    client.post("/api/orders", headers=h, json={"symbol": "CHG", "exchange": "NSE", "side": "BUY", "qty": 100, "price": 500})
    f = client.get("/api/portfolio", headers=h).json()["funds"]
    assert f["charges_paid"] == 21.01 and f["cash"] == round(1_000_000 - 50_000 - 21.01, 2) and f["net_pnl"] == round(0 - 21.01, 2)


# ---------------- market sessions
def at(y, m, d, hh, mm): return dt.datetime(y, m, d, hh, mm, tzinfo=IST)


def test_market_sessions(env):
    assert market.is_open("NSE", at(2026, 11, 2, 10, 0)) and market.is_open("NFO", at(2026, 11, 2, 15, 30))
    assert not market.is_open("NSE", at(2026, 11, 2, 9, 14)) and not market.is_open("NSE", at(2026, 11, 2, 15, 31))
    assert not market.is_open("NSE", at(2026, 11, 7, 11, 0)) and not market.is_open("BSE", at(2026, 11, 8, 11, 0))      # Sat / Sun
    assert market.is_open("MCX", at(2026, 11, 2, 23, 0)) and not market.is_open("MCX", at(2026, 11, 2, 23, 45))
    assert market.is_open("CRYPTO", at(2026, 11, 7, 3, 0)) and not market.is_open("WAT", at(2026, 11, 2, 10, 0))
    env(market_holidays="2026-11-05, 2026-11-20")
    assert not market.is_open("NSE", at(2026, 11, 5, 11, 0)) and market.is_open("NSE", at(2026, 11, 6, 11, 0))
    assert market.is_open("NSE", dt.datetime(2026, 11, 2, 4, 30, tzinfo=dt.timezone.utc))                # tz-aware UTC input is converted to IST (10:00)


def test_square_off_due(env):
    assert market.square_off_due("NSE", "MIS", None, at(2026, 11, 2, 15, 15)) and not market.square_off_due("NSE", "MIS", None, at(2026, 11, 2, 15, 14))
    assert not market.square_off_due("NSE", "CNC", None, at(2026, 11, 2, 15, 20)) and not market.square_off_due("CRYPTO", "MIS", None, at(2026, 11, 2, 15, 20))
    assert market.square_off_due("NFO", "MIS", "14:00", at(2026, 11, 2, 14, 0))


# ---------------- notifications
def test_notify_channels_dedupe_and_failures(env):
    notify._recent.clear(); sent = []
    def handler(req):
        sent.append((str(req.url), req.content.decode()))
        return httpx.Response(500 if "discord" in str(req.url) else 200, json={"ok": True})
    notify._transport = httpx.MockTransport(handler)
    try:
        env(telegram_bot_token="TOK123", telegram_chat_id="42", discord_webhook_url="https://discord.example/hook", notify_webhook_url="https://hooks.example/x")
        assert notify.channels() == ["telegram", "discord", "webhook"]
        r = notify.notify("hello")
        assert r["telegram"] == "ok" and r["webhook"] == "ok" and r["discord"].startswith("error") and "TOK123" not in str(r)
        assert any("api.telegram.org/botTOK123/sendMessage" in u and '"chat_id":"42"' in b.replace(" ", "") for u, b in sent)
        n = len(sent); assert notify.notify("hello") == {"skipped": "duplicate"} and len(sent) == n
        assert notify.notify("hello", force=True)["telegram"] == "ok"
        env(telegram_bot_token="", telegram_chat_id="", discord_webhook_url="", notify_webhook_url=""); notify._recent.clear()
        assert notify.channels() == [] and notify.notify("nobody listening") == {}
    finally:
        notify._transport = None


def test_notify_event_formatting():
    assert notify.format_event({"type": "order", "status": "filled", "side": "BUY", "qty": 3, "symbol": "TCS", "price": 100, "strategy": "s"})[1] == "info"
    t, lvl = notify.format_event({"type": "order", "status": "blocked", "side": "BUY", "qty": 3, "symbol": "TCS", "strategy": "s", "message": "kill switch is ON"}); assert lvl == "warning" and "kill switch" in t
    assert notify.format_event({"type": "breaker", "strategy": "s", "message": "x"})[1] == "error" and notify.format_event({"type": "tick"}) is None


# ---------------- circuit breaker
def O(symbol, side, qty, price, status="filled"): return NS(symbol=symbol, side=side, qty=qty, price=price, status=status)


def test_fifo_closed_trades():
    assert guard.closed_trades([O("A", "BUY", 10, 100), O("A", "SELL", 10, 110)]) == [100]
    assert guard.closed_trades([O("A", "BUY", 10, 100), O("A", "BUY", 10, 102), O("A", "SELL", 15, 104)]) == [40, 10]
    assert guard.closed_trades([O("A", "SELL", 10, 100), O("A", "BUY", 10, 95)]) == [50]                     # short winner
    assert guard.closed_trades([O("A", "BUY", 10, 100), O("A", "SELL", 5, 90, "blocked"), O("A", "SELL", 10, 90)]) == [-100]   # non-filled ignored
    assert guard.closed_trades([O("A", "BUY", 5, 100), O("B", "SELL", 5, 50)]) == []


def _strategy(c, h, **risk):
    spec = {**ALWAYS, "risk": {"qty": 1, **risk}}
    return c.post("/api/strategies", headers=h, json={"name": "brk", "spec": spec}).json()["id"]


def _add_orders(sid, rows, status="filled"):
    with SessionLocal() as db:
        st = db.get(Strategy, sid)
        for sym, side, qty, px in rows: db.add(Order(user_id=st.user_id, strategy_id=sid, symbol=sym, exchange="NSE", side=side, qty=qty, price=px, status=status, mode="paper"))
        db.commit()


def test_breaker_trips_on_losses_but_not_on_wins_or_few_trades(client, h):
    sid = _strategy(client, h, capital=10_000, breaker_trades=3, breaker_loss_pct=3)
    client.patch(f"/api/strategies/{sid}/mode", headers=h, json={"mode": "paper"})
    _add_orders(sid, [("T", "BUY", 10, 100), ("T", "SELL", 10, 90), ("T", "BUY", 10, 100), ("T", "SELL", 10, 90)])      # 2 trades, -200: fewer than N
    with SessionLocal() as db: assert guard.check_breaker(db, db.get(Strategy, sid)) is None
    _add_orders(sid, [("T", "BUY", 10, 100), ("T", "SELL", 10, 95)])                                                    # 3rd loss: -250 total < -300? no
    with SessionLocal() as db: assert guard.check_breaker(db, db.get(Strategy, sid)) is None
    _add_orders(sid, [("T", "BUY", 10, 100), ("T", "SELL", 10, 90)])                                                    # last 3: -100, -50, -100 = -250 ... still under 300
    with SessionLocal() as db: assert guard.check_breaker(db, db.get(Strategy, sid)) is None
    _add_orders(sid, [("T", "BUY", 10, 100), ("T", "SELL", 10, 80)])                                                    # last 3: -50, -100, -200 = -350 < -300
    with SessionLocal() as db:
        st = db.get(Strategy, sid); why = guard.check_breaker(db, st)
        assert why and "switched 'brk' OFF" in why and st.mode == "off"


def test_breaker_trips_on_repeated_failures_and_runner_reports_it(client, h):
    open_window(client, h); sid = _strategy(client, h)
    client.patch(f"/api/strategies/{sid}/mode", headers=h, json={"mode": "paper"})
    _add_orders(sid, [("T", "BUY", 1, 100)] * 5, status="failed")
    with SessionLocal() as db: ev = run_once(db)
    assert ev and ev[0]["type"] == "breaker" and "5 failed orders" in ev[0]["message"]
    assert client.get(f"/api/strategies/{sid}", headers=h).json()["mode"] == "off"
    with SessionLocal() as db: assert run_once(db) == []                                                              # now off: stays quiet


# ---------------- order rate limit and sticky kill switch
def test_order_rate_limit(client, h, env):
    open_window(client, h); env(max_orders_per_second=2)
    res = [client.post("/api/orders", headers=h, json={"symbol": f"R{i}", "exchange": "NSE", "side": "BUY", "qty": 1, "price": 10}).json() for i in range(3)]
    assert [r["status"] for r in res[:2]] == ["filled", "filled"] and res[2]["status"] == "blocked" and "rate limit" in res[2]["message"]


def test_daily_loss_engages_sticky_kill_switch(client, h):
    open_window(client, h, max_daily_loss=100); quotes.set_last("LOSSCO", 100.0)
    assert client.post("/api/orders", headers=h, json={"symbol": "LOSSCO", "exchange": "NSE", "side": "BUY", "qty": 10, "price": 100}).json()["status"] == "filled"
    quotes.set_last("LOSSCO", 80.0)                                                                                     # -200 open loss
    r = client.post("/api/orders", headers=h, json={"symbol": "OTHER", "exchange": "NSE", "side": "BUY", "qty": 1, "price": 10}).json()
    assert r["status"] == "blocked" and "kill switch engaged" in r["message"]
    assert client.get("/api/risk-limits", headers=h).json()["kill_switch"] is True
    quotes.set_last("LOSSCO", 100.0)                                                                                    # P&L recovers, but the switch stays on
    assert client.post("/api/orders", headers=h, json={"symbol": "OTHER", "exchange": "NSE", "side": "BUY", "qty": 1, "price": 10}).json()["message"].startswith("kill switch is ON")


def test_daily_pnl_counts_realized_today_not_all_time(client, h):
    open_window(client, h, max_daily_loss=50); quotes.set_last("RD", 100.0)
    client.post("/api/orders", headers=h, json={"symbol": "RD", "exchange": "NSE", "side": "BUY", "qty": 10, "price": 100})
    quotes.set_last("RD", 90.0)
    client.post("/api/orders", headers=h, json={"symbol": "RD", "exchange": "NSE", "side": "SELL", "qty": 10, "price": 90})       # realized -100 today
    r = client.post("/api/orders", headers=h, json={"symbol": "ZZ", "exchange": "NSE", "side": "BUY", "qty": 1, "price": 10}).json()
    assert r["status"] == "blocked" and "daily loss" in r["message"]


# ---------------- runner: market hours and square-off
def test_runner_respects_market_hours_and_squares_off(client, h, env, monkeypatch):
    open_window(client, h); env(enforce_market_hours="true")
    sid = client.post("/api/strategies", headers=h, json={"name": "a", "spec": ALWAYS}).json()["id"]
    client.patch(f"/api/strategies/{sid}/mode", headers=h, json={"mode": "paper"})
    monkeypatch.setattr(market, "is_open", lambda ex, now=None: False)
    with SessionLocal() as db: assert run_once(db) == []                                                                # closed: nothing happens
    assert client.get("/api/portfolio", headers=h).json()["positions"] == []
    monkeypatch.setattr(market, "is_open", lambda ex, now=None: True); monkeypatch.setattr(market, "square_off_due", lambda *a, **k: False)
    with SessionLocal() as db: ev = run_once(db)
    assert ev[0]["side"] == "BUY" and ev[0]["status"] == "filled"
    monkeypatch.setattr(market, "square_off_due", lambda *a, **k: True)                                                 # 15:15 reached
    with SessionLocal() as db: ev = run_once(db)
    assert ev and ev[0]["side"] == "SELL" and ev[0]["qty"] == 3
    pos = client.get("/api/portfolio", headers=h).json()["positions"]; assert all(p["qty"] == 0 for p in pos)


def test_heartbeat():
    with SessionLocal() as db:
        assert age_seconds(db, "nope") is None
        beat(db, "runner"); assert 0 <= age_seconds(db, "runner") < 5

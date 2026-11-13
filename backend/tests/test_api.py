import asyncio, time
import pytest
from conftest import EMA, ALWAYS, signup
from starlette.websockets import WebSocketDisconnect
from app.pubsub import get_pubsub


def test_openapi_has_all_features(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ["/api/accounts/login", "/api/strategies", "/api/backtests", "/api/scanner/run", "/api/brokers/accounts", "/api/portfolio", "/api/orders", "/api/risk-limits", "/api/admin/users", "/api/dashboard"]:
        assert p in paths, p
    print("path count:", len(paths))


def test_auth_flow(client):
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/accounts/register", json={"email": "x@example.com", "password": "short"}).status_code == 422
    h = signup(client)
    assert client.post("/api/accounts/register", json={"email": "A@example.com", "password": "password123"}).status_code == 409
    assert client.post("/api/accounts/login", json={"email": "a@example.com", "password": "wrongwrong"}).status_code == 401
    r = client.post("/api/accounts/login", json={"email": "a@example.com", "password": "password123"}); assert r.status_code == 200
    assert client.get("/api/me", headers=h).json()["role"] == "user"
    assert client.post("/api/me/password", headers=h, json={"current": "bad", "new": "newpassword1"}).status_code == 400
    assert client.post("/api/me/password", headers=h, json={"current": "password123", "new": "newpassword1"}).status_code == 200
    assert client.post("/api/accounts/login", json={"email": "a@example.com", "password": "newpassword1"}).status_code == 200
    assert client.get("/api/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_login_throttle(client):
    signup(client)
    codes = [client.post("/api/accounts/login", json={"email": "a@example.com", "password": "nope-nope"}).status_code for _ in range(10)]
    assert codes[:8] == [401] * 8 and codes[8] == 429


def test_admin_and_user_management(client):
    boss, user = signup(client, "boss@example.com"), signup(client, "u@example.com")
    assert client.get("/api/me", headers=boss).json()["role"] == "admin"
    assert client.get("/api/admin/users", headers=user).status_code == 403
    users = client.get("/api/admin/users", headers=boss).json(); uid = next(x["id"] for x in users if x["email"] == "u@example.com")
    assert client.patch(f"/api/admin/users/{uid}", headers=boss, json={"is_active": False}).status_code == 200
    assert client.get("/api/me", headers=user).status_code == 401           # disabled user is locked out immediately
    bid = next(x["id"] for x in users if x["email"] == "boss@example.com")
    assert client.patch(f"/api/admin/users/{bid}", headers=boss, json={"role": "user"}).status_code == 400


def test_strategy_crud_and_isolation(client, h):
    other = signup(client, "o@example.com")
    assert len(client.get("/api/strategies/templates", headers=h).json()) >= 3
    assert client.post("/api/strategies", headers=h, json={"name": "bad", "spec": {"symbol": "X"}}).status_code == 422
    bad = {**EMA, "entry": {"all": [{"left": {"ind": "nope"}, "op": ">", "right": {"value": 1}}]}}
    assert client.post("/api/strategies", headers=h, json={"name": "bad", "spec": bad}).status_code == 422
    s = client.post("/api/strategies", headers=h, json={"name": "EMA", "spec": EMA}); assert s.status_code == 201; sid = s.json()["id"]
    assert client.get(f"/api/strategies/{sid}", headers=other).status_code == 404
    assert client.patch(f"/api/strategies/{sid}/mode", headers=h, json={"mode": "live"}).status_code == 400
    assert client.patch(f"/api/strategies/{sid}/mode", headers=h, json={"mode": "paper"}).json()["mode"] == "paper"
    assert client.put(f"/api/strategies/{sid}", headers=h, json={"name": "EMA2", "spec": EMA}).status_code == 409
    client.patch(f"/api/strategies/{sid}/mode", headers=h, json={"mode": "off"})
    assert client.put(f"/api/strategies/{sid}", headers=h, json={"name": "EMA2", "spec": EMA}).json()["name"] == "EMA2"
    assert client.delete(f"/api/strategies/{sid}", headers=h).status_code == 204


def test_backtest_engine_api(client, h):
    r = client.post("/api/backtests", headers=h, json={"spec": EMA, "bars": 800, "source": "demo"}); assert r.status_code == 201, r.text
    b = r.json(); m = b["metrics"]
    assert m["bars"] == 800 and m["data_source"] == "demo" and "sharpe" in m and "max_drawdown_pct" in m and len(b["equity"]) > 10
    assert client.get(f"/api/backtests/{b['id']}", headers=h).json()["trades"] is not None
    assert len(client.get("/api/backtests", headers=h).json()) == 1
    assert client.post("/api/backtests", headers=h, json={}).status_code == 400
    assert client.post("/api/backtests", headers=h, json={"spec": EMA, "source": "openalgo"}).status_code == 400   # no account
    assert client.delete(f"/api/backtests/{b['id']}", headers=h).status_code == 204


def test_scanner(client, h):
    pre = client.get("/api/scanner/presets", headers=h).json()
    r = client.post("/api/scanner/run", headers=h, json={"symbols": ["TCS", "INFY", "SBIN"], "exchange": "NSE", "interval": "1d", "source": "demo", "conditions": pre[3]["conditions"]})
    assert r.status_code == 200 and r.json()["scanned"] == 3 and {"match", "close", "rsi"} <= set(r.json()["results"][0])
    assert client.post("/api/scanner/run", headers=h, json={"symbols": ["TCS"], "conditions": {"all": [{"op": "??"}]}}).status_code == 422


def test_brokers_secure_storage(client, h):
    accts = client.get("/api/brokers/accounts", headers=h).json()
    assert accts[0]["kind"] == "paper"
    assert client.get("/api/brokers/supported", headers=h).status_code == 404
    assert client.post("/api/brokers/accounts", headers=h, json={"label": "legacy", "broker_name": "zerodha", "host": "http://127.0.0.1:5000", "api_key": "SECRETKEY-12345"}).status_code == 405
    assert client.post("/api/brokers/accounts/kite", headers=h, json={"label": "Z", "api_key": "short", "api_secret": "short"}).status_code == 422
    assert client.delete(f"/api/brokers/accounts/{accts[0]['id']}", headers=h).status_code == 400
    assert client.post(f"/api/brokers/accounts/{accts[0]['id']}/test", headers=h).json()["ok"] is True


ORDER = {"symbol": "TCS", "exchange": "NSE", "side": "BUY", "qty": 5, "price": 100.0}


def open_window(client, h, **kw):
    lim = client.get("/api/risk-limits", headers=h).json(); lim.update(window_start="00:00", window_end="23:59", **kw)
    assert client.put("/api/risk-limits", headers=h, json=lim).status_code == 200


def test_order_pipeline_and_risk_gate(client, h):
    open_window(client, h)
    r = client.post("/api/orders", headers=h, json=ORDER).json(); assert r["status"] == "filled", r
    assert client.post("/api/orders", headers=h, json=ORDER).json()["message"].startswith("duplicate")
    assert client.post("/api/orders", headers=h, json={**ORDER, "qty": 500}).json()["message"].startswith("qty")
    assert "short" in client.post("/api/orders", headers=h, json={**ORDER, "symbol": "INFY", "side": "SELL"}).json()["message"]
    assert client.post("/api/orders", headers=h, json={**ORDER, "qty": 99, "price": 99999}).json()["message"] == "order value over limit"
    p = client.get("/api/portfolio", headers=h).json(); assert p["positions"][0]["qty"] == 5 and p["funds"]["cash"] < 1_000_000
    assert client.post("/api/orders", headers=h, json={**ORDER, "side": "SELL", "qty": 5, "price": 101}).json()["status"] == "filled"
    pos = client.get("/api/portfolio", headers=h).json()["positions"][0]; assert pos["qty"] == 0 and pos["realized"] != 0
    open_window(client, h, kill_switch=True)
    assert client.post("/api/orders", headers=h, json={**ORDER, "symbol": "SBIN"}).json()["message"].startswith("kill switch is ON")
    live = client.post("/api/orders", headers=h, json={**ORDER, "symbol": "SBIN", "mode": "live"}).json()
    assert live["status"] == "blocked"
    assert client.post("/api/orders", headers=h, json={**ORDER, "side": "HOLD"}).status_code == 422
    assert client.put("/api/risk-limits", headers=h, json={**client.get("/api/risk-limits", headers=h).json(), "window_start": "9am"}).status_code == 422


def test_live_is_hard_blocked_on_server(client, h):
    from app.db import SessionLocal
    from app.models import BrokerAccount, User
    from app.trading import submit_order
    from app.brokers.factory import ensure_paper_account, get_broker
    open_window(client, h)
    with SessionLocal() as db:
        u = db.query(User).first(); a = ensure_paper_account(db, u)
        o = submit_order(db, u, a, get_broker(db, a), symbol="TCS", exchange="NSE", side="BUY", qty=1, price=10, mode="live")
        assert o.status == "blocked" and "disabled on this server" in o.message


def test_runner_trades_paper_without_duplicates(client, h):
    from app.db import SessionLocal
    from app.runner import run_once
    open_window(client, h)
    sid = client.post("/api/strategies", headers=h, json={"name": "always", "spec": ALWAYS}).json()["id"]
    with SessionLocal() as db: assert run_once(db) == []                       # mode off -> nothing
    client.patch(f"/api/strategies/{sid}/mode", headers=h, json={"mode": "paper"})
    with SessionLocal() as db: ev = run_once(db)
    assert len(ev) == 1 and ev[0]["side"] == "BUY" and ev[0]["qty"] == 3 and ev[0]["status"] == "filled"
    with SessionLocal() as db: assert run_once(db) == []                       # already at target: no second order
    assert client.get("/api/portfolio", headers=h).json()["positions"][0]["qty"] == 3
    assert client.get("/api/dashboard", headers=h).json()["strategies"]["paper"] == 1


def test_runner_blocked_decision_not_spammed(client, h):
    from app.db import SessionLocal
    from app.runner import run_once
    lim = client.get("/api/risk-limits", headers=h).json(); lim.update(window_start="00:00", window_end="23:59", blocked=["TCS"]); client.put("/api/risk-limits", headers=h, json=lim)
    sid = client.post("/api/strategies", headers=h, json={"name": "always", "spec": ALWAYS}).json()["id"]
    client.patch(f"/api/strategies/{sid}/mode", headers=h, json={"mode": "paper"})
    with SessionLocal() as db: first = run_once(db)
    with SessionLocal() as db: second = run_once(db)
    assert first[0]["status"] == "blocked" and second == []


def _wait_subscribed(c, n=1):
    for _ in range(100):
        if c.portal.call(lambda: asyncio.sleep(0, len(get_pubsub()._subs))) >= n: return
        time.sleep(0.02)
    raise AssertionError("websocket never subscribed")


def test_websocket_stream(client, h):
    token = h["Authorization"].split()[1]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/stream?token=bad"): pass
    with client.websocket_connect(f"/ws/stream?token={token}&symbols=NIFTY") as ws:
        _wait_subscribed(client)
        ps = get_pubsub()
        client.portal.call(ps.publish, "ticks", {"type": "tick", "symbol": "BANKNIFTY", "ltp": 1})
        client.portal.call(ps.publish, "ticks", {"type": "tick", "symbol": "NIFTY", "ltp": 22000.5})
        assert ws.receive_json()["symbol"] == "NIFTY"                        # BANKNIFTY filtered out
        uid = client.get("/api/me", headers=h).json()["id"]
        client.portal.call(ps.publish, f"events:{uid}", {"type": "order", "symbol": "TCS"})
        client.portal.call(ps.publish, "events:9999", {"type": "order", "symbol": "LEAK"})
        client.portal.call(ps.publish, "ticks", {"type": "tick", "symbol": "NIFTY", "ltp": 2})
        got = [ws.receive_json() for _ in range(2)]
        assert got[0]["type"] == "order" and got[0]["symbol"] == "TCS" and got[1]["ltp"] == 2   # other user's events never arrive


def test_feeder_publishes_and_caches(client):
    from app.feed import Feeder
    from app import quotes
    f = Feeder(get_pubsub(), [("NIFTY", "NSE")], source="demo")
    got = []
    async def go():
        async def listen():
            async for ch, m in get_pubsub().subscribe(["ticks"]):
                got.append(m); return
        t = asyncio.create_task(listen()); await asyncio.sleep(0.05); await f.tick(); await asyncio.wait_for(t, 2)
    client.portal.call(go)
    assert got[0]["symbol"] == "NIFTY" and got[0]["ltp"] > 0 and quotes.get_last("NIFTY") == got[0]["ltp"]


def test_health(client):
    j = client.get("/health").json(); assert j["status"] == "ok" and j["db"] and j["pubsub"] and j["live_trading_enabled"] is False

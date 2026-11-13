import asyncio, time
import pytest
from conftest import ALWAYS, EMA
from app.db import SessionLocal
from app.policy import set_auth_required
from app.pubsub import get_pubsub


@pytest.fixture()
def open_client(client):
    with SessionLocal() as db:
        set_auth_required(db, False); db.commit()
    return client


def test_config_is_public_and_reports_mode(client, open_client):
    j = open_client.get("/api/app/config").json()
    assert j["mode"] == "open" and j["auth_required"] is False and j["live_available"] is False and j["brokers_available"] is True   # dev env: brokers ok
    assert open_client.get("/health").json()["access_mode"] == "open"


def test_everything_works_without_login(open_client):
    c = open_client
    me = c.get("/api/me").json(); assert me["role"] == "admin" and me["email"] == "owner@local"
    sid = c.post("/api/strategies", json={"name": "open", "spec": EMA}).json()["id"]
    assert c.post("/api/backtests", json={"strategy_id": sid, "source": "demo", "bars": 500}).status_code == 201
    pre = c.get("/api/scanner/presets").json()
    assert c.post("/api/scanner/run", json={"symbols": ["TCS"], "source": "demo", "interval": "1d", "conditions": pre[0]["conditions"]}).status_code == 200
    lim = c.get("/api/risk-limits").json(); lim.update(window_start="00:00", window_end="23:59"); c.put("/api/risk-limits", json=lim)
    o = c.post("/api/orders", json={"symbol": "TCS", "exchange": "NSE", "side": "BUY", "qty": 2, "price": 100}).json(); assert o["status"] == "filled"
    assert c.get("/api/portfolio").json()["positions"][0]["qty"] == 2
    assert c.get("/api/dashboard").status_code == 200 and c.get("/api/admin/users").status_code == 200
    me2 = c.get("/api/me", headers={"Authorization": "Bearer junk"}); assert me2.status_code == 200   # stray tokens are simply ignored


def test_runner_trades_in_open_mode(open_client):
    from app.runner import run_once
    c = open_client; lim = c.get("/api/risk-limits").json(); lim.update(window_start="00:00", window_end="23:59"); c.put("/api/risk-limits", json=lim)
    sid = c.post("/api/strategies", json={"name": "a", "spec": ALWAYS}).json()["id"]
    c.patch(f"/api/strategies/{sid}/mode", json={"mode": "paper"})
    with SessionLocal() as db: ev = run_once(db)
    assert len(ev) == 1 and ev[0]["status"] == "filled"


def test_websocket_needs_no_token_in_open_mode(open_client):
    c = open_client
    with c.websocket_connect("/ws/stream?symbols=NIFTY") as ws:
        for _ in range(100):
            if c.portal.call(lambda: asyncio.sleep(0, len(get_pubsub()._subs))) >= 1: break
            time.sleep(0.02)
        c.portal.call(get_pubsub().publish, "ticks", {"type": "tick", "symbol": "NIFTY", "ltp": 123.0})
        assert ws.receive_json()["ltp"] == 123.0


def test_live_trading_is_never_possible_in_open_mode(open_client):
    c = open_client
    sid = c.post("/api/strategies", json={"name": "a", "spec": EMA}).json()["id"]
    assert c.patch(f"/api/strategies/{sid}/mode", json={"mode": "live", "account_id": 1}).status_code == 403
    assert c.get("/api/brokers/supported").status_code == 404
    assert c.post("/api/backtests", json={"spec": EMA, "source": "openalgo"}).status_code == 400


def test_hosted_open_mode_blocks_brokers(open_client, monkeypatch):
    import base64, os
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ENV", "production"); monkeypatch.setenv("SECRET_KEY", "x" * 40); monkeypatch.setenv("ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    try:
        c = open_client
        assert c.get("/api/app/config").json()["brokers_available"] is False
        r = c.post("/api/brokers/accounts", json={"label": "Z", "broker_name": "zerodha", "host": "http://127.0.0.1:5000", "api_key": "k" * 20}); assert r.status_code == 403
        assert c.get("/api/brokers/supported").status_code == 404
        assert c.post("/api/backtests", json={"spec": EMA, "source": "openalgo"}).status_code in (400, 403)
    finally:
        monkeypatch.undo(); get_settings.cache_clear()


def test_turn_login_on_from_inside_then_off(open_client):
    c = open_client
    assert c.put("/api/app/auth", json={"required": True}).status_code == 422                                  # must set credentials first
    assert c.put("/api/app/auth", json={"required": True, "email": "me@example.com", "password": "short"}).status_code == 422
    sid = c.post("/api/strategies", json={"name": "keep me", "spec": EMA}).json()["id"]                       # data made in open mode survives
    r = c.put("/api/app/auth", json={"required": True, "email": "Me@Example.com", "password": "password123"}); assert r.status_code == 200 and r.json()["owner_email"] == "me@example.com"
    assert c.get("/api/app/config").json()["mode"] == "login"
    assert c.get("/api/me").status_code == 401 and c.get("/api/strategies").status_code == 401                 # now locked
    assert c.post("/api/accounts/login", json={"email": "me@example.com", "password": "wrong-pass1"}).status_code == 401
    tok = c.post("/api/accounts/login", json={"email": "me@example.com", "password": "password123"}).json()["token"]; h = {"Authorization": f"Bearer {tok}"}
    assert c.get("/api/me", headers=h).json()["role"] == "admin" and any(s["id"] == sid for s in c.get("/api/strategies", headers=h).json())
    assert c.put("/api/app/auth", headers=h, json={"required": False, "password": "wrong-pass1"}).status_code == 403
    assert c.put("/api/app/auth", headers=h, json={"required": False}).status_code == 403
    assert c.put("/api/app/auth", headers=h, json={"required": False, "password": "password123"}).json() == {"auth_required": False}
    assert c.get("/api/me").json()["email"] == "me@example.com"                                               # open again, same owner and data


def test_only_admins_can_change_access_mode(client):
    from conftest import signup
    signup(client, "boss@example.com"); h = signup(client, "plain@example.com")
    assert client.put("/api/app/auth", headers=h, json={"required": False, "password": "password123"}).status_code == 403
    assert client.get("/api/app/config").json()["mode"] == "login"

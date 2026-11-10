import datetime as dt, json
import httpx, pytest
from conftest import signup
from app import market, notify, quotes, runner
from app.brokers import kite
from app.brokers.base import BrokerError
from app.brokers.crypto import CcxtAdapter
from app.config import get_settings
from app.db import SessionLocal
from app.heartbeat import beat
from app.models import BrokerAccount, Webhook
from app.routers import system
from app.security import decrypt


@pytest.fixture()
def env(monkeypatch):
    def setter(**kw):
        for k, v in kw.items(): monkeypatch.setenv(k.upper(), str(v))
        get_settings.cache_clear()
    yield setter
    monkeypatch.undo(); get_settings.cache_clear()


def open_window(c, h, **kw):
    lim = c.get("/api/risk-limits", headers=h).json(); lim.update(window_start="00:00", window_end="23:59", **kw); assert c.put("/api/risk-limits", headers=h, json=lim).status_code == 200


class FakeKite:
    placed = []
    def __init__(self, api_key=None, access_token=None, **kw): self.api_key, self.token = api_key, access_token
    def login_url(self): return f"https://kite.zerodha.com/connect/login?v=3&api_key={self.api_key}"
    def generate_session(self, request_token, api_secret):
        if request_token == "badtoken": raise Exception("Token is invalid or has expired.")
        return {"access_token": "AT-" + request_token}
    def set_access_token(self, t): self.token = t
    def place_order(self, **kw):
        if kw["tradingsymbol"] == "BOOM": raise Exception("Insufficient funds")
        FakeKite.placed.append(kw); return 240101000123
    def positions(self):
        return {"net": [{"tradingsymbol": "SBIN", "exchange": "NSE", "quantity": -10, "average_price": 800.5, "last_price": 790, "pnl": 105},
                        {"tradingsymbol": "OLD", "exchange": "NSE", "quantity": 0, "pnl": 0}], "day": [{"pnl": -40.5}, {"pnl": 10}]}
    def holdings(self): return [{"tradingsymbol": "TCS", "exchange": "NSE", "quantity": 2, "t1_quantity": 1, "average_price": 3000, "last_price": 3100, "pnl": 300}]
    def margins(self): return {"equity": {"net": 51000.5, "available": {"cash": 50000.25}}}
    def ltp(self, key): return {key: {"last_price": 101.5}}


@pytest.fixture()
def fake_kite(monkeypatch):
    FakeKite.placed = []; monkeypatch.setattr(kite, "KiteConnect", FakeKite); return FakeKite


def creds(token="AT", date=None): return {"api_key": "KEY123", "api_secret": "SEC456", "access_token": token, "token_date": date or kite.today()}


# ---------------- Zerodha adapter
def test_kite_adapter_parsing_and_orders(fake_kite, env):
    a = kite.KiteAdapter(creds())
    p = a.positions(); assert len(p) == 1 and p[0] == {"symbol": "SBIN", "exchange": "NSE", "qty": -10.0, "avg_price": 800.5, "ltp": 790.0, "pnl": 105.0}
    assert a.daily_pnl() == -30.5                                              # from Kite's "day" book, not the net book
    assert a.holdings()[0]["qty"] == 3.0 and a.funds() == {"cash": 50000.25, "equity": 51000.5, "unrealized_pnl": 105.0} and a.quote("INFY", "NSE") == {"ltp": 101.5}
    r = a.place_order(symbol="TCS", exchange="NSE", side="buy", qty=3.0, price_hint=100, product="MIS", strategy="vmalgo-12 ema!")
    assert r == {"order_id": "240101000123", "status": "sent", "price": 100}
    k = fake_kite.placed[-1]; assert (k["variety"], k["transaction_type"], k["quantity"], k["order_type"], k["product"], k["tag"]) == ("regular", "BUY", 3, "MARKET", "MIS", "vmalgo12ema")
    assert "market_protection" not in k
    env(kite_market_protection="-1"); a.place_order(symbol="TCS", exchange="NSE", side="SELL", qty=1, price_hint=1); assert fake_kite.placed[-1]["market_protection"] == -1.0
    with pytest.raises(BrokerError, match="Insufficient"): a.place_order(symbol="BOOM", exchange="NSE", side="BUY", qty=1, price_hint=1)
    with pytest.raises(BrokerError, match="unsupported product"): a.place_order(symbol="TCS", exchange="NSE", side="BUY", qty=1, price_hint=1, product="BO")


def test_kite_requires_todays_login(fake_kite):
    yesterday = (dt.datetime.now(market.IST) - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    for c in (creds(date=yesterday), {"api_key": "K", "api_secret": "S"}, creds(token="")):
        with pytest.raises(BrokerError, match="daily login|Daily login"): kite.KiteAdapter(c)


def test_kite_account_endpoints_daily_login_flow(client, h, fake_kite):
    r = client.post("/api/brokers/accounts/kite", headers=h, json={"label": "Zerodha", "api_key": "KEY123", "api_secret": "SEC456"}); assert r.status_code == 201
    a = r.json(); assert a["kind"] == "kite" and a["token_ok"] is False and "SEC456" not in r.text
    with SessionLocal() as db: raw = db.get(BrokerAccount, a["id"]).api_key_enc
    assert "SEC456" not in raw and "KEY123" not in raw and json.loads(decrypt(raw))["api_secret"] == "SEC456"                # encrypted at rest
    assert client.post(f"/api/brokers/accounts/{a['id']}/test", headers=h).json()["ok"] is False                           # no token yet: clear message
    url = client.get(f"/api/brokers/accounts/{a['id']}/kite/login-url", headers=h).json()["url"]; assert "api_key=KEY123" in url and f"account%3D{a['id']}" in url
    assert client.post(f"/api/brokers/accounts/{a['id']}/kite/session", headers=h, json={"request_token": "badtoken"}).status_code == 400
    ok = client.post(f"/api/brokers/accounts/{a['id']}/kite/session", headers=h, json={"request_token": "reqtok123"}).json(); assert ok["token_ok"] is True
    t = client.post(f"/api/brokers/accounts/{a['id']}/test", headers=h).json(); assert t["ok"] is True and t["funds"]["cash"] == 50000.25
    p = client.get(f"/api/portfolio?account_id={a['id']}", headers=h).json(); assert p["positions"][0]["symbol"] == "SBIN" and p["holdings"][0]["symbol"] == "TCS"
    assert next(x for x in client.get("/api/brokers/accounts", headers=h).json() if x["id"] == a["id"])["token_ok"] is True
    other = signup(client, "o@example.com"); assert client.get(f"/api/brokers/accounts/{a['id']}/kite/login-url", headers=other).status_code == 404
    paper = next(x for x in client.get("/api/brokers/accounts", headers=h).json() if x["kind"] == "paper"); assert client.get(f"/api/brokers/accounts/{paper['id']}/kite/login-url", headers=h).status_code == 400


def test_daily_login_alert_once_per_day(client, h, fake_kite, monkeypatch):
    a = client.post("/api/brokers/accounts/kite", headers=h, json={"label": "Zerodha", "api_key": "KEY123", "api_secret": "SEC456"}).json()
    with SessionLocal() as db: db.get(BrokerAccount, a["id"]).live_enabled = True; db.commit()
    monkeypatch.setattr(runner, "now_ist", lambda: dt.datetime(2026, 11, 2, 10, 0, tzinfo=market.IST))                      # Monday 10:00
    with SessionLocal() as db: ev = runner.token_alerts(db)
    assert len(ev) == 1 and ev[0]["type"] == "token" and "daily login" in ev[0]["message"].lower()
    with SessionLocal() as db: assert runner.token_alerts(db) == []                                                          # not repeated today
    monkeypatch.setattr(runner, "now_ist", lambda: dt.datetime(2026, 11, 7, 10, 0, tzinfo=market.IST))                      # Saturday
    with SessionLocal() as db: assert runner.token_alerts(db) == []


# ---------------- crypto read-only account
class FakeEx:
    def fetch_balance(self): return {"total": {"USDT": 1000.0, "BTC": 0.5, "DUST": 0}}
    def fetch_ticker(self, s): return {"last": 60000.0}


def test_crypto_adapter_is_read_only():
    a = CcxtAdapter({"quote": "USDT"}, client=FakeEx())
    assert a.positions() == [] and a.holdings() == [{"symbol": "BTC/USDT", "exchange": "CRYPTO", "qty": 0.5, "avg_price": 0.0, "ltp": 60000.0, "pnl": 0.0}]
    assert a.funds() == {"cash": 1000.0, "equity": 31000.0, "unrealized_pnl": 0.0} and a.quote("BTC/USDT", "CRYPTO") == {"ltp": 60000.0}
    with pytest.raises(BrokerError, match="read-only"): a.place_order(symbol="BTC/USDT", exchange="CRYPTO", side="BUY", qty=1, price_hint=1)


def test_crypto_account_endpoints(client, h):
    body = {"label": "CB", "exchange": "coinbase", "api_key": "k" * 10, "api_secret": "s" * 20}
    assert client.post("/api/brokers/accounts/crypto", headers=h, json={**body, "exchange": "notanexchange"}).status_code == 422
    r = client.post("/api/brokers/accounts/crypto", headers=h, json=body); assert r.status_code == 201 and r.json()["kind"] == "ccxt" and "s" * 20 not in r.text
    assert client.patch(f"/api/brokers/accounts/{r.json()['id']}/live", headers=h, json={"enabled": True, "password": "password123"}).status_code == 400


# ---------------- TradingView webhooks
def make_hook(c, h, name="tv", **kw):
    r = c.post("/api/webhooks", headers=h, json={"name": name, **kw}); assert r.status_code == 201, r.text; return r.json()


def test_webhook_buy_close_and_secrecy(client, h):
    open_window(client, h); quotes.set_last("HOOKCO", 250.0); hook = make_hook(client, h); path = hook["path"]
    assert hook["token"] in path and "token" not in client.get("/api/webhooks", headers=h).json()[0]
    with SessionLocal() as db: stored = db.get(Webhook, hook["id"]).token_hash
    assert stored != hook["token"] and len(stored) == 64                                                         # only the hash is stored
    r = client.post(path, json={"action": "BUY", "symbol": "hookco", "qty": 4}).json(); assert r["status"] == "filled"
    assert client.get("/api/portfolio", headers=h).json()["positions"][0]["qty"] == 4
    assert client.post(path, json={"action": "close", "symbol": "HOOKCO"}).json()["status"] == "filled"          # flattens exactly what is open
    assert client.get("/api/portfolio", headers=h).json()["positions"] == []                                      # flat with zero P&L: nothing left to show
    assert client.post(path, json={"action": "close", "symbol": "HOOKCO"}).json()["status"] == "noop"
    assert client.get("/api/webhooks", headers=h).json()[0]["hits"] == 3
    orders = client.get("/api/orders", headers=h).json(); assert len(orders) == 2 and all(o["mode"] == "paper" for o in orders)


def test_webhook_validation_and_wrong_token(client, h):
    hook = make_hook(client, h); path = hook["path"]
    assert client.post("/api/hooks/tv/not-a-real-token", json={"action": "buy", "symbol": "X"}).status_code == 404
    for bad in ({"action": "yolo", "symbol": "X"}, {"action": "buy"}, {"action": "buy", "symbol": "bad symbol!"}, {"action": "buy", "symbol": "X", "qty": 0},
                {"action": "buy", "symbol": "X", "qty": "abc"}, {"action": "buy", "symbol": "X", "price": -1}, {"action": "buy", "symbol": "X", "product": "BO"}, [1, 2]):
        assert client.post(path, json=bad).status_code == 422, bad
    assert client.post(path, content=b"plain text alert", headers={"Content-Type": "text/plain"}).status_code == 422
    assert client.post(path, content=b"x" * 5000).status_code == 413
    assert client.delete(f"/api/webhooks/{hook['id']}", headers=h).status_code == 204 and client.post(path, json={"action": "buy", "symbol": "X"}).status_code == 404


def test_webhook_respects_risk_gate_and_always_allows_exits(client, h):
    open_window(client, h); quotes.set_last("GATE", 100.0); path = make_hook(client, h)["path"]
    assert client.post(path, json={"action": "buy", "symbol": "GATE", "qty": 5}).json()["status"] == "filled"
    open_window(client, h, kill_switch=True)
    b = client.post(path, json={"action": "buy", "symbol": "GATE", "qty": 1}).json(); assert b["status"] == "blocked" and "kill switch" in b["message"]
    assert client.post(path, json={"action": "close", "symbol": "GATE"}).json()["status"] == "filled"               # can always get out


def test_live_webhooks_need_login_and_a_live_account(client, h):
    assert client.post("/api/webhooks", headers=h, json={"name": "x", "mode": "live"}).status_code == 400            # login mode here, but no live-enabled broker
    assert client.post("/api/webhooks", headers=h, json={"name": "x", "mode": "weird"}).status_code == 422


def test_webhook_in_open_mode_cannot_go_live(client):
    from app.db import SessionLocal as S
    from app.policy import set_auth_required
    with S() as db: set_auth_required(db, False); db.commit()
    assert client.post("/api/webhooks", json={"name": "x", "mode": "live", "account_id": 1}).status_code == 403
    assert client.post("/api/webhooks", json={"name": "paper ok"}).status_code == 201


def test_disabled_user_webhook_is_dead(client, h):
    boss = signup(client, "boss@example.com"); hook = make_hook(client, h)
    uid = client.get("/api/me", headers=h).json()["id"]; assert client.patch(f"/api/admin/users/{uid}", headers=boss, json={"is_active": False}).status_code == 200
    assert client.post(hook["path"], json={"action": "buy", "symbol": "X"}).status_code == 404


# ---------------- system endpoints
def test_system_status_health_and_markets(client, h):
    s = client.get("/api/system/status", headers=h).json()
    assert s["healthy"] is False and any("runner" in p for p in s["problems"]) and s["markets"]["CRYPTO"] is True and s["settings"]["max_orders_per_second"] == 50
    with SessionLocal() as db: beat(db, "runner"); beat(db, "feed")
    s = client.get("/api/system/status", headers=h).json(); assert s["healthy"] is True and s["problems"] == [] and s["runner_age_s"] < 5 and s["access_mode"] == "login"


def test_egress_ip_cached_and_failure_safe(client, h):
    calls = []
    def ok(req): calls.append(1); return httpx.Response(200, text="203.0.113.7\n")
    system._ip_cache.update(t=0, v=None); system._transport = httpx.MockTransport(ok)
    try:
        assert client.get("/api/system/egress-ip", headers=h).json()["ip"] == "203.0.113.7"
        client.get("/api/system/egress-ip", headers=h); assert len(calls) == 1                                       # cached
        system._ip_cache.update(t=0, v=None); system._transport = httpx.MockTransport(lambda r: httpx.Response(500))
        j = client.get("/api/system/egress-ip", headers=h).json(); assert j["ip"] is None and "error" in j
    finally:
        system._transport = None; system._ip_cache.update(t=0, v=None)


def test_notify_test_endpoint_is_admin_only(client, env):
    boss, user = signup(client, "boss@example.com"), signup(client, "u@example.com")
    assert client.post("/api/system/notify-test", headers=user).status_code == 403
    assert client.post("/api/system/notify-test", headers=boss).json()["channels"] == []
    sent = []; notify._transport = httpx.MockTransport(lambda req: (sent.append(str(req.url)), httpx.Response(200))[1])
    try:
        env(discord_webhook_url="https://discord.example/h"); r = client.post("/api/system/notify-test", headers=boss).json()
        assert r["channels"] == ["discord"] and r["results"]["discord"] == "ok" and sent == ["https://discord.example/h"]
    finally:
        notify._transport = None

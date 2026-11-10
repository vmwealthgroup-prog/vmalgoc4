from datetime import datetime, timezone
import ccxt, pytest
from conftest import signup
from app.brokers.base import BrokerError
from app.brokers.crypto import CcxtAdapter
from app.config import get_settings
from app.db import SessionLocal
from app.guard import ledger
from app.models import Order


@pytest.fixture()
def env(monkeypatch):
    def setter(**kw):
        for k, v in kw.items(): monkeypatch.setenv(k.upper(), str(v))
        get_settings.cache_clear()
    yield setter
    monkeypatch.undo(); get_settings.cache_clear()


class FakeExchange:
    created: list = []
    last_price = 62000.0
    reply = None
    def __init__(self, cfg=None): self.cfg, self.sandbox = cfg or {}, False
    def set_sandbox_mode(self, on): self.sandbox = on
    def load_markets(self): pass
    def market(self, s): return {"limits": {"amount": {"min": 0.0001}, "cost": {"min": 5.0}}}
    def amount_to_precision(self, s, q): return f"{int(q * 1e5) / 1e5:.5f}"
    def create_order(self, symbol, typ, side, amount, price=None):
        if symbol == "FAIL/USDT": raise Exception("insufficient balance")
        FakeExchange.created.append((symbol, typ, side, amount, price))
        return FakeExchange.reply or {"id": "ord-1", "status": "closed", "filled": amount, "average": 60010.0}
    def fetch_ticker(self, s): return {"last": FakeExchange.last_price}
    def fetch_balance(self): return {"total": {"USDT": 1500.0, "BTC": 0.01}}


@pytest.fixture()
def fake_ex(monkeypatch):
    FakeExchange.created, FakeExchange.reply, FakeExchange.last_price = [], None, 62000.0
    monkeypatch.setattr(ccxt, "binance", FakeExchange); return FakeExchange


def O(side, qty, price, sym="BTC/USDT", acct=1, status="filled", t=None, user=1):
    return Order(user_id=user, account_id=acct, symbol=sym, exchange="CRYPTO", side=side, qty=qty, price=price, status=status, mode="live", created_at=t or datetime.now(timezone.utc))


# ---------------- adapter
def test_read_only_account_cannot_trade():
    a = CcxtAdapter({"quote": "USDT"}, client=FakeExchange())
    with pytest.raises(BrokerError, match="read-only"): a.place_order(symbol="BTC/USDT", exchange="CRYPTO", side="BUY", qty=0.01, price_hint=60000)
    assert a.positions() == [] and a.funds()["cash"] == 1500.0


def test_order_rounding_minimums_and_exchange_errors(fake_ex):
    a = CcxtAdapter({"quote": "USDT", "trade": True}, db=object(), account_id=1, client=FakeExchange())
    r = a.place_order(symbol="BTC/USDT", exchange="CRYPTO", side="BUY", qty=0.0123456789, price_hint=60000)
    assert fake_ex.created[-1] == ("BTC/USDT", "market", "buy", 0.01234, 60000) and r == {"order_id": "ord-1", "status": "filled", "price": 60010.0, "filled_qty": 0.01234}     # rounded to the market's precision
    a.place_order(symbol="BTC/USDT", exchange="CRYPTO", side="SELL", qty=0.01, price_hint=60000); assert fake_ex.created[-1][4] is None          # no price on sells
    with pytest.raises(BrokerError, match="below the exchange minimum"): a.place_order(symbol="BTC/USDT", exchange="CRYPTO", side="BUY", qty=0.00001, price_hint=60000)
    with pytest.raises(BrokerError, match="order value is below"): a.place_order(symbol="BTC/USDT", exchange="CRYPTO", side="BUY", qty=0.00011, price_hint=1000)
    with pytest.raises(BrokerError, match="insufficient balance"): a.place_order(symbol="FAIL/USDT", exchange="CRYPTO", side="BUY", qty=1, price_hint=100)
    fake_ex.reply = {"id": "ord-2", "status": "open", "filled": 0.002, "average": 60000.0}
    assert a.place_order(symbol="BTC/USDT", exchange="CRYPTO", side="BUY", qty=0.01, price_hint=60000)["status"] == "sent"                       # not fully filled: never recorded as a fill


def test_ledger_fifo_average_and_realized():
    pos, realized = ledger([O("BUY", 0.01, 60000), O("BUY", 0.01, 62000), O("SELL", 0.015, 63000)])
    assert pos["BTC/USDT"] == pytest.approx((0.005, 62000.0)) and [round(p, 2) for _, p in realized] == [30.0, 5.0]       # 0.01 x +3000, then 0.005 x +1000
    assert ledger([O("BUY", 1, 10, status="sent"), O("BUY", 1, 10, status="blocked")]) == ({}, [])


def test_positions_and_daily_pnl_come_from_our_fills(client, h, fake_ex):
    uid = client.get("/api/me", headers=h).json()["id"]; acct = add_trading_account(client, h)["id"]            # real rows: PostgreSQL enforces the foreign keys
    with SessionLocal() as db:
        db.add_all([O("BUY", 0.01, 60000, acct=acct, user=uid), O("SELL", 0.004, 61000, acct=acct, user=uid)]); db.commit()
        a = CcxtAdapter({"quote": "USDT", "trade": True}, db=db, account_id=acct, client=FakeExchange())
        p = a.positions()[0]
        assert (round(p["qty"], 6), p["avg_price"], p["ltp"]) == (0.006, 60000.0, 62000.0) and round(p["pnl"], 2) == 12.0                       # (62000-60000)*0.006
        assert round(a.daily_pnl(), 2) == 16.0                                                                                                    # + 4.00 realized today
        FakeExchange.last_price = 59000.0; assert round(a.daily_pnl(), 2) == round(4 - 6, 2)                                                      # a falling price turns it negative: the guard can see it


# ---------------- through the API, with every live gate
def add_trading_account(c, h, **kw):
    body = {"label": "Binance test", "exchange": "binance", "api_key": "k" * 12, "api_secret": "s" * 20, "trade": True, "sandbox": True, **kw}
    r = c.post("/api/brokers/accounts/crypto", headers=h, json=body); assert r.status_code == 201, r.text; return r.json()


def open_window(c, h, **kw):
    lim = c.get("/api/risk-limits", headers=h).json(); lim.update(window_start="00:00", window_end="23:59", **kw); assert c.put("/api/risk-limits", headers=h, json=lim).status_code == 200


def test_account_flags_and_validation(client, h, fake_ex):
    a = add_trading_account(client, h); assert a["crypto"] == {"trade": True, "sandbox": True} and "s" * 20 not in str(a)
    ro = client.post("/api/brokers/accounts/crypto", headers=h, json={"label": "RO", "exchange": "binance", "api_key": "k" * 12, "api_secret": "s" * 20}).json(); assert ro["crypto"]["trade"] is False
    assert client.patch(f"/api/brokers/accounts/{ro['id']}/live", headers=h, json={"enabled": True, "password": "password123"}).status_code == 400   # read-only can never go live
    class NoTestnet(FakeExchange):
        def set_sandbox_mode(self, on): raise Exception("no sandbox")
    ccxt.coinbase = NoTestnet
    r = client.post("/api/brokers/accounts/crypto", headers=h, json={"label": "CB", "exchange": "coinbase", "api_key": "k" * 12, "api_secret": "s" * 20, "sandbox": True}); assert r.status_code == 422 and "no test network" in r.text


def test_live_crypto_orders_need_every_gate_then_flow_through_risk_checks(client, h, fake_ex, env):
    open_window(client, h); a = add_trading_account(client, h)
    order = {"symbol": "BTC/USDT", "exchange": "CRYPTO", "side": "BUY", "qty": 0.01, "price": 60000, "mode": "live", "account_id": a["id"]}
    assert client.patch(f"/api/brokers/accounts/{a['id']}/live", headers=h, json={"enabled": True, "password": "password123"}).status_code == 400   # server switch off
    r = client.post("/api/orders", headers=h, json=order).json(); assert r["status"] == "blocked" and "disabled on this server" in r["message"] and not fake_ex.created
    env(live_trading_enabled="true")
    assert client.patch(f"/api/brokers/accounts/{a['id']}/live", headers=h, json={"enabled": True, "password": "wrong-pass1"}).status_code == 403
    assert client.patch(f"/api/brokers/accounts/{a['id']}/live", headers=h, json={"enabled": True, "password": "password123"}).json()["live_enabled"] is True
    r = client.post("/api/orders", headers=h, json=order).json(); assert r["status"] == "filled" and r["price"] == 60010.0 and fake_ex.created[-1][:4] == ("BTC/USDT", "market", "buy", 0.01)
    p = client.get(f"/api/portfolio?account_id={a['id']}", headers=h).json(); assert p["positions"][0]["qty"] == 0.01 and p["positions"][0]["avg_price"] == 60010.0
    # the risk gate protects crypto like everything else
    assert client.post("/api/orders", headers=h, json={**order, "qty": 6, "price": 60000}).json()["message"] == "order value over limit"     # 360,000 > the 300,000 limit
    open_window(client, h, kill_switch=True)
    assert client.post("/api/orders", headers=h, json={**order, "qty": 0.001}).json()["message"].startswith("kill switch is ON")
    sell = client.post("/api/orders", headers=h, json={**order, "side": "SELL", "qty": 0.01}).json(); assert sell["status"] == "filled"                    # exits always pass
    assert client.get(f"/api/portfolio?account_id={a['id']}", headers=h).json()["positions"] == [] or client.get(f"/api/portfolio?account_id={a['id']}", headers=h).json()["positions"][0]["qty"] == 0


def test_daily_loss_guard_works_on_live_crypto(client, h, fake_ex, env):
    env(live_trading_enabled="true"); open_window(client, h, max_daily_loss=50); a = add_trading_account(client, h)
    client.patch(f"/api/brokers/accounts/{a['id']}/live", headers=h, json={"enabled": True, "password": "password123"})
    base = {"symbol": "BTC/USDT", "exchange": "CRYPTO", "mode": "live", "account_id": a["id"], "price": 60000}
    assert client.post("/api/orders", headers=h, json={**base, "side": "BUY", "qty": 0.01}).json()["status"] == "filled"
    FakeExchange.last_price = 55000.0                                                        # bought at 60010: unrealized about -50.1
    r = client.post("/api/orders", headers=h, json={**base, "symbol": "ETH/USDT", "side": "BUY", "qty": 0.01, "price": 3000}).json()
    assert r["status"] == "blocked" and "kill switch engaged" in r["message"] and client.get("/api/risk-limits", headers=h).json()["kill_switch"] is True


def test_tradingview_alert_for_crypto_becomes_a_live_order(client, h, fake_ex, env):
    env(live_trading_enabled="true"); open_window(client, h); a = add_trading_account(client, h)
    client.patch(f"/api/brokers/accounts/{a['id']}/live", headers=h, json={"enabled": True, "password": "password123"})
    hook = client.post("/api/webhooks", headers=h, json={"name": "tv-crypto", "mode": "live", "account_id": a["id"]}).json()
    r = client.post(hook["path"], json={"action": "buy", "symbol": "BINANCE:BTCUSDT", "exchange": "CRYPTO", "qty": 0.01, "price": 60000}).json()
    assert r["status"] == "filled" and fake_ex.created[-1][:4] == ("BTC/USDT", "market", "buy", 0.01)                         # prefix stripped, BTCUSDT -> BTC/USDT
    assert client.post(hook["path"], json={"action": "close", "symbol": "BTCUSDT", "exchange": "CRYPTO"}).json()["status"] == "filled"
    assert fake_ex.created[-1][2] == "sell"

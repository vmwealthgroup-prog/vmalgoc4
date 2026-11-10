import pytest
from app.brokers.base import BrokerError
from app.brokers.openalgo import OpenAlgoAdapter


class Fake:
    def __init__(self, **r): self.r = r
    def __getattr__(self, name):
        if name in self.r: return lambda **k: self.r[name]
        raise AttributeError(name)


def adapter(**r):
    a = OpenAlgoAdapter.__new__(OpenAlgoAdapter); a.client = Fake(**r); return a


def test_parses_positions_holdings_funds_quote():
    a = adapter(
        positionbook={"status": "success", "data": [{"symbol": "SBIN", "exchange": "NSE", "quantity": "-10", "average_price": "800.5", "ltp": "790", "pnl": "105"},
                                                    {"symbol": "ZERO", "exchange": "NSE", "quantity": "0", "pnl": "0"}]},
        holdings={"status": "success", "data": {"holdings": [{"symbol": "TCS", "exchange": "NSE", "quantity": 2, "average_price": 3000, "ltp": 3100, "pnl": 200}]}},
        funds={"status": "success", "data": {"availablecash": "50000.5", "collateral": "1000", "m2munrealized": "-20", "m2mrealized": "5"}},
        quotes={"status": "success", "data": {"ltp": 101.5, "bid": 101.4, "ask": 101.6}})
    p = a.positions(); assert len(p) == 1 and p[0]["qty"] == -10 and p[0]["pnl"] == 105 and p[0]["avg_price"] == 800.5
    assert a.holdings()[0]["pnl"] == 200
    f = a.funds(); assert f["cash"] == 50000.5 and f["equity"] == 51000.5 and f["unrealized_pnl"] == -20
    assert a.quote("X", "NSE")["ask"] == 101.6


def test_errors_surface_as_brokererror():
    with pytest.raises(BrokerError, match="bad key"): adapter(funds={"status": "error", "message": "bad key"}).funds()
    with pytest.raises(BrokerError): adapter(placeorder={"status": "error", "message": "rejected"}).place_order(symbol="X", exchange="NSE", side="BUY", qty=1, price_hint=1)
    ok = adapter(placeorder={"status": "success", "orderid": "123"}).place_order(symbol="X", exchange="NSE", side="BUY", qty=1.0, price_hint=5)
    assert ok["order_id"] == "123" and ok["status"] == "sent"

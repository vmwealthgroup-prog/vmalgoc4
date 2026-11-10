"""One adapter for every broker OpenAlgo supports (Zerodha, Angel One, Upstox, Dhan, Fyers, Kotak, ...). OpenAlgo (self-hosted,
AGPL) runs as a separate service; this talks to it over its API with the MIT-licensed `openalgo` Python SDK.
Response parsing is defensive: field names are read with fallbacks because brokers differ."""
from .base import Broker, BrokerError


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _data(resp):
    if not isinstance(resp, dict):
        raise BrokerError("unexpected response from OpenAlgo")
    if resp.get("status") == "error":
        raise BrokerError(resp.get("message", "OpenAlgo error"))
    return resp.get("data", resp)


class OpenAlgoAdapter(Broker):
    def __init__(self, host: str, api_key: str):
        from openalgo import api
        self.client = api(api_key=api_key, host=host)

    def history_client(self):
        return self.client

    def place_order(self, *, symbol, exchange, side, qty, price_hint, product="MIS", strategy="VMAlgo"):
        r = self.client.placeorder(strategy=strategy, symbol=symbol, action=side, exchange=exchange, price_type="MARKET", product=product, quantity=int(qty))
        if not isinstance(r, dict) or r.get("status") != "success":
            raise BrokerError((r or {}).get("message", "order rejected") if isinstance(r, dict) else "order failed")
        return {"order_id": str(r.get("orderid", "")), "status": "sent", "price": price_hint}

    def positions(self):
        d = _data(self.client.positionbook())
        rows = d if isinstance(d, list) else d.get("positions", [])
        return [{"symbol": p.get("symbol"), "exchange": p.get("exchange"), "qty": _f(p.get("quantity", p.get("netqty"))),
                 "avg_price": _f(p.get("average_price", p.get("avgprice"))), "ltp": _f(p.get("ltp")), "pnl": _f(p.get("pnl"))}
                for p in rows if _f(p.get("quantity", p.get("netqty"))) != 0 or _f(p.get("pnl")) != 0]

    def holdings(self):
        d = _data(self.client.holdings())
        rows = d.get("holdings", []) if isinstance(d, dict) else d
        return [{"symbol": h.get("symbol"), "exchange": h.get("exchange"), "qty": _f(h.get("quantity")),
                 "avg_price": _f(h.get("average_price", h.get("avgprice"))), "ltp": _f(h.get("ltp")), "pnl": _f(h.get("pnl"))} for h in rows]

    def funds(self):
        d = _data(self.client.funds())
        return {"cash": _f(d.get("availablecash")), "equity": _f(d.get("availablecash")) + _f(d.get("collateral")),
                "unrealized_pnl": _f(d.get("m2munrealized")), "realized_pnl": _f(d.get("m2mrealized"))}

    def quote(self, symbol, exchange):
        d = _data(self.client.quotes(symbol=symbol, exchange=exchange))
        return {"ltp": _f(d.get("ltp")), "bid": _f(d.get("bid")), "ask": _f(d.get("ask"))}

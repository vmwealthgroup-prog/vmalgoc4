"""Direct Zerodha adapter on the official `kiteconnect` client (MIT). Zerodha does not allow automating its login: a fresh access token is needed every
trading day (one manual 2FA login). Orders must come from the static IP registered for your Kite Connect app."""
import json, re
from datetime import datetime
from kiteconnect import KiteConnect
from ..config import get_settings
from ..market import IST
from .base import Broker, BrokerError


def today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def token_ok(creds: dict) -> bool:
    return bool(creds.get("access_token")) and creds.get("token_date") == today()


def login_url(api_key: str, account_id: int | None = None) -> str:
    url = KiteConnect(api_key=api_key).login_url()
    return url + (f"&redirect_params=account%3D{account_id}" if account_id else "")


def exchange_request_token(api_key: str, api_secret: str, request_token: str) -> str:
    try:
        return KiteConnect(api_key=api_key).generate_session(request_token, api_secret=api_secret)["access_token"]
    except Exception as e:
        raise BrokerError(f"Zerodha rejected the login: {e}")


def _f(x, d=0.0):
    try: return float(x)
    except (TypeError, ValueError): return d


class KiteAdapter(Broker):
    def __init__(self, creds: dict, client=None):
        if not token_ok(creds):
            raise BrokerError("Zerodha login has expired. Zerodha needs one fresh login every trading day: open Brokers and press Daily login.")
        self.kite = client or KiteConnect(api_key=creds["api_key"])
        if client is None: self.kite.set_access_token(creds["access_token"])

    def place_order(self, *, symbol, exchange, side, qty, price_hint, product="MIS", strategy="VMAlgo"):
        if product not in ("MIS", "CNC", "NRML"): raise BrokerError(f"unsupported product {product}")
        extra = {}
        if get_settings().kite_market_protection.strip():
            extra["market_protection"] = float(get_settings().kite_market_protection)
        try:
            oid = self.kite.place_order(variety="regular", exchange=exchange, tradingsymbol=symbol, transaction_type=side.upper(), quantity=int(qty),
                                        product=product, order_type="MARKET", tag=re.sub(r"[^A-Za-z0-9]", "", strategy)[:20] or None, **extra)
        except Exception as e:
            raise BrokerError(str(e)[:200])
        return {"order_id": str(oid), "status": "sent", "price": price_hint}

    def _rows(self, key):
        try:
            return self.kite.positions().get(key, [])
        except Exception as e:
            raise BrokerError(str(e)[:200])

    def positions(self):
        return [{"symbol": p["tradingsymbol"], "exchange": p["exchange"], "qty": _f(p["quantity"]), "avg_price": _f(p.get("average_price")),
                 "ltp": _f(p.get("last_price")), "pnl": _f(p.get("pnl"))} for p in self._rows("net") if _f(p["quantity"]) != 0 or _f(p.get("pnl")) != 0]

    def daily_pnl(self):
        return sum(_f(p.get("pnl")) for p in self._rows("day"))     # Kite's "day" book = today's trades

    def holdings(self):
        try:
            rows = self.kite.holdings()
        except Exception as e:
            raise BrokerError(str(e)[:200])
        return [{"symbol": h["tradingsymbol"], "exchange": h["exchange"], "qty": _f(h["quantity"]) + _f(h.get("t1_quantity")), "avg_price": _f(h.get("average_price")),
                 "ltp": _f(h.get("last_price")), "pnl": _f(h.get("pnl"))} for h in rows]

    def funds(self):
        try:
            eq = self.kite.margins().get("equity", {}) or {}
        except Exception as e:
            raise BrokerError(str(e)[:200])
        cash = _f((eq.get("available") or {}).get("cash"))
        return {"cash": cash, "equity": _f(eq.get("net"), cash), "unrealized_pnl": sum(p["pnl"] for p in self.positions())}

    def quote(self, symbol, exchange):
        key = f"{exchange}:{symbol}"
        try:
            return {"ltp": _f(self.kite.ltp(key)[key]["last_price"])}
        except Exception as e:
            raise BrokerError(str(e)[:200])

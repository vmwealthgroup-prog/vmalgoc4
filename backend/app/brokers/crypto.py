"""Crypto exchange account via ccxt (MIT). Two modes, chosen when the account is added:
  read-only (default)  balances and prices for the portfolio view; it cannot place orders
  trading              spot MARKET orders. Spot exchanges report balances, not positions, so positions and P&L come from a FIFO ledger of our own filled orders;
                       that is what lets the daily-loss guard and kill switch protect crypto trading too.
Use API keys with TRADE permission and WITHDRAWALS DISABLED. Start on the exchange's test network. Live orders still need every live switch (see README)."""
from datetime import datetime
import ccxt
from sqlalchemy import select
from ..guard import ledger
from ..market import IST
from ..models import Order
from .base import Broker, BrokerError


class CcxtAdapter(Broker):
    def __init__(self, creds: dict, db=None, account_id=None, client=None):
        self.quote_ccy, self.trade = creds.get("quote", "USDT").upper(), bool(creds.get("trade"))
        self.db, self.account_id = db, account_id
        if client is None:
            if creds["exchange"] not in ccxt.exchanges: raise BrokerError("unknown exchange")
            client = getattr(ccxt, creds["exchange"])({"apiKey": creds["api_key"], "secret": creds["api_secret"], **({"password": creds["password"]} if creds.get("password") else {}), "enableRateLimit": True})
            if creds.get("sandbox"):
                try: client.set_sandbox_mode(True)
                except Exception: raise BrokerError("this exchange has no test network in ccxt")
        self.ex = client

    # ---- orders
    def place_order(self, *, symbol, exchange, side, qty, price_hint, product="MIS", strategy="VMAlgo"):
        if not self.trade: raise BrokerError("This crypto account is read-only. Add it again with trading enabled to trade.")
        side = side.upper()
        try:
            self.ex.load_markets(); m = self.ex.market(symbol)
            amount = float(self.ex.amount_to_precision(symbol, qty))
            lim = m.get("limits") or {}
            if amount <= 0: raise BrokerError("quantity rounds to zero on this market")
            if (lim.get("amount") or {}).get("min") and amount < lim["amount"]["min"]: raise BrokerError(f"quantity {amount} is below the exchange minimum {lim['amount']['min']}")
            if (lim.get("cost") or {}).get("min") and price_hint and amount * price_hint < lim["cost"]["min"]: raise BrokerError(f"order value is below the exchange minimum {lim['cost']['min']}")
            o = self.ex.create_order(symbol, "market", side.lower(), amount, price_hint if side == "BUY" else None)   # some exchanges size market buys by cost, so a reference price is passed
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(str(e)[:200])
        filled = float(o.get("filled") or 0); avg = float(o.get("average") or o.get("price") or price_hint or 0)
        done = filled > 0 and (o.get("status") == "closed" or filled >= amount * 0.999)
        return {"order_id": str(o.get("id", "")), "status": "filled" if done else "sent", "price": avg, "filled_qty": filled if done else amount}

    # ---- positions from our own fills
    def _ledger(self):
        if not (self.trade and self.db is not None and self.account_id): return {}, []
        orders = self.db.scalars(select(Order).where(Order.account_id == self.account_id, Order.status == "filled").order_by(Order.id)).all()
        return ledger(orders)

    def _ltp(self, symbol, fallback):
        try: return float(self.ex.fetch_ticker(symbol)["last"])
        except Exception: return fallback

    def positions(self):
        pos, _ = self._ledger(); out = []
        for sym, (qty, avg) in pos.items():
            ltp = self._ltp(sym, avg); out.append({"symbol": sym, "exchange": "CRYPTO", "qty": qty, "avg_price": avg, "ltp": ltp, "pnl": (ltp - avg) * qty})
        return out

    def daily_pnl(self):
        _, realized = self._ledger(); today = datetime.now(IST).date()
        def day(t):
            return (t.astimezone(IST) if t.tzinfo else t.replace(tzinfo=__import__("datetime").timezone.utc).astimezone(IST)).date()
        return sum(p for t, p in realized if t is not None and day(t) == today) + sum(p["pnl"] for p in self.positions())

    # ---- read-only views
    def _balances(self):
        try:
            return {a: float(v) for a, v in (self.ex.fetch_balance().get("total") or {}).items() if v and float(v) > 0}
        except Exception as e:
            raise BrokerError(str(e)[:200])

    def holdings(self):
        out = []
        for asset, qty in self._balances().items():
            if asset == self.quote_ccy: continue
            out.append({"symbol": f"{asset}/{self.quote_ccy}", "exchange": "CRYPTO", "qty": qty, "avg_price": 0.0, "ltp": self._ltp(f"{asset}/{self.quote_ccy}", 0.0), "pnl": 0.0})
        return out

    def funds(self):
        cash = self._balances().get(self.quote_ccy, 0.0)
        return {"cash": cash, "equity": cash + sum(h["qty"] * h["ltp"] for h in self.holdings()), "unrealized_pnl": sum(p["pnl"] for p in self.positions())}

    def quote(self, symbol, exchange):
        try: return {"ltp": float(self.ex.fetch_ticker(symbol)["last"])}
        except Exception as e: raise BrokerError(str(e)[:200])

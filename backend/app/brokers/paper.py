from datetime import datetime
from sqlalchemy import select
from .. import charges as charge_model
from ..market import IST
from ..data import demo_candles
from .. import quotes
from ..models import BrokerAccount, PaperPosition
from .base import Broker


def _price(symbol):
    return quotes.get_last(symbol) or float(demo_candles(symbol, "5m", 5)["close"].iloc[-1])


class PaperBroker(Broker):
    def __init__(self, db, account: BrokerAccount):
        self.db, self.acct = db, account

    def _pos(self, symbol, exchange):
        p = self.db.scalar(select(PaperPosition).where(PaperPosition.account_id == self.acct.id, PaperPosition.symbol == symbol, PaperPosition.exchange == exchange))
        if p is None:
            p = PaperPosition(account_id=self.acct.id, symbol=symbol, exchange=exchange, qty=0, avg_price=0, realized_pnl=0); self.db.add(p)
        return p

    def place_order(self, *, symbol, exchange, side, qty, price_hint, product="MIS", strategy="VMAlgo"):
        price = quotes.get_last(symbol) or price_hint or _price(symbol)   # fill at the latest tick; the hint is only a fallback
        p, signed = self._pos(symbol, exchange), (qty if side == "BUY" else -qty)
        today = datetime.now(IST).strftime("%Y-%m-%d")
        if p.day_key != today:
            p.day_key, p.realized_day = today, 0.0
        if p.qty == 0 or (p.qty > 0) == (signed > 0):
            new = p.qty + signed
            p.avg_price = (p.avg_price * abs(p.qty) + price * abs(signed)) / abs(new) if new else 0
            p.qty = new
        else:
            closing, sign = min(abs(signed), abs(p.qty)), (1 if p.qty > 0 else -1)
            gain = (price - p.avg_price) * closing * sign
            p.realized_pnl += gain; p.realized_day += gain
            rem = abs(signed) - closing; p.qty += signed
            p.avg_price = 0 if p.qty == 0 else (price if rem > 0 else p.avg_price)
        self.acct.paper_cash += -qty * price if side == "BUY" else qty * price
        fees = charge_model.calc(exchange, symbol, side, qty, price, product)
        self.acct.paper_cash -= fees["total"]; self.acct.paper_charges = (self.acct.paper_charges or 0.0) + fees["total"]
        self.db.flush()
        return {"order_id": f"paper-{p.id}-{int(__import__('time').time() * 1000)}", "status": "filled", "price": price, "charges": fees["total"]}

    def positions(self):
        out = []
        for p in self.db.scalars(select(PaperPosition).where(PaperPosition.account_id == self.acct.id)):
            ltp = _price(p.symbol)
            if p.qty or p.realized_pnl:
                out.append({"symbol": p.symbol, "exchange": p.exchange, "qty": p.qty, "avg_price": round(p.avg_price, 4), "ltp": round(ltp, 4),
                            "pnl": round((ltp - p.avg_price) * p.qty + p.realized_pnl, 2), "realized": round(p.realized_pnl, 2)})
        return out

    def holdings(self):
        return []

    def daily_pnl(self):
        today = datetime.now(IST).strftime("%Y-%m-%d"); total = 0.0
        for p in self.db.scalars(select(PaperPosition).where(PaperPosition.account_id == self.acct.id)):
            total += (_price(p.symbol) - p.avg_price) * p.qty + (p.realized_day if p.day_key == today else 0.0)
        return total

    def funds(self):
        pos = self.positions()
        mv = sum(p["qty"] * p["ltp"] for p in pos)
        fees = round(self.acct.paper_charges or 0.0, 2)
        return {"cash": round(self.acct.paper_cash, 2), "equity": round(self.acct.paper_cash + mv, 2), "unrealized_pnl": round(sum(p["pnl"] for p in pos), 2),
                "charges_paid": fees, "net_pnl": round(sum(p["pnl"] for p in pos) - fees, 2)}

    def quote(self, symbol, exchange):
        return {"ltp": _price(symbol)}

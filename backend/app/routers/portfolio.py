import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..brokers.factory import ensure_limits, ensure_paper_account, get_broker
from ..db import get_db
from ..deps import current_user, owned_account
from ..models import BrokerAccount, Order, Strategy, User
from ..trading import now_ist, submit_order

router = APIRouter(prefix="/api", tags=["portfolio"])


@router.get("/portfolio")
def portfolio(account_id: int | None = None, u: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned_account(db, u, account_id) if account_id else ensure_paper_account(db, u)
    try:
        b = get_broker(db, a); pos, hold, funds = b.positions(), b.holdings(), b.funds(); err = None
    except Exception as e:
        pos, hold, funds, err = [], [], {}, str(e)[:200]
    value = lambda rows: sum(r["qty"] * r["ltp"] for r in rows)
    db.commit()
    return {"account": {"id": a.id, "label": a.label, "kind": a.kind}, "error": err, "positions": pos, "holdings": hold, "funds": funds,
            "totals": {"positions_value": round(value(pos), 2), "holdings_value": round(value(hold), 2), "pnl": round(sum(r["pnl"] for r in pos + hold), 2)}}


@router.get("/dashboard")
def dashboard(u: User = Depends(current_user), db: Session = Depends(get_db)):
    acct = ensure_paper_account(db, u)
    day = now_ist().replace(hour=0, minute=0, second=0, microsecond=0)
    modes = dict(db.execute(select(Strategy.mode, func.count()).where(Strategy.user_id == u.id).group_by(Strategy.mode)).all())
    recent = db.scalars(select(Order).where(Order.user_id == u.id).order_by(Order.id.desc()).limit(8)).all()
    try:
        funds = get_broker(db, acct).funds()
    except Exception:
        funds = {}
    db.commit()
    return {"strategies": {m: modes.get(m, 0) for m in ("off", "paper", "live")}, "paper_funds": funds,
            "orders_today": db.scalar(select(func.count()).select_from(Order).where(Order.user_id == u.id, Order.created_at >= day.astimezone(day.tzinfo))) or 0,
            "recent_orders": [_order(o) for o in recent]}


def _order(o: Order):
    return {"id": o.id, "symbol": o.symbol, "exchange": o.exchange, "side": o.side, "qty": o.qty, "price": o.price, "status": o.status, "mode": o.mode,
            "message": o.message, "strategy_id": o.strategy_id, "created_at": o.created_at.isoformat()}


@router.get("/orders")
def orders(limit: int = 100, u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_order(o) for o in db.scalars(select(Order).where(Order.user_id == u.id).order_by(Order.id.desc()).limit(min(limit, 500)))]


class OrderIn(BaseModel):
    account_id: int | None = None
    symbol: str = Field(min_length=1, max_length=40)
    exchange: str = Field(default="NSE", max_length=20)
    side: str
    qty: float = Field(gt=0)
    price: float = Field(gt=0, description="reference price used for risk checks")
    mode: str = "paper"
    product: str = "MIS"


@router.post("/orders", status_code=201)
def place(b: OrderIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if b.side.upper() not in ("BUY", "SELL") or b.mode not in ("paper", "live"): raise HTTPException(422, "side must be BUY/SELL and mode paper/live")
    a = owned_account(db, u, b.account_id) if (b.account_id and b.mode == "live") else ensure_paper_account(db, u)
    o = submit_order(db, u, a, get_broker(db, a), symbol=b.symbol.upper(), exchange=b.exchange.upper(), side=b.side, qty=b.qty, price=b.price, mode=b.mode, product=b.product)
    db.commit(); return _order(o)


class LimitsIn(BaseModel):
    max_qty: int = Field(ge=1, le=1_000_000)
    max_order_value: float = Field(ge=0)
    max_position_value: float = Field(ge=0)
    max_orders_per_day: int = Field(ge=1, le=1000)
    max_daily_loss: float = Field(ge=0)
    window_start: str
    window_end: str
    allow_short: bool
    blocked: list[str] = []
    kill_switch: bool

    @field_validator("window_start", "window_end")
    @classmethod
    def hhmm(cls, v):
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v): raise ValueError("use HH:MM")
        return v


@router.get("/risk-limits")
def get_limits(u: User = Depends(current_user), db: Session = Depends(get_db)):
    r = ensure_limits(db, u.id); db.commit()
    return {k: getattr(r, k) for k in LimitsIn.model_fields}


@router.put("/risk-limits")
def put_limits(b: LimitsIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    r = ensure_limits(db, u.id)
    for k, v in b.model_dump().items(): setattr(r, k, [s.upper() for s in v] if k == "blocked" else v)
    db.commit(); return b.model_dump()

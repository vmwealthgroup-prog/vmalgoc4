"""The single path every order takes: live gating -> risk gate -> broker -> audit row. Used by the API and the runner."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from .brokers.base import BrokerError
from .brokers.factory import ensure_limits, live_account_error
from .config import get_settings
from .engine.risk import Limits, check_order
from .models import BrokerAccount, Order, User
from .policy import live_allowed

IST = ZoneInfo("Asia/Kolkata")
COOLDOWN_S = 60


def now_ist():
    return datetime.now(IST)


def _limits(r) -> Limits:
    return Limits(max_qty=r.max_qty, max_order_value=r.max_order_value, max_position_value=r.max_position_value, max_orders_per_day=r.max_orders_per_day,
                  max_daily_loss=r.max_daily_loss, window_start=r.window_start, window_end=r.window_end, allow_short=r.allow_short,
                  blocked=list(r.blocked or []), kill_switch=r.kill_switch)


def submit_order(db, user: User, account: BrokerAccount, broker, *, symbol, exchange, side, qty, price, strategy_id=None, mode="paper", product="MIS") -> Order:
    side = side.upper(); s = get_settings(); t = now_ist()
    o = Order(user_id=user.id, account_id=account.id, strategy_id=strategy_id, symbol=symbol, exchange=exchange, side=side, qty=qty, price=price, status="blocked", mode=mode)
    db.add(o)

    def block(msg):
        o.message = msg[:255]; db.flush(); return o

    if mode == "live":
        if not live_allowed(db): return block("live trading needs login: turn on login in Settings first")
        if not s.live_trading_enabled: return block("live trading is disabled on this server (LIVE_TRADING_ENABLED=false)")
        reason = live_account_error(account)
        if reason: return block(reason)
    recent = db.scalar(select(func.count()).select_from(Order).where(Order.user_id == user.id, Order.status.in_(("filled", "sent")),
                       Order.created_at >= datetime.now(timezone.utc) - timedelta(seconds=1))) or 0
    if recent >= s.max_orders_per_second:
        return block(f"order rate limit: {recent} orders in the last second (cap {s.max_orders_per_second}/s)")
    try:
        positions = broker.positions(); day_pnl = broker.daily_pnl()
    except Exception as e:
        return block(f"could not read positions: {e}")
    cur = next((p["qty"] for p in positions if p["symbol"] == symbol and p["exchange"] == exchange), 0.0)
    day_start = t.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    orders_today = db.scalar(select(func.count()).select_from(Order).where(Order.user_id == user.id, Order.created_at >= day_start, Order.status.in_(("filled", "sent")))) or 0
    dup = db.scalar(select(func.count()).select_from(Order).where(Order.user_id == user.id, Order.symbol == symbol, Order.side == side, Order.qty == qty,
                    Order.status.in_(("filled", "sent")), Order.created_at >= datetime.now(timezone.utc) - timedelta(seconds=COOLDOWN_S))) > 0
    lim = ensure_limits(db, user.id)
    ok, why = check_order(_limits(lim), symbol=symbol, side=side, qty=qty, price=price, position_qty=cur, orders_today=orders_today,
                          daily_pnl=day_pnl, hhmm=t.strftime("%H:%M"), duplicate_recent=dup, enforce_window=exchange != "CRYPTO")
    if not ok:
        if why == "daily loss limit hit":
            lim.kill_switch = True
            why = "daily loss limit hit: kill switch engaged. Review, then reset it in Settings"
        return block(why)
    try:
        r = broker.place_order(symbol=symbol, exchange=exchange, side=side, qty=qty, price_hint=price, product=product, strategy=f"vmalgo-{strategy_id or 'manual'}")
    except (BrokerError, Exception) as e:
        o.status, o.message = "failed", str(e)[:255]; db.flush(); return o
    o.status, o.message, o.broker_order_id, o.price = r["status"], "PASS", r.get("order_id", ""), r.get("price") or price
    if r.get("filled_qty"): o.qty = r["filled_qty"]
    db.flush(); return o

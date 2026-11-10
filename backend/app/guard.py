"""Automatic protections beyond the per-order risk gate: a per-strategy circuit breaker. (The daily-loss kill switch lives in trading.py.)"""
from collections import deque
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from .config import get_settings
from .models import Order, Strategy


def ledger(orders):
    """FIFO ledger from FILLED orders (oldest first). Returns ({symbol: (net_qty, avg_cost)}, [(order_time, realized_pnl)]). Long and short lots."""
    lots: dict[str, deque] = {}; realized = []
    for o in orders:
        if o.status != "filled" or o.price <= 0 or o.qty <= 0:
            continue
        q = lots.setdefault(o.symbol, deque()); signed = o.qty if o.side == "BUY" else -o.qty
        while abs(signed) > 1e-12 and q and (q[0][0] > 0) != (signed > 0):
            lq, lp = q[0]; m = min(abs(lq), abs(signed)); d = 1 if lq > 0 else -1
            realized.append((getattr(o, "created_at", None), (o.price - lp) * m * d))
            q[0] = (lq - m * d, lp); signed -= m * (1 if signed > 0 else -1)
            if abs(q[0][0]) < 1e-12: q.popleft()
        if abs(signed) > 1e-12:
            q.append((signed, o.price))
    pos = {}
    for sym, q in lots.items():
        net = sum(l[0] for l in q)
        if abs(net) > 1e-12: pos[sym] = (net, sum(abs(l[0]) * l[1] for l in q) / sum(abs(l[0]) for l in q))
    return pos, realized


def closed_trades(orders) -> list[float]:
    """Round-trip P&L (in currency) per matched chunk, oldest first."""
    return [p for _, p in ledger(orders)[1]]


def check_breaker(db, st: Strategy) -> str | None:
    """Trips (and switches the strategy OFF) if recent closed trades lost too much, or orders keep failing. Returns the reason."""
    s, r = get_settings(), st.spec.get("risk", {})
    n = int(r.get("breaker_trades") or s.breaker_default_trades); pct = float(r.get("breaker_loss_pct") or s.breaker_default_loss_pct); capital = float(r.get("capital") or 100_000)
    since = datetime.now(timezone.utc) - timedelta(minutes=15)
    failed = db.scalar(select(func.count()).select_from(Order).where(Order.strategy_id == st.id, Order.status == "failed", Order.created_at >= since)) or 0
    reason = None
    if failed >= 5:
        reason = f"{failed} failed orders in 15 minutes"
    else:
        orders = db.scalars(select(Order).where(Order.strategy_id == st.id, Order.status == "filled").order_by(Order.id)).all()
        pnl = closed_trades(orders)[-n:]
        if len(pnl) >= n and sum(pnl) < -pct / 100 * capital:
            reason = f"last {n} closed trades lost {abs(sum(pnl)):,.0f} (more than {pct:g}% of {capital:,.0f})"
    if reason:
        st.mode = "off"
        return f"circuit breaker switched '{st.name}' OFF: {reason}"
    return None

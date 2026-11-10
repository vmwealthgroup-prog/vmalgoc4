"""Pre-trade risk gate (pure logic). The caller supplies current state; every order must pass before it is sent.

Position-REDUCING orders (closing or trimming without flipping to the other side) are always allowed past the kill switch, daily-loss,
order-count, trading-window, blocked-symbol and size checks: a safety stop must never trap you in a losing position."""
from dataclasses import dataclass, field


@dataclass
class Limits:
    max_qty: int = 100
    max_order_value: float = 300_000
    max_position_value: float = 500_000
    max_orders_per_day: int = 20
    max_daily_loss: float = 5_000
    window_start: str = "09:20"
    window_end: str = "15:15"
    allow_short: bool = False
    blocked: list = field(default_factory=list)
    kill_switch: bool = False


def check_order(l: Limits, *, symbol, side, qty, price, position_qty, orders_today, daily_pnl, hhmm,
                duplicate_recent=False, enforce_window=True):
    side = str(side).upper()
    if side not in ("BUY", "SELL") or qty <= 0 or price <= 0: return False, "malformed order"
    new = position_qty + (qty if side == "BUY" else -qty)
    reducing = position_qty != 0 and abs(new) < abs(position_qty) and (new == 0 or (new > 0) == (position_qty > 0))
    if reducing:
        return (False, "duplicate order inside cooldown") if duplicate_recent else (True, "PASS (reduces position)")
    if l.kill_switch: return False, "kill switch is ON (closing orders are still allowed)"
    if symbol in (l.blocked or []): return False, f"{symbol} is blocked"
    if enforce_window and not (l.window_start <= hhmm <= l.window_end): return False, f"outside trading window {l.window_start}-{l.window_end}"
    if daily_pnl <= -abs(l.max_daily_loss): return False, "daily loss limit hit"
    if orders_today >= l.max_orders_per_day: return False, "daily order limit hit"
    if duplicate_recent: return False, "duplicate order inside cooldown"
    if qty > l.max_qty: return False, f"qty {qty:g} over max {l.max_qty}"
    if qty * price > l.max_order_value: return False, "order value over limit"
    if new < 0 and not l.allow_short: return False, "would go short (shorting disabled)"
    if abs(new) * price > l.max_position_value: return False, "position value over limit"
    return True, "PASS"

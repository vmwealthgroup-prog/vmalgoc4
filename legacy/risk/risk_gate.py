"""Pre-trade risk gate. Every order must pass check() before it is sent. Orders are judged as if earlier approved
orders had filled. A BLOCK is final. Idea borrowed from the 'trader-risk' skill; code is original."""
import os, time
from dataclasses import dataclass


@dataclass
class Limits:
    max_qty: int = 50
    max_order_value: float = 200_000
    max_position_value: float = 500_000
    max_orders_per_day: int = 20
    max_daily_loss: float = 5_000
    cooldown_s: int = 60                 # same symbol+side+qty inside this window = duplicate
    allow_short: bool = False
    blocked: tuple = ()
    window: tuple = ("09:20", "15:15")   # no new orders outside this window (local time)
    kill_file: str = "KILL"              # create this file to stop all trading instantly


class RiskGate:
    def __init__(self, limits=None):
        self.l, self.pos, self.orders, self.pnl, self.recent = limits or Limits(), {}, 0, 0.0, {}

    def check(self, symbol, side, qty, price, now=None):
        l, side = self.l, str(side).upper()
        now = now or time.time()
        hhmm = time.strftime("%H:%M", time.localtime(now))
        if os.path.exists(l.kill_file): return False, "kill switch file present"
        if side not in ("BUY", "SELL") or qty <= 0 or price <= 0: return False, "malformed order"
        if symbol in l.blocked: return False, f"{symbol} is blocked"
        if not (l.window[0] <= hhmm <= l.window[1]): return False, f"outside trading window {l.window}"
        if self.pnl <= -abs(l.max_daily_loss): return False, "daily loss limit hit"
        if self.orders >= l.max_orders_per_day: return False, "daily order limit hit"
        key = (symbol, side, qty)
        if now - self.recent.get(key, -1e9) < l.cooldown_s: return False, "duplicate inside cooldown"
        if qty > l.max_qty: return False, f"qty {qty} over max {l.max_qty}"
        if qty * price > l.max_order_value: return False, "order value over limit"
        new = self.pos.get(symbol, 0) + (qty if side == "BUY" else -qty)
        if new < 0 and not l.allow_short: return False, "would go short"
        if abs(new) * price > l.max_position_value: return False, "position value over limit"
        return True, "PASS"

    def record(self, symbol, side, qty, now=None):
        """Call after an order is actually sent."""
        self.pos[symbol] = self.pos.get(symbol, 0) + (qty if side.upper() == "BUY" else -qty)
        self.orders += 1
        self.recent[(symbol, side.upper(), qty)] = now or time.time()

    def add_pnl(self, amount):
        self.pnl += amount

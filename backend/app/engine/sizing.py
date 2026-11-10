import math


def atr_qty(equity: float, risk_pct: float, atr_value: float, stop_atr: float = 2.0, lot: int = 1, max_qty: float | None = None) -> int:
    per = atr_value * stop_atr
    if per <= 0:
        return 0
    q = int(math.floor(equity * risk_pct / 100 / per / lot)) * lot
    return int(min(q, max_qty)) if max_qty else q

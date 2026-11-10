"""Position sizing and band rebalancing. Original code; ideas from the 'trader-budget' and 'trader-rebalance' skills."""
import math
import pandas as pd


def atr(df, n=14):
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def atr_qty(equity, risk_pct, atr_value, stop_atr=2.0, lot=1, max_qty=None):
    """Quantity so that a stop `stop_atr` ATRs away loses about risk_pct % of equity. Rounded down to whole lots."""
    per_unit = atr_value * stop_atr
    if per_unit <= 0:
        return 0
    q = int(math.floor(equity * risk_pct / 100 / per_unit / lot)) * lot
    return min(q, max_qty) if max_qty else q


def cap_weights(weights, cap_pct):
    """Normalise to 100% and pin anything over the cap at the cap, sharing the excess over the rest by weight."""
    tot = sum(weights.values()); w = {k: v / tot for k, v in weights.items()}; cap = cap_pct / 100
    if cap * len(w) < 1 - 1e-9:
        raise ValueError("cap too low for this many assets")
    fixed = {}
    while True:
        free = {k: v for k, v in w.items() if k not in fixed}
        if not free:
            return fixed
        rem, s = 1 - sum(fixed.values()), sum(free.values())
        scaled = {k: v / s * rem for k, v in free.items()}
        over = [k for k, v in scaled.items() if v > cap + 1e-12]
        if not over:
            return {**fixed, **scaled}
        for k in over:
            fixed[k] = cap


def rebalance_trades(values, targets, cash=0.0, band_pts=5.0, buffer_pct=0.0, min_trade=0.0):
    """values: {asset: current value}. Trades only assets drifting more than band_pts from target, back to target.
    Sells first. Buys are scaled down if cash (after sells, above the buffer) is short. Returns [(asset, side, amount, drift_pts)]."""
    total = sum(values.values()) + cash
    tw = {k: v / sum(targets.values()) for k, v in targets.items()}
    tgt = {k: total * (1 - buffer_pct / 100) * tw[k] for k in tw}
    sells, buys = [], []
    for k in tw:
        cur = values.get(k, 0.0); drift = (cur - tgt[k]) / total * 100; amt = abs(tgt[k] - cur)
        if abs(drift) > band_pts and amt >= min_trade:
            (buys if tgt[k] > cur else sells).append([k, "BUY" if tgt[k] > cur else "SELL", amt, drift])
    avail = cash + sum(s[2] for s in sells) - total * buffer_pct / 100
    need = sum(b[2] for b in buys)
    if need > max(avail, 0):
        f = max(avail, 0) / need if need else 0
        for b in buys:
            b[2] *= f
    return [(a, s, round(x, 2), round(d, 2)) for a, s, x, d in sells + buys if x > 0]

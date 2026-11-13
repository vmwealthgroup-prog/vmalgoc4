"""Single-instrument, event-driven OHLC backtest.

Signals are evaluated at completed candle closes and orders execute at the next
candle open. Stops/targets are evaluated against the execution candle's OHLC.
This is a research simulator, not a broker fill or portfolio-margin model.
"""
import math

import numpy as np
import pandas as pd

from .rules import eval_group

BARS_PER_YEAR = {"1m": 75 * 250 * 5, "5m": 75 * 250, "15m": 25 * 250, "1h": 7 * 250, "1d": 252}
_OHLC = ("open", "high", "low", "close")


def _finite_nonnegative(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite non-negative number") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return number


def _validate_inputs(df, spec, cost_bps, max_points):
    if not isinstance(df, pd.DataFrame) or len(df) < 2:
        raise ValueError("backtest requires at least two OHLC candles")
    missing = [name for name in _OHLC if name not in df.columns]
    if missing:
        raise ValueError(f"missing OHLC columns: {', '.join(missing)}")
    if not df.index.is_unique or not df.index.is_monotonic_increasing or df.index.hasnans:
        raise ValueError("candle index must be unique, non-null and increasing")
    try:
        prices = df.loc[:, list(_OHLC)].to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("OHLC prices must be numeric") from exc
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("OHLC prices must be finite and greater than zero")
    o, h, l, c = (prices[:, i] for i in range(4))
    if ((h < np.maximum.reduce([o, c, l])) | (l > np.minimum.reduce([o, c, h]))).any():
        raise ValueError("invalid OHLC candle: high/low do not contain open and close")
    if not isinstance(spec, dict) or not isinstance(spec.get("entry"), dict):
        raise ValueError("spec.entry rule is required")
    side = spec.get("side", "long")
    if side not in ("long", "short"):
        raise ValueError("side must be 'long' or 'short'")
    risk = spec.get("risk") or {}
    if not isinstance(risk, dict):
        raise ValueError("spec.risk must be an object")
    stop_pct = _finite_nonnegative(risk.get("stop_pct", 0), "risk.stop_pct")
    take_pct = _finite_nonnegative(risk.get("take_pct", 0), "risk.take_pct")
    if stop_pct >= 100:
        raise ValueError("risk.stop_pct must be below 100")
    if take_pct >= 100:
        raise ValueError("risk.take_pct must be below 100")
    cost_bps = _finite_nonnegative(cost_bps, "cost_bps")
    if cost_bps > 10000:
        raise ValueError("cost_bps must not exceed 10000")
    if isinstance(max_points, bool) or not isinstance(max_points, int) or max_points < 1:
        raise ValueError("max_points must be a positive integer")
    return prices, side, stop_pct / 100.0, take_pct / 100.0, cost_bps / 10000.0


def _intrabar_exit(side, open_price, high, low, stop_price, target_price):
    """Return (fill, reason); stop wins when both levels are touched."""
    if side == 1:
        stop_hit = stop_price is not None and (open_price <= stop_price or low <= stop_price)
        target_hit = target_price is not None and (open_price >= target_price or high >= target_price)
        if stop_hit:
            return (open_price if open_price <= stop_price else stop_price), "stop"
        if target_hit:
            return (open_price if open_price >= target_price else target_price), "target"
    else:
        stop_hit = stop_price is not None and (open_price >= stop_price or high >= stop_price)
        target_hit = target_price is not None and (open_price <= target_price or low <= target_price)
        if stop_hit:
            return (open_price if open_price >= stop_price else stop_price), "stop"
        if target_hit:
            return (open_price if open_price <= target_price else target_price), "target"
    return None, None


def run_backtest(df: pd.DataFrame, spec: dict, cost_bps: float = 5.0,
                 interval: str = "1d", max_points: int = 400) -> dict:
    """Replay one instrument using next-open fills, OHLC stops/targets and per-side costs.

    Equity assumes one-times notional exposure and compounds price returns. cost_bps
    is charged on each entry and exit notional. No partial fills, bid/ask spread,
    market impact, statutory fees, leverage/margin or multi-leg derivatives are modelled.
    """
    prices, side_name, stop_frac, take_frac, fee_rate = _validate_inputs(df, spec, cost_bps, max_points)
    opens, highs, lows, closes = (prices[:, i] for i in range(4))
    sign = 1 if side_name == "long" else -1
    entry_signal = eval_group(df, spec["entry"]).fillna(False).to_numpy(dtype=bool)
    exit_signal = (eval_group(df, spec["exit"]).fillna(False).to_numpy(dtype=bool)
                   if spec.get("exit") else np.zeros(len(df), dtype=bool))

    equity = 1.0
    equity_values = []
    trades = []
    position = None
    pending = None
    entry_armed = True
    exposure_bars = 0

    def apply_move(from_price, to_price, direction):
        nonlocal equity
        factor = 1.0 + direction * (to_price / from_price - 1.0)
        equity *= max(0.0, factor)

    def charge_fee():
        nonlocal equity
        equity *= max(0.0, 1.0 - fee_rate)

    def close_position(ts, fill, reason):
        nonlocal position
        if position is None:
            return
        apply_move(position["last_mark"], fill, position["side"])
        charge_fee()
        gross_pct = (fill / position["entry"] - 1.0) * position["side"] * 100.0
        net_pct = gross_pct - (2.0 * fee_rate * 100.0)
        trades.append({
            "side": "LONG" if position["side"] == 1 else "SHORT",
            "entry_time": position["entry_time"],
            "entry": round(float(position["entry"]), 8),
            "exit_time": str(ts),
            "exit": round(float(fill), 8),
            "pnl_pct": round(float(net_pct), 4),
            "exit_reason": reason,
        })
        position = None

    for i, ts in enumerate(df.index):
        open_price, high, low, close = opens[i], highs[i], lows[i], closes[i]

        if position is not None:
            apply_move(position["last_mark"], open_price, position["side"])
            position["last_mark"] = open_price

        if pending == "exit" and position is not None:
            close_position(ts, open_price, "signal")
        elif pending == "entry" and position is None:
            charge_fee()
            position = {
                "side": sign, "entry": float(open_price),
                "entry_time": str(ts), "last_mark": float(open_price),
                "stop": float(open_price * (1.0 - stop_frac if sign == 1 else 1.0 + stop_frac)) if stop_frac else None,
                "target": float(open_price * (1.0 + take_frac if sign == 1 else 1.0 - take_frac)) if take_frac else None,
            }
        pending = None

        was_exposed_this_bar = position is not None
        if position is not None:
            fill, reason = _intrabar_exit(position["side"], open_price, high, low,
                                          position["stop"], position["target"])
            if fill is not None:
                close_position(ts, float(fill), reason)
            else:
                apply_move(open_price, close, position["side"])
                position["last_mark"] = float(close)

        if was_exposed_this_bar:
            exposure_bars += 1
        equity_values.append(float(equity))

        if position is not None:
            if exit_signal[i]:
                pending = "exit"
        else:
            if not entry_signal[i]:
                entry_armed = True
            elif entry_armed and i < len(df) - 1:
                pending = "entry"
                entry_armed = False

    closed_count = len(trades)
    wins = [t["pnl_pct"] for t in trades if t["pnl_pct"] > 0]
    losses = [t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0]
    eq = pd.Series(equity_values, index=df.index, dtype=float)
    returns = eq.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    bpy = BARS_PER_YEAR.get(interval, 252)
    sd = float(returns.std())
    final = float(eq.iloc[-1]) if len(eq) else 1.0
    years = max(len(eq) / bpy, 1e-9)
    buy_hold = float((closes[-1] / closes[0] - 1.0) * 100.0)

    open_position = None
    if position is not None:
        unrealised = (closes[-1] / position["entry"] - 1.0) * position["side"] * 100.0
        open_position = {
            "side": "LONG" if position["side"] == 1 else "SHORT",
            "entry_time": position["entry_time"],
            "entry": round(float(position["entry"]), 8),
            "mark_time": str(df.index[-1]),
            "mark": round(float(closes[-1]), 8),
            "unrealised_pnl_pct": round(float(unrealised - fee_rate * 100.0), 4),
        }

    metrics = {
        "bars": len(df),
        "total_return_pct": round((final - 1.0) * 100.0, 2),
        "buy_hold_pct": round(buy_hold, 2),
        "cagr_pct": round((final ** (1.0 / years) - 1.0) * 100.0, 2) if final > 0 else -100.0,
        "sharpe": round(float(returns.mean() / sd * math.sqrt(bpy)) if sd > 0 else 0.0, 2),
        "max_drawdown_pct": round(float((eq / eq.cummax() - 1.0).min()) * 100.0, 2),
        "trades": closed_count,
        "win_rate_pct": round(100.0 * len(wins) / closed_count, 1) if closed_count else 0.0,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else None,
        "in_market_pct": round(100.0 * exposure_bars / len(df), 1),
        "cost_bps": float(cost_bps),
        "open_position": open_position,
    }
    step = max(1, math.ceil(len(eq) / max_points))
    indices = list(range(0, len(eq), step))
    if indices[-1] != len(eq) - 1:
        indices.append(len(eq) - 1)
    curve = [{"t": str(df.index[i]), "equity": round(float(eq.iloc[i]), 8), "close": round(float(closes[i]), 6)}
             for i in indices]
    return {"metrics": metrics, "equity": curve, "trades": trades[-200:],
            "open_position": open_position}

import numpy as np
import pandas as pd
from .rules import positions

BARS_PER_YEAR = {"1m": 75 * 250 * 5, "5m": 75 * 250, "15m": 25 * 250, "1h": 7 * 250, "1d": 252}


def run_backtest(df: pd.DataFrame, spec: dict, cost_bps: float = 5.0, interval: str = "1d", max_points: int = 400) -> dict:
    pos = positions(df, spec).shift(1).fillna(0)                      # decide at close, trade next bar: no lookahead
    ret = pos * df["close"].pct_change().fillna(0) - pos.diff().abs().fillna(0) * cost_bps / 1e4
    eq = (1 + ret).cumprod(); bpy = BARS_PER_YEAR.get(interval, 252); sd = ret.std()
    yrs = max(len(ret) / bpy, 1e-9)
    trades, cur = [], None
    for ts, p, px in zip(df.index, pos.values, df["close"].values):
        if cur is None and p != 0:
            cur = {"side": "LONG" if p > 0 else "SHORT", "entry_time": str(ts), "entry": float(px), "p": int(p)}
        elif cur is not None and p != cur["p"]:
            pnl = (px / cur["entry"] - 1) * cur["p"] * 100
            trades.append({**{k: v for k, v in cur.items() if k != "p"}, "exit_time": str(ts), "exit": float(px), "pnl_pct": round(float(pnl), 3)})
            cur = {"side": "LONG" if p > 0 else "SHORT", "entry_time": str(ts), "entry": float(px), "p": int(p)} if p != 0 else None
    wins = [t["pnl_pct"] for t in trades if t["pnl_pct"] > 0]; losses = [t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0]
    final = float(eq.iloc[-1]) if len(eq) else 1.0
    bh = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100 if len(df) > 1 else 0.0
    metrics = {
        "bars": len(df), "total_return_pct": round((final - 1) * 100, 2), "buy_hold_pct": round(bh, 2),
        "cagr_pct": round((final ** (1 / yrs) - 1) * 100, 2) if final > 0 else -100.0,
        "sharpe": round(float(ret.mean() / sd * np.sqrt(bpy)) if sd > 0 else 0.0, 2),
        "max_drawdown_pct": round(float((eq / eq.cummax() - 1).min()) * 100, 2),
        "trades": len(trades), "win_rate_pct": round(100 * len(wins) / len(trades), 1) if trades else 0.0,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else None,
        "in_market_pct": round(float((pos != 0).mean()) * 100, 1), "cost_bps": cost_bps,
    }
    step = max(1, len(eq) // max_points)
    curve = [{"t": str(t), "equity": round(float(v), 5), "close": round(float(c), 4)} for t, v, c in
             list(zip(df.index, eq.values, df["close"].values))[::step]]
    return {"metrics": metrics, "equity": curve, "trades": trades[-200:]}

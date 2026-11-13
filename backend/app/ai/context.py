"""Builds the facts the analyst sees. Everything here is computed by the platform from market data; nothing is free text from outside."""
import pandas as pd
from sqlalchemy import select
from .. import quotes
from ..brokers.factory import ensure_limits, ensure_paper_account, get_broker
from ..data import get_candles
from ..engine.rules import indicator
from ..models import Backtest, Strategy


def candle_facts(df: pd.DataFrame) -> dict:
    n = len(df); c = df["close"]; last = float(c.iloc[-1])
    def chg(k): return round((last / float(c.iloc[-1 - k]) - 1) * 100, 3) if n > k else None
    f = {"bars": n, "from": str(df.index[0]), "to": str(df.index[-1]), "last_close": round(last, 6),
         "change_pct": {"1_bar": chg(1), "5_bars": chg(5), "20_bars": chg(20), "whole_window": chg(n - 1)}}
    ema = {p: float(indicator(df, "ema", p).iloc[-1]) for p in (9, 21, 50) if n >= p}
    f["ema"] = {str(p): round(v, 6) for p, v in ema.items()}
    f["rsi14"] = round(float(indicator(df, "rsi", 14).iloc[-1]), 1) if n >= 15 else None
    atr = float(indicator(df, "atr", 14).iloc[-1]); f["atr14"] = round(atr, 6); f["atr14_pct_of_price"] = round(atr / last * 100, 3)
    hi, lo = float(df["high"].tail(20).max()), float(df["low"].tail(20).min())
    f["range_20_bars"] = {"high": round(hi, 6), "low": round(lo, 6), "price_below_high_pct": round((1 - last / hi) * 100, 3), "price_above_low_pct": round((last / lo - 1) * 100, 3)}
    rets = c.pct_change().dropna().tail(50); f["volatility_pct_per_bar_50"] = round(float(rets.std()) * 100, 4) if len(rets) > 5 else None
    if set(ema) == {9, 21, 50}:
        f["trend"] = "uptrend (EMA 9 > 21 > 50)" if ema[9] > ema[21] > ema[50] else "downtrend (EMA 9 < 21 < 50)" if ema[9] < ema[21] < ema[50] else "mixed or sideways"
    elif set(ema) == {9, 21}:       # fewer than 50 candles: judge on the two faster averages and say so
        f["trend"] = "short-term uptrend (EMA 9 > 21; under 50 candles, so EMA 50 is not available)" if ema[9] > ema[21] else "short-term downtrend (EMA 9 < 21; under 50 candles, so EMA 50 is not available)"
    else:
        f["trend"] = "not enough data"
    v = df["volume"] if "volume" in df else None
    if v is not None and len(v) >= 25 and float(v.tail(25).sum()) > 0:
        f["volume_last5_vs_prior20"] = round(float(v.tail(5).mean()) / max(float(v.iloc[-25:-5].mean()), 1e-12), 2)
    return f


def load_candles(db, user, symbol, exchange, interval, bars=300):
    """Best real data first. CRYPTO: ticks recorded from the live feed, then the exchange's public candles, then synthetic demo data (flagged)."""
    tries = [("recorded", None), ("crypto", None)] if exchange == "CRYPTO" else [None]
    for t in tries:
        if t is None:
            continue
        try:
            df = get_candles(symbol, exchange, interval, bars, t[0], db=db)
            if len(df) >= 30: return df, t[0]
        except Exception:
            continue
    return get_candles(symbol, exchange, interval, bars, "demo"), "demo"


def portfolio_context(db, user) -> dict:
    """Only sent to the AI provider if the user explicitly opts in."""
    acct = ensure_paper_account(db, user); b = get_broker(db, acct); lim = ensure_limits(db, user.id)
    strategies = db.scalars(select(Strategy).where(Strategy.user_id == user.id).order_by(Strategy.id.desc()).limit(8)).all()
    tests = db.scalars(select(Backtest).where(Backtest.user_id == user.id).order_by(Backtest.id.desc()).limit(5)).all()
    return {"paper_positions": [{k: p[k] for k in ("symbol", "qty", "avg_price", "ltp", "pnl")} for p in b.positions()][:10], "paper_funds": b.funds(),
            "strategies": [{"name": s.name, "mode": s.mode, "symbol": s.spec.get("symbol"), "interval": s.spec.get("interval")} for s in strategies],
            "recent_backtests": [{"name": t.name, **{k: t.metrics.get(k) for k in ("total_return_pct", "buy_hold_pct", "max_drawdown_pct", "sharpe", "trades", "data_source")}} for t in tests],
            "risk": {"kill_switch": lim.kill_switch, "max_daily_loss": lim.max_daily_loss, "max_order_value": lim.max_order_value}}


def build_context(db, user, symbol, exchange, interval, include_portfolio=False) -> dict:
    df, src = load_candles(db, user, symbol, exchange, interval)
    ctx = {"instrument": {"symbol": symbol, "exchange": exchange, "candle_interval": interval}, "data_source": src,
           "data_is_synthetic": src == "demo", "facts": candle_facts(df)}
    live = quotes.get_last(symbol)
    if live: ctx["live_price_from_feed"] = live
    if include_portfolio: ctx["portfolio"] = portfolio_context(db, user)
    return ctx

"""Simple vectorised backtester. Trades on the NEXT bar after a signal (no lookahead).
Usage:
  python backtest.py --demo --strategy ema_crossover
  python backtest.py --csv data.csv --strategy opening_range_breakout
  python backtest.py --openalgo RELIANCE NSE 5m 2025-01-01 2025-06-30 --strategy ema_crossover
"""
import argparse, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "strategies"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data"))
from signals import REGISTRY


def demo_data(days=60, bars=75, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.concat([pd.Series(pd.date_range(f"2025-01-01 09:15", periods=bars, freq="5min") + pd.Timedelta(days=d))
                     for d in range(days)])
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, len(idx))))
    df = pd.DataFrame({"close": close}, index=pd.DatetimeIndex(idx))
    df["open"] = df["close"].shift(1).fillna(df["close"])
    df["high"] = df[["open", "close"]].max(axis=1) * 1.0005
    df["low"] = df[["open", "close"]].min(axis=1) * 0.9995
    return df


def load(args):
    if args.demo:
        return demo_data()
    if args.csv:
        df = pd.read_csv(args.csv, parse_dates=[0], index_col=0)
        df.columns = [c.lower() for c in df.columns]
        return df
    if args.crypto:
        from crypto_feed import history
        ex, sym, tf, n = args.crypto
        return history(sym, tf, int(n), __import__("crypto_feed").get_exchange(ex))
    from openalgo import api
    sym, exch, interval, start, end = args.openalgo
    client = api(api_key=os.environ["OPENALGO_API_KEY"], host=os.environ.get("HOST_SERVER") or os.environ.get("OPENALGO_HOST", "http://127.0.0.1:5000"))
    return client.history(symbol=sym, exchange=exch, interval=interval, start_date=start, end_date=end)


def run(df, name, cost_bps=2.0):
    pos = REGISTRY[name](df).shift(1).fillna(0)
    ret = pos * df["close"].pct_change().fillna(0) - pos.diff().abs().fillna(0) * cost_bps / 1e4
    eq = (1 + ret).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    trades = int((pos.diff().abs() > 0).sum())
    return {"strategy": name, "bars": len(df), "position_changes": trades,
            "total_return_%": round((eq.iloc[-1] - 1) * 100, 2), "max_drawdown_%": round(dd * 100, 2),
            "bars_in_market_%": round((pos != 0).mean() * 100, 1)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", required=True, choices=REGISTRY)
    p.add_argument("--cost-bps", type=float, default=2.0)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--demo", action="store_true")
    g.add_argument("--csv")
    g.add_argument("--crypto", nargs=4, metavar=("EXCHANGE", "SYMBOL", "TIMEFRAME", "CANDLES"), help="e.g. coinbase BTC/USD 5m 300")
    g.add_argument("--openalgo", nargs=5, metavar=("SYMBOL", "EXCHANGE", "INTERVAL", "START", "END"))
    a = p.parse_args()
    for k, v in run(load(a), a.strategy, a.cost_bps).items():
        print(f"{k:>20}: {v}")
    print("\nBacktests are not predictions. Demo data is random.")

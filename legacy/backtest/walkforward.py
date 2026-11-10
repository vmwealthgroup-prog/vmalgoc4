"""Walk-forward test on REAL data. Picks parameters on the first part of history (in-sample), then reports how they did on
the later part they never saw (out-of-sample), next to buy & hold. A big gap between the two means overfit.
  pip install pandas numpy yfinance ccxt
  python walkforward.py --yf ^NSEI --period 10y                 Nifty daily
  python walkforward.py --yf ^NSEBANK --period 10y              BankNifty daily
  python walkforward.py --yf ^NSEBANK --period 55d --interval 5m   intraday (Yahoo limits 5m to ~60 days)
  python walkforward.py --crypto coinbase BTC/USD 1d 1000       crypto daily
  python walkforward.py --csv data.csv   |   --demo
Opening-range breakout needs intraday bars and is skipped on daily data."""
import argparse, itertools, os, sys
import numpy as np, pandas as pd
here = os.path.dirname(os.path.abspath(__file__))
for d in ("strategies", "data", "backtest"): sys.path.insert(0, os.path.join(here, "..", d))
from signals import REGISTRY

GRID = {"ema_crossover": {"fast": [5, 9, 13], "slow": [21, 34, 55]},
        "rsi_mean_reversion": {"period": [7, 14], "buy_below": [25, 30, 35], "exit_above": [50, 55, 60]},
        "opening_range_breakout": {"range_bars": [2, 3, 6]}}


def simulate(df, name, params, cost_bps):
    pos = REGISTRY[name](df, **params).shift(1).fillna(0)
    ret = pos * df["close"].pct_change().fillna(0) - pos.diff().abs().fillna(0) * cost_bps / 1e4
    return ret, pos


def stats(ret, pos, bpy):
    eq = (1 + ret).cumprod(); yrs = max(len(ret) / bpy, 1e-9); sd = ret.std()
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1.0
    return {"cagr_%": round(cagr * 100, 1), "sharpe": round(float(ret.mean() / sd * np.sqrt(bpy)) if sd > 0 else 0, 2),
            "maxdd_%": round((eq / eq.cummax() - 1).min() * 100, 1), "pos_changes": int((pos.diff().abs() > 0).sum()),
            "in_market_%": round((pos != 0).mean() * 100, 0)}


def load(a):
    if a.demo:
        from backtest import demo_data; return demo_data(days=120)
    if a.csv:
        df = pd.read_csv(a.csv, parse_dates=[0], index_col=0); df.columns = [c.lower() for c in df.columns]; return df
    if a.crypto:
        from crypto_feed import history, get_exchange; ex, s, tf, n = a.crypto; return history(s, tf, int(n), get_exchange(ex))
    import yfinance as yf
    df = yf.download(a.yf, period=a.period, interval=a.interval, auto_adjust=True, progress=False)
    df.columns = [(c[0] if isinstance(c, tuple) else c).lower() for c in df.columns]
    return df.dropna()


if __name__ == "__main__":
    p = argparse.ArgumentParser(); g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--demo", action="store_true"); g.add_argument("--csv"); g.add_argument("--yf")
    g.add_argument("--crypto", nargs=4, metavar=("EXCHANGE", "SYMBOL", "TIMEFRAME", "CANDLES"))
    p.add_argument("--period", default="10y"); p.add_argument("--interval", default="1d")
    p.add_argument("--split", type=float, default=0.6, help="fraction used for tuning"); p.add_argument("--cost-bps", type=float, default=5.0)
    p.add_argument("--bars-per-year", type=float); p.add_argument("--min-changes", type=int, default=10)
    a = p.parse_args(); df = load(a)
    intraday = df.index.normalize().nunique() < len(df) * 0.9
    bpy = a.bars_per_year or (75 * 250 if intraday else 252)
    cut = int(len(df) * a.split); ins, oos = df.iloc[:cut], df.iloc[cut:]
    print(f"{len(df)} bars ({'intraday' if intraday else 'daily'}), tune on first {len(ins)}, test on last {len(oos)}, cost {a.cost_bps} bps per position change\n")
    rows = []
    for name, grid in GRID.items():
        if name == "opening_range_breakout" and not intraday: continue
        best = None
        for vals in itertools.product(*grid.values()):
            prm = dict(zip(grid, vals))
            if "fast" in prm and prm["fast"] >= prm["slow"]: continue
            r, ps = simulate(ins, name, prm, a.cost_bps); s = stats(r, ps, bpy)
            if s["pos_changes"] < a.min_changes: continue
            if best is None or s["sharpe"] > best[0]["sharpe"]: best = (s, prm)
        if best is None: print(f"{name}: too few trades in-sample for any setting"); continue
        r, ps = simulate(oos, name, best[1], a.cost_bps); o = stats(r, ps, bpy)
        rows.append({"strategy": name, "params": str(best[1]), "IS_sharpe": best[0]["sharpe"], "OOS_sharpe": o["sharpe"],
                     "OOS_cagr_%": o["cagr_%"], "OOS_maxdd_%": o["maxdd_%"], "OOS_changes": o["pos_changes"]})
    bh = stats(oos["close"].pct_change().fillna(0), pd.Series(1, index=oos.index), bpy)
    rows.append({"strategy": "BUY&HOLD", "params": "-", "IS_sharpe": stats(ins["close"].pct_change().fillna(0), pd.Series(1, index=ins.index), bpy)["sharpe"],
                 "OOS_sharpe": bh["sharpe"], "OOS_cagr_%": bh["cagr_%"], "OOS_maxdd_%": bh["maxdd_%"], "OOS_changes": 0})
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nRead it: OOS_sharpe is what counts. A strategy that beats BUY&HOLD out-of-sample after costs, with OOS_sharpe close to IS_sharpe,")
    print("and enough changes to mean something, is worth paper trading. Otherwise it is noise. One test on one instrument proves little.")

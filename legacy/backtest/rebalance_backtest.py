"""Compare buy&hold, calendar rebalancing and band rebalancing on a basket. Close prices only.
  python rebalance_backtest.py --demo
  python rebalance_backtest.py --csv closes.csv --weights NIFTYBEES=60,GOLDBEES=25,BTC=15 --band 5
CSV: date index, one column of closes per asset."""
import argparse, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "strategies"))
from sizing import cap_weights


def simulate(px, w, mode, band=5.0, every=21, cost_bps=10.0):
    r = px.pct_change().fillna(0).values; w = np.array([w[c] for c in px.columns]); h = w.copy(); v = 1.0; traded = 0.0; n = 0
    for i in range(len(px)):
        h = h * (1 + r[i]); v = h.sum(); cur = h / v
        go = (mode == "calendar" and i % every == 0 and i > 0) or (mode == "band" and np.abs(cur - w).max() * 100 > band)
        if go:
            t = np.abs(w * v - h).sum(); traded += t; n += 1; v -= t * cost_bps / 1e4; h = w * v
    return {"mode": mode, "final_value": round(float(v), 4), "rebalances": n, "turnover_x": round(float(traded), 2)}


if __name__ == "__main__":
    p = argparse.ArgumentParser(); g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--demo", action="store_true"); g.add_argument("--csv")
    p.add_argument("--weights"); p.add_argument("--band", type=float, default=5.0); p.add_argument("--cap", type=float, default=100.0)
    a = p.parse_args()
    if a.demo:
        rng = np.random.default_rng(3); z = rng.normal(0, 1, (750, 3)); vol = np.array([.009, .006, .03]); drift = np.array([.0004, .0002, .0006])
        px = pd.DataFrame(100 * np.exp(np.cumsum(drift + z * vol, axis=0)), columns=["EQUITY", "GOLD", "CRYPTO"]); wts = {"EQUITY": 60, "GOLD": 25, "CRYPTO": 15}
    else:
        px = pd.read_csv(a.csv, index_col=0, parse_dates=True); wts = {k: float(v) for k, v in (x.split("=") for x in a.weights.split(","))}
    w = cap_weights(wts, a.cap)
    for m in ("hold", "calendar", "band"):
        print(simulate(px, w, m, a.band))
    print("Illustrative only. Demo data is random; costs 10 bps of traded value.")

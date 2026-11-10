"""Checks js/btc-lib.js against strategies/signals.py + sizing.py on the same random candles. Needs node."""
import json, os, subprocess, sys
import numpy as np, pandas as pd
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(root, "strategies")); from signals import ema_crossover, rsi_mean_reversion; from sizing import atr, atr_qty
rng = np.random.default_rng(5); c = 100 * np.exp(np.cumsum(rng.normal(0, .01, 400))); h = c * (1 + rng.random(400) * .01); l = c * (1 - rng.random(400) * .01)
df = pd.DataFrame({"high": h, "low": l, "close": c})
d = json.dumps({"h": h.tolist(), "l": l.tolist(), "c": c.tolist()})
js = "const B=require('./js/btc-lib.js');const d=JSON.parse(process.argv[1]);console.log(JSON.stringify({e:B.emaSignal(d.c),r:B.rsiSignal(d.c),rsi:B.rsi(d.c),a:B.atr(d.h,d.l,d.c),q:B.size(10000,.5,2,100,2,100).qty}))"
o = json.loads(subprocess.run(["node", "-e", js, d], cwd=root, capture_output=True, text=True, check=True).stdout)
ok = (np.array(o["e"]) == ema_crossover(df).values).all() and (np.array(o["r"]) == rsi_mean_reversion(df).values).all()
rs = pd.Series(c).diff(); g = rs.clip(lower=0).ewm(alpha=1/14, adjust=False).mean(); lo_ = (-rs.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
rsi_py = (100 - 100 / (1 + g / lo_.replace(0, 1e-12))).values
print("ema signals match:", (np.array(o["e"]) == ema_crossover(df).values).all())
print("rsi signals match:", (np.array(o["r"]) == rsi_mean_reversion(df).values).all())
print("rsi values max diff:", float(np.nanmax(np.abs(np.array(o["rsi"], dtype=float) - rsi_py))))
print("atr max diff:", float(np.max(np.abs(np.array(o["a"]) - atr(df).values))))
print("size qty js vs py:", o["q"], atr_qty(10000, .5, 2, 2))

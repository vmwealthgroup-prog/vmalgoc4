import os, sys, time, unittest, tempfile
for d in ("risk", "strategies"): sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", d))
import pandas as pd
from risk_gate import RiskGate, Limits
from sizing import cap_weights, rebalance_trades, atr_qty, atr
from signals import REGISTRY

NOON = time.mktime(time.strptime("2026-10-28 11:00", "%Y-%m-%d %H:%M"))


class Gate(unittest.TestCase):
    def g(self, **k): return RiskGate(Limits(kill_file="/nonexistent/KILL", **k))
    def test_pass(self): self.assertTrue(self.g().check("X", "BUY", 1, 100, NOON)[0])
    def test_malformed(self): self.assertFalse(self.g().check("X", "HOLD", 1, 100, NOON)[0]); self.assertFalse(self.g().check("X", "BUY", 0, 100, NOON)[0])
    def test_blocked(self): self.assertFalse(self.g(blocked=("X",)).check("X", "BUY", 1, 100, NOON)[0])
    def test_window(self): self.assertFalse(self.g().check("X", "BUY", 1, 100, NOON + 6 * 3600)[0])
    def test_qty_value(self):
        self.assertFalse(self.g(max_qty=5).check("X", "BUY", 6, 1, NOON)[0]); self.assertFalse(self.g(max_order_value=500).check("X", "BUY", 6, 100, NOON)[0])
    def test_short(self): self.assertFalse(self.g().check("X", "SELL", 1, 100, NOON)[0]); self.assertTrue(self.g(allow_short=True).check("X", "SELL", 1, 100, NOON)[0])
    def test_position_as_if_filled(self):
        g = self.g(max_position_value=1000); g.record("X", "BUY", 8, NOON); self.assertFalse(g.check("X", "BUY", 5, 100, NOON + 600)[0])
    def test_duplicate_and_daily(self):
        g = self.g(max_orders_per_day=1, cooldown_s=60); g.record("X", "BUY", 1, NOON); self.assertFalse(g.check("Y", "BUY", 1, 10, NOON + 1)[0])
        h = self.g(); h.record("X", "BUY", 1, NOON); self.assertFalse(h.check("X", "BUY", 1, 10, NOON + 5)[0]); self.assertTrue(h.check("X", "BUY", 1, 10, NOON + 120)[0])
    def test_loss_limit(self): g = self.g(max_daily_loss=100); g.add_pnl(-150); self.assertFalse(g.check("X", "BUY", 1, 10, NOON)[0])
    def test_kill_switch(self):
        with tempfile.NamedTemporaryFile() as f: self.assertFalse(RiskGate(Limits(kill_file=f.name)).check("X", "BUY", 1, 10, NOON)[0])


class Sizing(unittest.TestCase):
    def test_cap(self):
        w = cap_weights({"A": 60, "B": 25, "C": 15}, 40); self.assertAlmostEqual(sum(w.values()), 1); self.assertAlmostEqual(w["A"], .4); self.assertAlmostEqual(w["B"] / w["C"], 25 / 15)
        with self.assertRaises(ValueError): cap_weights({"A": 1, "B": 1}, 40)
    def test_atr_qty(self): self.assertEqual(atr_qty(100000, 1, 10, 2, lot=25), 50); self.assertEqual(atr_qty(100000, 1, 0), 0)
    def test_rebalance_band(self):
        self.assertEqual(rebalance_trades({"A": 50, "B": 50}, {"A": 50, "B": 50}), [])
        t = rebalance_trades({"A": 70, "B": 30}, {"A": 50, "B": 50}, band_pts=5); self.assertEqual([x[:2] for x in t], [("A", "SELL"), ("B", "BUY")]); self.assertAlmostEqual(t[0][2], 20)
    def test_rebalance_cash_short(self):
        t = rebalance_trades({"A": 40, "B": 40}, {"A": 50, "B": 50}, cash=20, band_pts=5, buffer_pct=20); self.assertTrue(all(x[2] <= 20 for x in t))
    def test_atr_series(self):
        df = pd.DataFrame({"high": [2, 3, 4], "low": [1, 2, 3], "close": [1.5, 2.5, 3.5]}); self.assertEqual(len(atr(df)), 3)
    def test_signals_still_work(self):
        idx = pd.date_range("2026-01-01", periods=50, freq="D"); c = pd.Series(range(50), index=idx, dtype=float) + 100
        df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c}); self.assertEqual(int(REGISTRY["ema_crossover"](df).iloc[-1]), 1)


if __name__ == "__main__": unittest.main()

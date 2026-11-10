// Indicator math, mirrors strategies/signals.py and strategies/sizing.py (pandas ewm adjust=False semantics).
const BTC = {
  ewm(a, k, from = 0) { const o = new Array(a.length).fill(NaN); o[from] = a[from]; for (let i = from + 1; i < a.length; i++) o[i] = a[i] * k + o[i - 1] * (1 - k); return o; },
  ema(a, n) { return BTC.ewm(a, 2 / (n + 1)); },
  rsi(c, n = 14) {
    const g = c.map((v, i) => i ? Math.max(v - c[i - 1], 0) : NaN), l = c.map((v, i) => i ? Math.max(c[i - 1] - v, 0) : NaN);
    const ag = BTC.ewm(g, 1 / n, 1), al = BTC.ewm(l, 1 / n, 1);
    return ag.map((v, i) => 100 - 100 / (1 + v / (al[i] === 0 ? 1e-12 : al[i])));
  },
  atr(h, l, c, n = 14) {
    const tr = c.map((_, i) => i ? Math.max(h[i] - l[i], Math.abs(h[i] - c[i - 1]), Math.abs(l[i] - c[i - 1])) : h[i] - l[i]);
    return BTC.ewm(tr, 1 / n);
  },
  emaSignal(c, fast = 9, slow = 21) { const f = BTC.ema(c, fast), s = BTC.ema(c, slow); return c.map((_, i) => +(f[i] > s[i])); },
  rsiSignal(c, n = 14, buy = 30, exit = 55) { let st = 0; return BTC.rsi(c, n).map(v => (st === 0 && v < buy ? st = 1 : st === 1 && v > exit ? st = 0 : 0, st)); },
  // quantity so a stop `mult` ATRs away risks riskPct % of equity; capped at maxPct % of equity in notional
  size(equity, riskPct, atrV, price, mult = 2, maxPct = 100) {
    const perUnit = atrV * mult; if (!(perUnit > 0) || !(price > 0)) return { qty: 0, notional: 0, stop: NaN, capped: false };
    let qty = equity * riskPct / 100 / perUnit, capped = false;
    const maxQty = equity * maxPct / 100 / price; if (qty > maxQty) { qty = maxQty; capped = true; }
    return { qty, notional: qty * price, stop: price - perUnit, capped };
  }
};
if (typeof module !== 'undefined') module.exports = BTC;

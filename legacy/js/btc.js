// BTC page: public Coinbase data only (no keys in the browser). Signals are informational / paper only.
const $ = id => document.getElementById(id), fmt = (v, d = 2) => (+v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
let candles = [], last = null;
function connect() {
  const ws = new WebSocket('wss://advanced-trade-ws.coinbase.com');
  ws.onopen = () => { ws.send(JSON.stringify({ type: 'subscribe', product_ids: ['BTC-USD'], channel: 'ticker' })); $('wstat').textContent = 'Live'; };
  ws.onmessage = e => { try { const m = JSON.parse(e.data); if (m.channel !== 'ticker') return;
    for (const ev of m.events || []) for (const t of ev.tickers || []) { const p = +t.price; $('px').textContent = fmt(p);
      if (last !== null) $('px').className = p >= last ? 'up' : 'dn'; last = p; $('bid').textContent = fmt(t.best_bid); $('ask').textContent = fmt(t.best_ask); } } catch (_) {} };
  ws.onclose = () => { $('wstat').textContent = 'Disconnected, retrying…'; setTimeout(connect, 5000); }; ws.onerror = () => ws.close();
}
async function load() {
  const g = $('tf').value;
  try {
    const r = await fetch(`https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=${g}`); if (!r.ok) throw new Error(r.status);
    candles = (await r.json()).map(([t, lo, hi, o, c, v]) => ({ t, lo, hi, o, c, v })).sort((a, b) => a.t - b.t); $('cstat').textContent = `${candles.length} candles`;
    draw(); signals(); sizer();
  } catch (e) { $('cstat').textContent = 'Candles unavailable (network or CORS blocked)'; }
}
function draw() {
  const W = 900, H = 320, P = 40, d = candles.slice(-100); if (!d.length) return;
  const hi = Math.max(...d.map(x => x.hi)), lo = Math.min(...d.map(x => x.lo)), y = v => P / 2 + (hi - v) / (hi - lo || 1) * (H - P), cw = (W - P) / d.length;
  const x = i => P + i * cw + cw / 2, all = candles.map(x => x.c), f = BTC.ema(all, 9).slice(-100), s = BTC.ema(all, 21).slice(-100);
  const line = (a, col) => `<polyline fill="none" stroke="${col}" stroke-width="1.5" points="${a.map((v, i) => x(i) + ',' + y(v)).join(' ')}"/>`;
  let g = ''; for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4; g += `<line x1="${P}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="#dde3ec"/><text x="2" y="${y(v) + 4}" font-size="11" fill="#51627a">${fmt(v, 0)}</text>`; }
  const cs = d.map((c, i) => { const col = c.c >= c.o ? '#0e7c5a' : '#c8372d'; return `<line x1="${x(i)}" x2="${x(i)}" y1="${y(c.hi)}" y2="${y(c.lo)}" stroke="${col}"/><rect x="${x(i) - cw * .35}" y="${y(Math.max(c.o, c.c))}" width="${cw * .7}" height="${Math.max(1, Math.abs(y(c.o) - y(c.c)))}" fill="${col}"/>`; }).join('');
  $('chart').innerHTML = g + cs + line(f, '#f2a900') + line(s, '#10223b');
}
function signals() {
  const c = candles.map(x => x.c), i = c.length - 2; if (i < 30) return;       // last COMPLETED candle
  const e = BTC.emaSignal(c)[i], r = BTC.rsiSignal(c)[i], rv = BTC.rsi(c)[i];
  $('sig').innerHTML = `<div class="row"><span>EMA 9/21 crossover</span><b class="${e ? 'up' : ''}">${e ? 'LONG' : 'FLAT'}</b></div><div class="row"><span>RSI mean reversion (RSI ${rv.toFixed(1)})</span><b class="${r ? 'up' : ''}">${r ? 'LONG' : 'FLAT'}</b></div>`;
}
function sizer() {
  if (candles.length < 30 || last === null && !candles.length) return;
  const h = candles.map(x => x.hi), l = candles.map(x => x.lo), c = candles.map(x => x.c), a = BTC.atr(h, l, c)[c.length - 2], px = last || c[c.length - 1];
  const r = BTC.size(+$('eq').value, +$('rk').value, a, px, +$('mu').value, +$('mx').value);
  $('out').innerHTML = `<div class="row"><span>ATR (14)</span><b>${fmt(a)}</b></div><div class="row"><span>Quantity</span><b>${r.qty.toFixed(5)} BTC${r.capped ? ' (capped)' : ''}</b></div><div class="row"><span>Notional</span><b>$${fmt(r.notional)}</b></div><div class="row"><span>Stop (long)</span><b>$${fmt(r.stop)}</b></div>`;
}
['eq', 'rk', 'mu', 'mx'].forEach(id => $(id).addEventListener('input', sizer)); $('tf').addEventListener('change', load);
connect(); load(); setInterval(load, 30000); setInterval(sizer, 5000);

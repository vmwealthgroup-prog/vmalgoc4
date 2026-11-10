"""Tick feeder: publishes prices to pub/sub and the shared last-price cache. Sources: demo | openalgo | crypto."""
import asyncio, json, random, time
from .config import get_settings
from .data import demo_candles
from . import quotes
from .candles import CandleBuilder, save_candles
from .feeds.coinbase import CoinbaseFeed


def parse_symbols(s: str):
    out = []
    for part in s.split(","):
        part = part.strip()
        if part:
            sym, _, ex = part.partition(":"); out.append((sym, ex or "NSE"))
    return out


class Feeder:
    """Publishes prices to pub/sub and the last-price cache.
    - CRYPTO symbols with CRYPTO_FEED=coinbase: REAL ticks from Coinbase's public WebSocket (every trade becomes part of a 1-minute candle that is recorded)
    - other symbols: demo (synthetic) or OpenAlgo quotes, polled"""
    def __init__(self, pubsub, symbols=None, source=None, interval=1.0, crypto_feed=None, ws_connect=None):
        s = get_settings(); self.ps, self.interval = pubsub, interval
        every = symbols or parse_symbols(s.feed_symbols); self.source = source or s.feed_source; self.crypto_feed = crypto_feed or s.crypto_feed
        self.ws_symbols = [sym for sym, ex in every if ex == "CRYPTO"] if self.crypto_feed == "coinbase" else []
        self.symbols = [(sym, ex) for sym, ex in every if sym not in self.ws_symbols]
        self.px = {sym: float(demo_candles(sym, "5m", 5)["close"].iloc[-1]) for sym, _ in self.symbols}
        self._stop = False; self.builder = CandleBuilder(); self.book: dict = {}; self._last_pub: dict = {}; self._pending: dict = {}; self._last_beat = 0.0; self._ws_connect = ws_connect; self.cb = None

    @staticmethod
    def _beat():
        from .db import SessionLocal
        from .heartbeat import beat
        with SessionLocal() as db: beat(db, "feed")

    def stop(self):
        self._stop = True
        if self.cb: self.cb.stop()

    def _fetch(self):
        s = get_settings(); out = {}
        if self.source == "openalgo" and s.openalgo_api_key:
            from openalgo import api
            c = api(api_key=s.openalgo_api_key, host=s.openalgo_host)
            for sym, ex in self.symbols:
                if ex != "CRYPTO":
                    try:
                        d = c.quotes(symbol=sym, exchange=ex).get("data", {}); out[sym] = float(d["ltp"])
                    except Exception:
                        pass
        if self.source == "crypto" or any(ex == "CRYPTO" for _, ex in self.symbols) and self.source != "demo":
            import ccxt
            ex_ = getattr(ccxt, s.crypto_exchange)({"enableRateLimit": True})
            for sym, ex in self.symbols:
                if ex == "CRYPTO":
                    try: out[sym] = float(ex_.fetch_ticker(sym)["last"])
                    except Exception: pass
        return out

    def _demo(self):
        return {sym: self.px[sym] * (1 + random.gauss(0, 0.0004)) for sym, _ in self.symbols}

    async def tick(self):
        prices = await asyncio.to_thread(self._fetch) if self.source != "demo" else {}
        for sym, ex in self.symbols:
            p = prices.get(sym) or (self._demo()[sym] if self.source == "demo" else None)
            if p is None: continue
            p = round(p, 4); self.px[sym] = p; quotes.set_last(sym, p)
            await self.ps.publish("ticks", {"type": "tick", "symbol": sym, "exchange": ex, "ltp": p, "ts": time.time(), "src": "demo" if self.source == "demo" else self.source})

    async def _poll_loop(self):
        n = 0
        while not self._stop:
            try:
                await self.tick(); n += 1
                if n % 10 == 1: await asyncio.to_thread(self._beat)
            except Exception:
                pass
            await asyncio.sleep(self.interval if self.source == "demo" else max(self.interval, 3))

    # ---- real ticks from Coinbase
    async def _publish(self, sym, price, **extra):
        """The last-price cache is updated on EVERY trade. Publishing to browsers is limited to 4/s per symbol; a tick held back by the limit is sent as soon as the window ends,
        so the newest price of a burst is never lost."""
        price = round(price, 8); quotes.set_last(sym, price)
        self._pending[sym] = (price, extra)
        if time.monotonic() - self._last_pub.get(sym, 0) >= 0.25: await self._send(sym)

    async def _send(self, sym):
        price, extra = self._pending.pop(sym)
        self._last_pub[sym] = time.monotonic(); b = self.book.get(sym, {})
        await self.ps.publish("ticks", {"type": "tick", "symbol": sym, "exchange": "CRYPTO", "ltp": price, "ts": time.time(), "src": "coinbase", "bid": b.get("bid"), "ask": b.get("ask"), **extra})

    async def _flush_loop(self):
        while not self._stop:
            await asyncio.sleep(0.1)
            for sym in list(self._pending):
                if time.monotonic() - self._last_pub.get(sym, 0) >= 0.25: await self._send(sym)

    async def _on_trade(self, t):
        done = self.builder.add(t["symbol"], t["price"], t["size"], t["ts"])
        if done: await asyncio.to_thread(self._save, done)
        if not t["snapshot"]: await self._publish(t["symbol"], t["price"], size=t["size"], side=t["side"])
        else: quotes.set_last(t["symbol"], t["price"])

    async def _on_ticker(self, t):
        self.book[t["symbol"]] = {"bid": t["bid"], "ask": t["ask"]}
        await self._publish(t["symbol"], t["price"], vol24h=t["vol24h"])

    @staticmethod
    def _save(candles):
        from .db import SessionLocal
        with SessionLocal() as db: save_candles(db, candles)

    def _write_stats(self):
        from .db import SessionLocal
        from .heartbeat import beat, put
        st = self.cb.stats
        with SessionLocal() as db:
            put(db, "feedstats", json.dumps({"connected": st["connected"], "messages": st["messages"], "trades": st["trades"], "gaps": st["gaps"], "reconnects": st["reconnects"], "err": st["last_error"][:60]}))
            if st["connected"]: beat(db, "feed")                              # only a LIVE connection counts as a heartbeat: a dead feed must show as a problem

    async def _on_message(self, _msg):
        now = time.monotonic()
        if self._last_beat == 0: self._last_beat = now - 4              # first write ~1 s after the first message, so the health card never shows an empty start
        if now - self._last_beat >= 5:
            self._last_beat = now; await asyncio.to_thread(self._write_stats)

    async def _coinbase(self):
        s = get_settings()
        self.cb = CoinbaseFeed(self.ws_symbols, self._on_trade, self._on_ticker, self._on_message, url=s.coinbase_ws_url, connect=self._ws_connect)
        try:
            await self.cb.run()
        finally:
            await asyncio.to_thread(self._write_stats)                          # final, accurate state (connected=False)
            done = self.builder.flush()
            if done: await asyncio.to_thread(self._save, done)

    async def run(self):
        jobs = []
        if self.symbols: jobs.append(self._poll_loop())
        if self.ws_symbols: jobs.extend([self._coinbase(), self._flush_loop()])
        # return_exceptions=True makes this wait for every job's cleanup (flush the last candle, write final stats) before it returns, even when cancelled
        for r in await asyncio.gather(*jobs, return_exceptions=True):
            if isinstance(r, BaseException) and not isinstance(r, asyncio.CancelledError): raise r

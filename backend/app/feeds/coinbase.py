"""Real tick data from Coinbase's PUBLIC Advanced Trade WebSocket (no API key). Built to the documented protocol:
  endpoint  wss://advanced-trade-ws.coinbase.com
  subscribe one message PER channel, within 5 s of connecting:  {"type":"subscribe","product_ids":[...],"channel":"market_trades"}
  channels  market_trades (every trade, batched per 250 ms), ticker (last price + best bid/ask), heartbeats (keeps idle channels open)
  messages  {"channel":"market_trades","timestamp":..,"sequence_num":..,"events":[{"type":"snapshot|update","trades":[{trade_id,product_id,price,size,side,time}]}]}
Trade `side` in the feed is the MAKER's side, so the taker (aggressor) side reported here is the opposite.
Clients must ignore message types they do not know. A silent connection is treated as dead and re-opened with backoff."""
import asyncio, json, random, re, time
from collections import deque
from datetime import datetime, timezone
import websockets

CHANNELS = ("market_trades", "ticker", "heartbeats")


def to_product(symbol: str) -> str:
    return symbol.replace("/", "-").upper()


def to_symbol(product: str) -> str:
    return product.replace("-", "/").upper()


def parse_ts(s: str) -> float:
    """Coinbase timestamps carry up to 9 fractional digits; Python takes 6."""
    s = re.sub(r"(\.\d{6})\d+", r"\1", s.strip()).replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()


def parse(msg: dict) -> list[dict]:
    """Normalise one feed message into ticks. Unknown channels and malformed items are skipped, never raised."""
    out = []
    try:
        ch = msg.get("channel")
        for ev in msg.get("events") or []:
            if ch == "market_trades":
                for t in ev.get("trades") or []:
                    maker = str(t.get("side", "")).upper()
                    out.append({"kind": "trade", "snapshot": ev.get("type") == "snapshot", "id": str(t["trade_id"]), "symbol": to_symbol(t["product_id"]),
                                "price": float(t["price"]), "size": float(t["size"]), "side": "sell" if maker == "BUY" else "buy" if maker == "SELL" else "",
                                "ts": parse_ts(t["time"])})
            elif ch == "ticker":
                for t in ev.get("tickers") or []:
                    out.append({"kind": "ticker", "symbol": to_symbol(t["product_id"]), "price": float(t["price"]), "bid": float(t["best_bid"]) if t.get("best_bid") else None,
                                "ask": float(t["best_ask"]) if t.get("best_ask") else None, "vol24h": float(t["volume_24_h"]) if t.get("volume_24_h") else None,
                                "ts": parse_ts(msg["timestamp"]) if msg.get("timestamp") else time.time()})
    except (KeyError, ValueError, TypeError, AttributeError):
        return out
    return out


class CoinbaseFeed:
    def __init__(self, symbols, on_trade, on_ticker=None, on_message=None, url="wss://advanced-trade-ws.coinbase.com", connect=None, stale_after=25.0, max_backoff=30.0, base_backoff=1.0):
        self.products = [to_product(s) for s in symbols]; self.on_trade, self.on_ticker, self.on_message = on_trade, on_ticker, on_message
        self.url, self._connect, self.stale_after, self.max_backoff, self.base_backoff = url, connect or websockets.connect, stale_after, max_backoff, base_backoff
        self._seen: deque = deque(maxlen=20000); self._seen_set: set = set(); self._stop = False
        self.stats = {"connected": False, "messages": 0, "trades": 0, "gaps": 0, "bad": 0, "reconnects": 0, "last_error": "", "last_msg": 0.0}

    def stop(self):
        self._stop = True

    def _new_trade(self, tid: str) -> bool:
        if tid in self._seen_set: return False
        if len(self._seen) == self._seen.maxlen: self._seen_set.discard(self._seen[0])
        self._seen.append(tid); self._seen_set.add(tid); return True

    async def handle(self, raw):
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            self.stats["bad"] += 1; return                        # one garbage frame must not drop a healthy connection
        if not isinstance(msg, dict): self.stats["bad"] += 1; return
        self.stats["messages"] += 1; self.stats["last_msg"] = time.time()
        if msg.get("type") == "error":
            self.stats["last_error"] = str(msg.get("message", "feed error"))[:120]; return
        seq = msg.get("sequence_num")
        if isinstance(seq, int) and isinstance(self._last_seq, int) and seq > self._last_seq + 1: self.stats["gaps"] += 1       # informational: ticks are not stateful
        if isinstance(seq, int): self._last_seq = seq
        for t in parse(msg):
            if t["kind"] == "trade":
                if not self._new_trade(t["id"]): continue                  # snapshot after a reconnect repeats recent trades
                self.stats["trades"] += 1; await self.on_trade(t)
            elif self.on_ticker: await self.on_ticker(t)
        if self.on_message: await self.on_message(msg)

    async def run(self):
        try:
            await self._run()
        finally:
            self.stats["connected"] = False                                      # never leave a stopped feed looking connected

    async def _run(self):
        backoff, self._last_seq = self.base_backoff, None
        while not self._stop:
            try:
                async with self._connect(self.url, open_timeout=10) as ws:
                    for ch in CHANNELS:                                      # one subscribe per channel, well inside the 5-second limit
                        await ws.send(json.dumps({"type": "subscribe", "product_ids": self.products, "channel": ch}))
                    self.stats["connected"], self._last_seq = True, None
                    while not self._stop:
                        raw = await asyncio.wait_for(ws.recv(), timeout=self.stale_after)      # silence = dead connection
                        backoff = self.base_backoff
                        await self.handle(raw)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.stats["last_error"] = f"{type(e).__name__}: {str(e)[:100]}"
            self.stats["connected"] = False
            if self._stop: break
            self.stats["reconnects"] += 1
            await asyncio.sleep(backoff + random.uniform(0, 0.25 * backoff)); backoff = min(backoff * 2, self.max_backoff)

"""A local stand-in for Coinbase's public Advanced Trade WebSocket, written to the documented protocol: the client must send one subscribe per channel
within a time limit; market_trades arrive as snapshot then update events with maker-side trades; ticker carries price and best bid/ask; heartbeats keep the feed alive."""
import asyncio, json, time
from datetime import datetime, timezone
import websockets


def iso(t=None):
    return datetime.fromtimestamp(t or time.time(), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def trade(tid, price, size, side="BUY", t=None, product="BTC-USD"):
    return {"trade_id": str(tid), "product_id": product, "price": str(price), "size": str(size), "side": side, "time": iso(t)}


def trades_msg(trades, kind="update", seq=0):
    return json.dumps({"channel": "market_trades", "client_id": "", "timestamp": iso(), "sequence_num": seq, "events": [{"type": kind, "trades": trades}]})


def ticker_msg(price, bid, ask, seq=0, product="BTC-USD"):
    return json.dumps({"channel": "ticker", "client_id": "", "timestamp": iso(), "sequence_num": seq, "events": [{"type": "update", "tickers": [
        {"type": "ticker", "product_id": product, "price": str(price), "volume_24_h": "16038.28", "best_bid": str(bid), "best_ask": str(ask)}]}]})


def heartbeat_msg(n=1, seq=0):
    return json.dumps({"channel": "heartbeats", "client_id": "", "timestamp": iso(), "sequence_num": seq, "events": [{"current_time": iso(), "heartbeat_counter": n}]})


class FakeCoinbase:
    """script(ws, connection_number, server) decides what each connection sends."""
    def __init__(self, script=None, subscribe_timeout=1.5):
        self.script, self.subscribe_timeout = script or self.default_script, subscribe_timeout
        self.subscribes: list[dict] = []; self.connections = 0; self.server = None; self.port = 0

    async def default_script(self, ws, n, server):
        await ws.send(heartbeat_msg(1, 0)); await ws.send(ticker_msg(60000, 59999.5, 60000.5, 1))
        await ws.send(trades_msg([trade(100, 59990, 0.5, "SELL", time.time() - 3), trade(101, 59995, 0.2, "BUY", time.time() - 2)], "snapshot", 2))
        for i in range(5):
            await asyncio.sleep(0.05)
            await ws.send(trades_msg([trade(102 + i, 60000 + i, 0.01, "BUY" if i % 2 else "SELL")], "update", 3 + i))
        await ws.wait_closed()

    async def handler(self, ws):
        self.connections += 1; got = set()
        try:
            while len(got) < 3:
                m = json.loads(await asyncio.wait_for(ws.recv(), self.subscribe_timeout))
                self.subscribes.append(m); got.add(m["channel"])
        except Exception:
            await ws.close(code=1008); return                                   # no/late subscribe: disconnected, like the real service
        try:
            await self.script(ws, self.connections, self)
        except websockets.ConnectionClosed:
            pass

    async def __aenter__(self):
        self.server = await websockets.serve(self.handler, "127.0.0.1", 0); self.port = self.server.sockets[0].getsockname()[1]; return self

    async def __aexit__(self, *a):
        self.server.close(); await self.server.wait_closed()

    @property
    def url(self): return f"ws://127.0.0.1:{self.port}"

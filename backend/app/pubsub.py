"""Pub/sub for real-time ticks and user events. Redis in production; in-process fallback when REDIS_URL is empty
(fine for one API process, NOT for multiple processes)."""
import asyncio, json
from .config import get_settings


class MemoryPubSub:
    def __init__(self):
        self._subs: list[tuple[asyncio.Queue, set]] = []

    async def publish(self, channel: str, msg: dict):
        for q, chans in list(self._subs):
            if channel in chans:
                q.put_nowait((channel, msg))

    async def subscribe(self, channels):
        q: asyncio.Queue = asyncio.Queue(maxsize=1000); entry = (q, set(channels)); self._subs.append(entry)
        try:
            while True:
                yield await q.get()
        finally:
            self._subs.remove(entry)

    async def ping(self) -> bool:
        return True


class RedisPubSub:
    def __init__(self, url: str, client=None):
        import redis.asyncio as aioredis
        self.r = client or aioredis.from_url(url, decode_responses=True)

    async def publish(self, channel: str, msg: dict):
        await self.r.publish(channel, json.dumps(msg))

    async def subscribe(self, channels):
        ps = self.r.pubsub(); await ps.subscribe(*channels)
        try:
            async for m in ps.listen():
                if m.get("type") == "message":
                    yield m["channel"], json.loads(m["data"])
        finally:
            await ps.unsubscribe(*channels); await ps.aclose()

    async def ping(self) -> bool:
        try:
            return bool(await self.r.ping())
        except Exception:
            return False


_ps = None


def get_pubsub():
    global _ps
    if _ps is None:
        s = get_settings()
        _ps = RedisPubSub(s.redis_url) if s.redis_url else MemoryPubSub()
    return _ps


def set_pubsub(p):  # tests
    global _ps
    _ps = p

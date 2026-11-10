"""Last-price cache shared by the feeder, paper broker and runner (Redis if configured so API and worker agree)."""
import time
from .config import get_settings

_mem: dict[str, tuple[float, float]] = {}
_r = None


def _redis():
    global _r
    s = get_settings()
    if s.redis_url and _r is None:
        import redis
        _r = redis.Redis.from_url(s.redis_url, decode_responses=True, socket_timeout=1)
    return _r


def set_last(symbol: str, price: float):
    _mem[symbol] = (price, time.time())
    try:
        r = _redis()
        if r: r.setex(f"last:{symbol}", 120, price)
    except Exception:
        pass


def get_last(symbol: str, max_age: float = 120):
    try:
        r = _redis()
        if r:
            v = r.get(f"last:{symbol}")
            if v: return float(v)
    except Exception:
        pass
    v = _mem.get(symbol)
    return v[0] if v and time.time() - v[1] <= max_age else None

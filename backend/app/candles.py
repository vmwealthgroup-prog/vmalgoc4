"""Candles built from live ticks: a pure builder, plus storage and resampling of the recorded 1-minute candles."""
from datetime import datetime, timedelta, timezone
import pandas as pd
from sqlalchemy import select
from .models import MarketCandle

RULE = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "1d": "1D"}
MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "1d": 1440}


class CandleBuilder:
    """Feed it trades; it returns 1-minute candles once they can no longer change. A candle stays open for one extra minute so trades that arrive a little late
    still land in the right bucket. Trades older than that are dropped (a stored candle is never rewritten)."""
    def __init__(self):
        self.open: dict[tuple[str, int], dict] = {}
        self.newest: dict[str, int] = {}

    def add(self, symbol: str, price: float, size: float, ts: float) -> list[dict]:
        b = int(ts // 60); newest = self.newest.get(symbol, b)
        if b < newest - 1:
            return []
        self.newest[symbol] = newest = max(newest, b)
        c = self.open.get((symbol, b))
        if c is None:
            c = self.open[(symbol, b)] = {"symbol": symbol, "ts": b * 60, "open": price, "high": price, "low": price, "close": price, "volume": 0.0, "_first": ts, "_last": ts}
        c["high"], c["low"], c["volume"] = max(c["high"], price), min(c["low"], price), c["volume"] + max(size, 0.0)
        if ts >= c["_last"]: c["close"], c["_last"] = price, ts
        if ts < c["_first"]: c["open"], c["_first"] = price, ts
        done = sorted((k for k in self.open if k[0] == symbol and k[1] < newest - 1), key=lambda k: k[1])
        return [self._clean(self.open.pop(k)) for k in done]

    def flush(self) -> list[dict]:
        out = [self._clean(c) for _, c in sorted(self.open.items(), key=lambda kv: kv[0][1])]; self.open.clear(); return out

    @staticmethod
    def _clean(c): return {k: v for k, v in c.items() if not k.startswith("_")}


def save_candles(db, candles: list[dict]):
    for c in candles:
        ts = datetime.fromtimestamp(c["ts"], tz=timezone.utc)
        row = db.scalar(select(MarketCandle).where(MarketCandle.symbol == c["symbol"], MarketCandle.interval == "1m", MarketCandle.ts == ts))
        if row is None:
            db.add(MarketCandle(symbol=c["symbol"], interval="1m", ts=ts, open=c["open"], high=c["high"], low=c["low"], close=c["close"], volume=c["volume"]))
        else:
            row.high, row.low, row.close, row.volume = max(row.high, c["high"]), min(row.low, c["low"]), c["close"], max(row.volume, c["volume"])
    db.commit()


def load_candles(db, symbol: str, interval: str = "5m", bars: int = 500) -> pd.DataFrame:
    if interval not in RULE:
        raise ValueError(f"interval must be one of {list(RULE)}")
    since = datetime.now(timezone.utc) - timedelta(minutes=bars * MINUTES[interval] + 5)
    rows = db.scalars(select(MarketCandle).where(MarketCandle.symbol == symbol, MarketCandle.interval == "1m", MarketCandle.ts >= since).order_by(MarketCandle.ts)).all()
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"], index=pd.DatetimeIndex([], tz="UTC"))
    df = pd.DataFrame([{"ts": r.ts, "open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume} for r in rows])
    df["ts"] = pd.to_datetime(df["ts"], utc=True); df = df.set_index("ts")
    if interval != "1m":
        df = df.resample(RULE[interval]).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["close"])
    return df.tail(bars)

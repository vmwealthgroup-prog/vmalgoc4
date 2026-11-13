"""Candle providers: demo (synthetic) and crypto (public exchange data)."""
import zlib
import numpy as np
import pandas as pd
from .config import get_settings

FREQ = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "1d": "1D"}


def demo_candles(symbol: str, interval: str = "5m", bars: int = 500) -> pd.DataFrame:
    """Deterministic synthetic candles for research and paper trading only."""
    n = max(5000, bars)
    seed = zlib.crc32(symbol.encode()); rng = np.random.default_rng(seed)
    vol = 0.011 if interval == "1d" else 0.0025
    close = (50 + seed % 2000) * np.exp(np.cumsum(rng.normal(0.00003, vol, n)))
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor(FREQ[interval]), periods=n, freq=FREQ[interval])
    open_ = np.concatenate([[close[0]], close[:-1]]); span = np.abs(rng.normal(0, vol / 2, n))
    df = pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * (1 + span), "low": np.minimum(open_, close) * (1 - span),
                       "close": close, "volume": rng.integers(1_000, 50_000, n).astype(float)}, index=idx)
    return df.tail(bars)


def crypto_candles(symbol: str, interval: str, bars: int, exchange_id: str | None = None) -> pd.DataFrame:
    import ccxt
    ex = getattr(ccxt, exchange_id or get_settings().crypto_exchange)({"enableRateLimit": True})
    rows = ex.fetch_ohlcv(symbol, timeframe=interval, limit=min(bars, 1000))
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
    return df[~df.index.duplicated()].sort_index()


def get_candles(symbol, exchange, interval="5m", bars=500, source="auto", client=None, db=None) -> pd.DataFrame:
    if interval not in FREQ:
        raise ValueError(f"interval must be one of {list(FREQ)}")
    if source == "auto":
        source = "crypto" if exchange == "CRYPTO" else "demo"
    if source == "recorded":
        if db is None:
            raise ValueError("recorded data needs a database session")
        from .candles import load_candles
        df = load_candles(db, symbol, interval, bars)
        if len(df) < 30:
            raise ValueError(f"Not enough recorded data for {symbol} yet ({len(df)} {interval} candles).")
        return df
    if source == "demo":
        return demo_candles(symbol, interval, bars)
    if source == "crypto":
        if exchange != "CRYPTO":
            raise ValueError("crypto candles are only valid for CRYPTO symbols")
        return crypto_candles(symbol, interval, bars)
    raise ValueError("Unsupported data source")

"""Candle providers: demo (deterministic synthetic), openalgo (Indian brokers), crypto (ccxt, public data)."""
import zlib
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
from .config import get_settings

FREQ = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "1d": "1D"}
SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}
OA_INTERVAL = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "1d": "D"}


def demo_candles(symbol: str, interval: str = "5m", bars: int = 500) -> pd.DataFrame:
    """Deterministic synthetic candles. The series is generated at a fixed length and sliced from the END, so the latest price
    is the same no matter how many bars are requested (the feeder, runner and paper broker must agree on 'now')."""
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


def openalgo_candles(client, symbol: str, exchange: str, interval: str, bars: int) -> pd.DataFrame:
    days = max(2, int(bars * SECONDS[interval] / 86400 * (1.6 if interval != "1d" else 1.5)) + 2)
    end = datetime.now(timezone.utc).date()
    df = client.history(symbol=symbol, exchange=exchange, interval=OA_INTERVAL[interval],
                        start_date=str(end - timedelta(days=days)), end_date=str(end))
    if isinstance(df, dict):
        raise RuntimeError(df.get("message", "history failed"))
    df.columns = [c.lower() for c in df.columns]
    return df.tail(bars)


def get_candles(symbol, exchange, interval="5m", bars=500, source="auto", client=None, db=None) -> pd.DataFrame:
    if interval not in FREQ:
        raise ValueError(f"interval must be one of {list(FREQ)}")
    if source == "auto":
        source = "openalgo" if client is not None else "demo"
    if source == "recorded":
        if db is None: raise ValueError("recorded data needs a database session")
        from .candles import load_candles
        df = load_candles(db, symbol, interval, bars)
        if len(df) < 30: raise ValueError(f"Not enough recorded data for {symbol} yet ({len(df)} {interval} candles). The live feed records 1-minute candles while the worker runs.")
        return df
    if source == "openalgo":
        if client is None: raise ValueError("no OpenAlgo account available")
        return openalgo_candles(client, symbol, exchange, interval, bars)
    if source == "crypto":
        return crypto_candles(symbol, interval, bars)
    return demo_candles(symbol, interval, bars)

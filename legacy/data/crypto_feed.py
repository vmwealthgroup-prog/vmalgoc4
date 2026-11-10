"""Crypto market data via ccxt. Public data (candles, prices) needs NO API key on most exchanges.
Keys are only read from the environment if you set them, and are never needed for this file's read-only functions.
  CRYPTO_EXCHANGE   ccxt id: coinbase (Advanced Trade), coinbaseexchange, kraken, bybit, okx, binance ...
  CRYPTO_API_KEY / CRYPTO_API_SECRET / CRYPTO_API_PASSPHRASE   optional, only for private endpoints
Use a READ-ONLY key (no trade, no withdraw permission) even if you set one."""
import os, time
import ccxt
import pandas as pd


def get_exchange(name=None):
    name = name or os.environ.get("CRYPTO_EXCHANGE", "coinbase")
    cfg = {"enableRateLimit": True}
    if os.environ.get("CRYPTO_API_KEY"):
        cfg["apiKey"] = os.environ["CRYPTO_API_KEY"]
        cfg["secret"] = os.environ.get("CRYPTO_API_SECRET", "").replace("\\n", "\n")  # PEM keys often stored with \n
        if os.environ.get("CRYPTO_API_PASSPHRASE"):
            cfg["password"] = os.environ["CRYPTO_API_PASSPHRASE"]
    return getattr(ccxt, name)(cfg)


def candles_to_df(rows):
    """ccxt rows [ms, o, h, l, c, v] -> DataFrame matching what strategies/signals.py expects."""
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
    return df[~df.index.duplicated()].sort_index()


def history(symbol="BTC/USD", timeframe="5m", limit=300, exchange=None):
    ex = exchange or get_exchange()
    return candles_to_df(ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit))


def price(symbol="BTC/USD", exchange=None):
    return (exchange or get_exchange()).fetch_ticker(symbol)["last"]


if __name__ == "__main__":  # python data/crypto_feed.py BTC/USD  -> prints a live price every 5s (Ctrl+C to stop)
    import sys
    ex, sym = get_exchange(), (sys.argv[1] if len(sys.argv) > 1 else "BTC/USD")
    while True:
        print(time.strftime("%H:%M:%S"), sym, price(sym, ex)); time.sleep(5)

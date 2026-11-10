"""PAPER trading on live crypto candles. Places NO orders and needs NO API key; it only logs the position
a strategy would hold. Usage: python crypto_paper_runner.py [strategy] [symbol] [timeframe]"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data"))
from signals import REGISTRY
from crypto_feed import get_exchange, history

name = sys.argv[1] if len(sys.argv) > 1 else "ema_crossover"
symbol = sys.argv[2] if len(sys.argv) > 2 else "BTC/USD"
tf = sys.argv[3] if len(sys.argv) > 3 else "5m"
ex, last = get_exchange(), None
print(f"Paper trading {name} on {symbol} {tf} via {ex.id}. No orders are sent.")
while True:
    df = history(symbol, tf, 300, ex)
    target = int(REGISTRY[name](df).iloc[-2])  # last completed candle only
    if target != last:
        print(f"{time.strftime('%H:%M:%S')} paper position -> {target:+d} at {df['close'].iloc[-1]:.2f}")
        last = target
    time.sleep(30)

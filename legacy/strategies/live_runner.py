"""Runs one signal strategy against OpenAlgo behind a pre-trade risk gate. DRY_RUN (print only) by default.
Enable OpenAlgo Analyzer Mode and test there before ever going live.
Env: OPENALGO_API_KEY, HOST_SERVER (default http://127.0.0.1:5000); both are injected by the OpenAlgo /python strategy host.
Create a file named KILL next to this script to stop all new orders immediately."""
import os, sys, time
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "risk"))
from openalgo import api
from signals import REGISTRY
from sizing import atr, atr_qty
from risk_gate import RiskGate, Limits

STRATEGY = "ema_crossover"      # key in signals.REGISTRY
SYMBOL, EXCHANGE = "RELIANCE", "NSE"
INTERVAL, FIXED_QTY = "5m", 1
EQUITY, RISK_PCT = 0, 0.5       # set EQUITY > 0 to size by ATR risk (stop = 2 ATR); 0 = use FIXED_QTY
PRODUCT, SQUARE_OFF = "MIS", "15:15"
DRY_RUN = True                  # set False only after paper testing
gate = RiskGate(Limits(max_qty=100, max_order_value=300_000, max_position_value=300_000, max_orders_per_day=10,
                       max_daily_loss=3_000, window=("09:20", SQUARE_OFF), kill_file="KILL"))

client = api(api_key=os.environ["OPENALGO_API_KEY"], host=os.environ.get("HOST_SERVER") or os.environ.get("OPENALGO_HOST", "http://127.0.0.1:5000"))


def latest():
    end = datetime.now().date()
    df = client.history(symbol=SYMBOL, exchange=EXCHANGE, interval=INTERVAL,
                        start_date=str(end - timedelta(days=10)), end_date=str(end))
    qty = atr_qty(EQUITY, RISK_PCT, float(atr(df).iloc[-2])) if EQUITY else FIXED_QTY
    return int(REGISTRY[STRATEGY](df).iloc[-2]), max(qty, 1), float(df["close"].iloc[-1])  # last COMPLETED bar signal


def send(target, qty, price):
    want = target * qty
    delta = want - gate.pos.get(SYMBOL, 0)          # the gate tracks INTENDED position, not broker-confirmed fills
    if delta == 0:
        return
    side = "BUY" if delta > 0 else "SELL"
    ok, why = gate.check(SYMBOL, side, abs(delta), price)
    print(f"{datetime.now():%H:%M:%S} target {want:+d} ({side} {abs(delta)} @ {price:.2f}) -> {why}")
    if not ok:
        return
    if not DRY_RUN:
        client.placesmartorder(strategy=STRATEGY, symbol=SYMBOL, action=side, exchange=EXCHANGE, price_type="MARKET",
                               product=PRODUCT, quantity=abs(delta), position_size=want)
    gate.record(SYMBOL, side, abs(delta))


last = None
while True:
    if datetime.now().strftime("%H:%M") >= SQUARE_OFF:
        gate.l.window = ("00:00", "23:59"); send(0, 1, 1.0); print("Square-off time reached. Stopping."); sys.exit(0)
    t, q, px = latest()
    if t != last:
        send(t, q, px); last = t
    time.sleep(30)

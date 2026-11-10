"""Automation: evaluates every deployed (paper/live) strategy on fresh candles and trades the difference between the
target position and the current position, through the same risk-gated pipeline as manual orders."""
from datetime import datetime, timedelta, timezone
import json
from sqlalchemy import select
from . import market
from .brokers.factory import ensure_paper_account, get_broker
from .config import get_settings
from .guard import check_breaker
from .data import get_candles
from .engine.rules import indicator, positions as rule_positions
from .engine.sizing import atr_qty
from .brokers.kite import today as kite_today, token_ok as kite_token_ok
from .models import AppSetting, BrokerAccount, Order, Strategy, User
from .security import decrypt
from .trading import now_ist, submit_order


def _event(user_id, st, o: Order):
    kind = "kill_switch" if "kill switch engaged" in (o.message or "") else "order"
    return {"user_id": user_id, "type": kind, "strategy": st.name, "symbol": o.symbol, "side": o.side, "qty": o.qty, "price": o.price, "status": o.status, "message": o.message, "ts": o.created_at.isoformat() if o.created_at else None}


def run_strategy(db, st: Strategy) -> list[dict]:
    user = db.get(User, st.user_id)
    if user is None or not user.is_active:
        return []
    spec = st.spec; sym, exch = spec["symbol"], spec["exchange"]
    s = get_settings(); live = st.mode == "live"
    reason = check_breaker(db, st)
    if reason:
        return [{"user_id": user.id, "type": "breaker", "strategy": st.name, "message": reason}]
    if s.enforce_market_hours and not market.is_open(exch):
        return []                                              # market closed: nothing to do, no data calls
    acct = db.get(BrokerAccount, st.account_id) if (live and st.account_id) else ensure_paper_account(db, user)
    if acct is None:
        acct = ensure_paper_account(db, user)
    broker = get_broker(db, acct)
    data_client = broker.history_client() if live else None
    df = get_candles(sym, exch, spec["interval"], 300, "crypto" if exch == "CRYPTO" and not data_client else "auto", client=data_client)
    if len(df) < 30:
        return []
    direction = int(rule_positions(df, spec).iloc[-2])                       # last COMPLETED bar
    r = spec.get("risk", {}); qty = int(r.get("qty", 1) or 1)
    if r.get("risk_pct") and r.get("equity"):
        qty = atr_qty(float(r["equity"]), float(r["risk_pct"]), float(indicator(df, "atr", 14).iloc[-2]), float(r.get("stop_atr", 2)), max_qty=r.get("max_qty")) or 0
    target = direction * qty
    explicit = r.get("square_off") and exch != "CRYPTO" and now_ist().strftime("%H:%M") >= r["square_off"]
    if explicit or (s.enforce_market_hours and market.square_off_due(exch, r.get("product", "MIS"), None)):
        target = 0
    cur = next((p["qty"] for p in broker.positions() if p["symbol"] == sym and p["exchange"] == exch), 0.0)
    delta = target - cur
    st.last_run = datetime.now(timezone.utc); st.last_target = int(target)
    if delta == 0:
        return []
    side, q = ("BUY", delta) if delta > 0 else ("SELL", -delta)
    # don't re-record an identical blocked decision every loop
    if db.scalar(select(Order.id).where(Order.strategy_id == st.id, Order.status == "blocked", Order.side == side, Order.qty == q,
                                        Order.created_at >= datetime.now(timezone.utc) - timedelta(minutes=10)).limit(1)):
        return []
    o = submit_order(db, user, acct, broker, symbol=sym, exchange=exch, side=side, qty=q, price=float(df["close"].iloc[-1]), strategy_id=st.id,
                     mode="live" if live else "paper", product=r.get("product", "MIS"))
    return [_event(user.id, st, o)]


def token_alerts(db) -> list[dict]:
    """Once per trading day, tell the owner if a live-enabled Zerodha account still needs its daily login."""
    t = now_ist()
    if t.weekday() >= 5 or not ("08:30" <= t.strftime("%H:%M") <= "15:30"):
        return []
    out = []
    for a in db.scalars(select(BrokerAccount).where(BrokerAccount.kind == "kite", BrokerAccount.live_enabled == True)).all():  # noqa: E712
        try:
            if kite_token_ok(json.loads(decrypt(a.api_key_enc))): continue
        except Exception:
            pass
        row = db.get(AppSetting, f"tokalert:{a.id}")
        if row and row.value == kite_today(): continue
        if row is None: db.add(AppSetting(key=f"tokalert:{a.id}", value=kite_today()))
        else: row.value = kite_today()
        out.append({"user_id": a.user_id, "type": "token", "strategy": "", "message": f"Zerodha login for '{a.label}' has expired. Do the daily login (Brokers page) so live strategies can trade."})
    db.commit()
    return out


def run_once(db) -> list[dict]:
    events = []
    for st in db.scalars(select(Strategy).where(Strategy.mode.in_(("paper", "live")))).all():
        try:
            events += run_strategy(db, st)
            db.commit()
        except Exception as e:  # one bad strategy must not stop the others
            db.rollback()
            events.append({"user_id": st.user_id, "type": "error", "strategy": st.name, "message": str(e)[:200]})
    try:
        events += token_alerts(db)
    except Exception:
        db.rollback()
    return events

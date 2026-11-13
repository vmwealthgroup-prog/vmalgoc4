"""Automation: evaluates deployed strategies through the common risk-gated order pipeline."""
from datetime import datetime, timedelta, timezone
import json
import math
from sqlalchemy import select
from . import market
from .brokers.factory import ensure_paper_account, get_broker, live_account_error
from .config import get_settings
from .guard import check_breaker
from .data import get_candles
from .engine.rules import indicator, positions as rule_positions
from .engine.sizing import atr_qty
from .brokers.kite import today as kite_today, token_ok as kite_token_ok
from .models import AppSetting, BrokerAccount, Order, Strategy, User
from .security import decrypt
from .trading import now_ist, submit_order
from .policy import live_allowed


def _event(user_id, st, o: Order):
    kind = "kill_switch" if "kill switch engaged" in (o.message or "") else "order"
    return {"user_id": user_id, "type": kind, "strategy": st.name, "symbol": o.symbol, "side": o.side, "qty": o.qty, "price": o.price, "status": o.status, "message": o.message, "ts": o.created_at.isoformat() if o.created_at else None}


def _safety_event(user, st, message):
    return {"user_id": user.id, "type": "safety_block", "strategy": st.name, "symbol": st.spec.get("symbol"), "status": "blocked", "message": message}


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
        return []
    acct = db.get(BrokerAccount, st.account_id) if (live and st.account_id) else ensure_paper_account(db, user)
    if acct is None or acct.user_id != user.id:
        return [_safety_event(user, st, "Selected broker account is missing or does not belong to this strategy owner.")]
    if live:
        if not s.live_trading_enabled:
            return [_safety_event(user, st, "Live trading is disabled on this server (LIVE_TRADING_ENABLED=false).")]
        if not live_allowed(db):
            return [_safety_event(user, st, "Live trading requires login to be enabled in Settings.")]
        account_reason = live_account_error(acct)
        if account_reason:
            return [_safety_event(user, st, account_reason)]
        if exch != "CRYPTO":
            return [_safety_event(user, st, "Automated Indian-market live strategies are disabled: no validated real Indian-market candle provider is configured. Paper trading and backtesting remain available.")]
        if acct.kind != "ccxt":
            return [_safety_event(user, st, "Live crypto strategies require a CCXT exchange account.")]
    try:
        broker = get_broker(db, acct)
        if live:
            # Live crypto only: use public exchange OHLCV, never demo or an unverified broker-history fallback.
            df = get_candles(sym, exch, spec["interval"], 300, "crypto")
        else:
            df = get_candles(sym, exch, spec["interval"], 300, "auto")
    except Exception as exc:
        if live:
            return [_safety_event(user, st, f"Live market data unavailable; no order sent: {str(exc)[:150]}")]
        raise
    if len(df) < 30 or not all(math.isfinite(float(df[c].iloc[-1])) for c in ("open", "high", "low", "close")):
        if live:
            return [_safety_event(user, st, "Live candle data is incomplete or invalid; no order sent.")]
        return []
    direction = int(rule_positions(df, spec).iloc[-2])
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
        except Exception as e:
            db.rollback()
            events.append({"user_id": st.user_id, "type": "error", "strategy": st.name, "message": str(e)[:200]})
    try:
        events += token_alerts(db)
    except Exception:
        db.rollback()
    return events

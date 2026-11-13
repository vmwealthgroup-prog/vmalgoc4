"""TradingView alert receiver. Create a webhook, paste its URL into a TradingView alert, and send JSON like
   {"action": "buy", "symbol": "TCS", "exchange": "NSE", "qty": 5}        action: buy | sell | close
Every alert goes through the same risk-gated order path as everything else. The URL contains a secret token (shown once; only its hash is stored)."""
import hashlib, re, secrets, math
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .. import notify, quotes
from ..brokers.factory import ensure_paper_account, get_broker, live_account_error
from ..data import demo_candles
from ..config import get_settings
from ..db import get_db
from ..deps import current_user, owned_account
from ..models import User, Webhook
from ..policy import live_allowed
from ..trading import submit_order

manage = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
public = APIRouter(prefix="/api/hooks", tags=["webhooks"])
SYMBOL = re.compile(r"^[A-Z0-9:._&/-]{1,40}$")
ACTIONS = {"buy": "BUY", "long": "BUY", "sell": "SELL", "short": "SELL", "close": "CLOSE", "exit": "CLOSE", "flat": "CLOSE"}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _out(w: Webhook):
    return {"id": w.id, "name": w.name, "mode": w.mode, "account_id": w.account_id, "hits": w.hits, "last_used_at": w.last_used_at.isoformat() if w.last_used_at else None}


class HookIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    mode: str = "paper"
    account_id: int | None = None


@manage.get("")
def list_hooks(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_out(w) for w in db.scalars(select(Webhook).where(Webhook.user_id == u.id).order_by(Webhook.id.desc()))]


@manage.post("", status_code=201)
def create_hook(b: HookIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if b.mode not in ("paper", "live"): raise HTTPException(422, "mode must be paper or live")
    if b.mode == "live":
        if not live_allowed(db): raise HTTPException(403, "Live webhooks need login. Turn on login in Settings first.")
        a = owned_account(db, u, b.account_id) if b.account_id else None
        if a is None: raise HTTPException(400, "A live webhook needs a broker account")
        reason = live_account_error(a)
        if reason: raise HTTPException(400, reason)
        if not get_settings().live_trading_enabled: raise HTTPException(403, "Live trading is disabled on this server")
    token = secrets.token_urlsafe(32)
    w = Webhook(user_id=u.id, name=b.name, token_hash=_hash(token), mode=b.mode, account_id=b.account_id if b.mode == "live" else None)
    db.add(w); db.commit()
    return {**_out(w), "token": token, "path": f"/api/hooks/tv/{token}", "note": "Copy the URL now: the token is not shown again."}


@manage.delete("/{wid}", status_code=204)
def delete_hook(wid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    w = db.get(Webhook, wid)
    if not w or w.user_id != u.id: raise HTTPException(404, "Webhook not found")
    db.delete(w); db.commit()


@public.post("/tv/{token}")
async def receive(token: str, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    raw = await request.body()
    if len(raw) > 4096: raise HTTPException(413, "alert body too large")
    w = db.scalar(select(Webhook).where(Webhook.token_hash == _hash(token)))
    if w is None: raise HTTPException(404, "Not found")                       # same answer for any wrong token
    user = db.get(User, w.user_id)
    if user is None or not user.is_active: raise HTTPException(404, "Not found")
    try:
        import json
        d = json.loads(raw or b"{}"); assert isinstance(d, dict)
        action = ACTIONS[str(d.get("action", "")).strip().lower()]
        symbol = str(d.get("symbol", "")).strip().upper().split(":")[-1]                       # TradingView may send "EXCHANGE:SYMBOL"
        exchange = str(d.get("exchange", "NSE")).strip().upper(); assert re.fullmatch(r"[A-Z]{2,10}", exchange)
        if exchange == "CRYPTO" and "/" not in symbol:                                           # BTCUSDT -> BTC/USDT
            for q in ("USDT", "USDC", "USD", "EUR", "BTC", "ETH"):
                if symbol.endswith(q) and len(symbol) > len(q): symbol = f"{symbol[:-len(q)]}/{q}"; break
        assert SYMBOL.match(symbol)
        qty = float(d.get("qty", 1)); assert 0 < qty <= 1_000_000
        px = float(d["price"]) if d.get("price") not in (None, "") else None; assert px is None or (math.isfinite(px) and px > 0)
        product = str(d.get("product", "MIS")).upper(); assert product in ("MIS", "CNC", "NRML")
    except Exception:
        raise HTTPException(422, 'Expected JSON like {"action": "buy|sell|close", "symbol": "TCS", "exchange": "NSE", "qty": 1}')
    w.hits += 1; w.last_used_at = datetime.now(timezone.utc)
    acct = owned_account(db, user, w.account_id) if (w.mode == "live" and w.account_id) else ensure_paper_account(db, user)
    try:
        broker = get_broker(db, acct)
    except Exception as e:
        db.commit(); return {"status": "failed", "message": str(e)[:200]}
    if w.mode == "live":
        if px is None:
            try:
                live_quote = broker.quote(symbol, exchange)
                px = float(live_quote.get("ltp") or 0)
            except Exception:
                px = 0
        if not px or px <= 0:
            db.commit()
            raise HTTPException(422, "Live webhook requires a valid alert price or verified broker quote; demo prices are never used")
        price = px
    else:
        price = px or quotes.get_last(symbol) or float(demo_candles(symbol, "5m", 5)["close"].iloc[-1])
    side = action
    if action == "CLOSE":
        pos = next((p["qty"] for p in broker.positions() if p["symbol"] == symbol and p["exchange"] == exchange), 0.0)
        if pos == 0:
            db.commit(); return {"status": "noop", "message": "no open position to close"}
        side, qty = ("SELL", pos) if pos > 0 else ("BUY", -pos)
    o = submit_order(db, user, acct, broker, symbol=symbol, exchange=exchange, side=side, qty=qty, price=price, mode=w.mode, product=product)
    db.commit()
    ev = {"type": "order", "status": o.status, "side": o.side, "qty": o.qty, "symbol": o.symbol, "price": o.price, "strategy": f"tradingview:{w.name}", "message": o.message}
    fm = notify.format_event(ev)
    if fm: background.add_task(notify.notify, *fm)
    return {"status": o.status, "message": o.message, "order_id": o.id}

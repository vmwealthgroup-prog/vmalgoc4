import time
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .. import market, notify
from ..brokers.factory import ensure_limits, ensure_paper_account, get_broker
from ..config import get_settings
from ..db import get_db
from ..deps import admin_user, current_user
import json
from ..heartbeat import age_seconds, get as hb_get
from ..models import Strategy, User
from ..policy import auth_required, brokers_allowed, live_allowed

router = APIRouter(prefix="/api/system", tags=["system"])
_ip_cache: dict = {"t": 0, "v": None}
_transport = None          # tests inject httpx.MockTransport


@router.get("/status")
def status(u: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_settings(); feed, runner = age_seconds(db, "feed"), age_seconds(db, "runner")
    runner_limit = s.runner_interval_s * 3 + 15
    modes = dict(db.execute(select(Strategy.mode, func.count()).where(Strategy.user_id == u.id).group_by(Strategy.mode)).all())
    try: day_pnl = get_broker(db, ensure_paper_account(db, u)).daily_pnl()
    except Exception: day_pnl = None
    lim = ensure_limits(db, u.id); db.commit()
    problems = []
    if runner is None: problems.append("no runner heartbeat yet (is the worker running?)")
    elif runner > runner_limit: problems.append(f"runner silent for {runner:.0f}s")
    if feed is None: problems.append("no feed heartbeat yet")
    elif feed > 60: problems.append(f"price feed silent for {feed:.0f}s")
    try: feed_stats = json.loads(hb_get(db, "feedstats") or "null")
    except Exception: feed_stats = None
    return {"feed": feed_stats, "crypto_feed": s.crypto_feed, "healthy": not problems, "problems": problems, "feed_age_s": feed, "runner_age_s": runner,
            "markets": {ex: market.is_open(ex) for ex in ("NSE", "NFO", "MCX", "CRYPTO")},
            "kill_switch": lim.kill_switch, "paper_day_pnl": None if day_pnl is None else round(day_pnl, 2), "strategies": {m: modes.get(m, 0) for m in ("off", "paper", "live")},
            "access_mode": "login" if auth_required(db) else "open", "live_available": live_allowed(db), "brokers_available": brokers_allowed(db),
            "notifications": notify.channels(),
            "settings": {"enforce_market_hours": s.enforce_market_hours, "square_off_time": s.square_off_time, "max_orders_per_second": s.max_orders_per_second, "feed_source": s.feed_source}}


@router.get("/egress-ip")
def egress_ip(_: User = Depends(current_user)):
    """The public IP this server sends orders from. Indian brokers accept API orders only from a static IP you have registered with them."""
    if time.time() - _ip_cache["t"] < 600 and _ip_cache["v"]:
        return _ip_cache["v"]
    try:
        with httpx.Client(timeout=4, transport=_transport) as c:
            r = c.get(get_settings().egress_ip_url); r.raise_for_status(); ip = r.text.strip()
        out = {"ip": ip, "note": "Register this as your static IP with your broker. It must stay the same: use a static/elastic IP on your host."}
        _ip_cache.update(t=time.time(), v=out); return out
    except Exception as e:
        return {"ip": None, "error": f"could not determine IP ({type(e).__name__})"}


@router.post("/notify-test")
def notify_test(_: User = Depends(admin_user)):
    ch = notify.channels()
    if not ch: return {"channels": [], "message": "No notification channel is configured (set TELEGRAM_*, DISCORD_WEBHOOK_URL or NOTIFY_WEBHOOK_URL)."}
    return {"channels": ch, "results": notify.notify("VM Algo test alert: notifications are working.", force=True)}

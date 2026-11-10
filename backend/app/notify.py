"""Alerts to Telegram, Discord and/or a generic webhook. Credentials live in env only. A failing channel never breaks trading."""
import time
import httpx
from .config import get_settings

_recent: dict[str, float] = {}
_transport = None          # tests inject httpx.MockTransport here
DEDUPE_S = 60


def channels() -> list[str]:
    s = get_settings()
    return [n for n, on in (("telegram", s.telegram_bot_token and s.telegram_chat_id), ("discord", s.discord_webhook_url), ("webhook", s.notify_webhook_url)) if on]


def _post(url, payload):
    with httpx.Client(timeout=5, transport=_transport) as c:
        r = c.post(url, json=payload); r.raise_for_status()


def notify(text: str, level: str = "info", force: bool = False) -> dict:
    """Send to every configured channel. Identical messages inside 60 s are dropped (no alert storms) unless force=True."""
    s, now = get_settings(), time.time()
    if not force and now - _recent.get(text, 0) < DEDUPE_S:
        return {"skipped": "duplicate"}
    _recent[text] = now
    if len(_recent) > 500:
        for k in [k for k, t in _recent.items() if now - t > DEDUPE_S]: _recent.pop(k, None)
    out = {}
    jobs = []
    if s.telegram_bot_token and s.telegram_chat_id:
        jobs.append(("telegram", f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage", {"chat_id": s.telegram_chat_id, "text": text[:3900], "disable_web_page_preview": True}))
    if s.discord_webhook_url:
        jobs.append(("discord", s.discord_webhook_url, {"content": text[:1900]}))
    if s.notify_webhook_url:
        jobs.append(("webhook", s.notify_webhook_url, {"text": text, "level": level}))
    for name, url, payload in jobs:
        try:
            _post(url, payload); out[name] = "ok"
        except Exception as e:                      # never leak the bot token that is inside the URL
            out[name] = "error: " + type(e).__name__
    return out


def format_event(e: dict) -> tuple[str, str] | None:
    """(text, level) for events worth an alert; None for routine ones."""
    t = e.get("type")
    if t == "order":
        if e.get("status") in ("filled", "sent"):
            return f"{e['side']} {e['qty']:g} {e['symbol']} @ {e.get('price') or 0:g} ({e.get('strategy', 'manual')}) {e['status']}", "info"
        return f"ORDER {e['status'].upper()}: {e['side']} {e['qty']:g} {e['symbol']} ({e.get('strategy', 'manual')}): {e.get('message', '')}", "warning"
    if t in ("error", "breaker", "kill_switch", "token", "reconcile", "watchdog"):
        return f"{t.upper()}: {e.get('strategy', '')} {e.get('message', '')}".strip(), "error"
    return None

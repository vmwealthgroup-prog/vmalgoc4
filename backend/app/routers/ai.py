import time
from collections import defaultdict, deque
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..ai import analyst
from ..ai.context import build_context
from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..models import User

router = APIRouter(prefix="/api/ai", tags=["ai"])
_calls: dict[int, deque] = defaultdict(deque)       # per-process sliding window; use a shared store if you run several API replicas


class AnalyzeIn(BaseModel):
    symbol: str = Field(default="BTC/USD", min_length=1, max_length=40)
    exchange: str = Field(default="CRYPTO", min_length=2, max_length=20)
    interval: str = Field(default="1h", pattern="^(1m|5m|15m|1h|1d)$")
    question: str = Field(default="", max_length=600)
    include_portfolio: bool = False                  # opt-in: sends your paper positions, strategies and backtest results to the AI provider
    use_ai: bool = True                              # false = always use the built-in offline analyst


@router.get("/status")
def status(_: User = Depends(current_user)):
    s = get_settings()
    return {"claude_configured": bool(s.anthropic_api_key), "model": s.ai_model if s.anthropic_api_key else None, "limit_per_hour": s.ai_max_per_hour,
            "advisory_only": True, "note": "The analyst can read market data and write analysis. It cannot place orders."}


@router.post("/analyze")
def analyze(b: AnalyzeIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_settings(); symbol, exchange = b.symbol.strip().upper(), b.exchange.strip().upper()
    q = _calls[u.id]; now = time.time()
    while q and now - q[0] > 3600: q.popleft()
    if len(q) >= s.ai_max_per_hour: raise HTTPException(429, f"Analysis limit reached ({s.ai_max_per_hour} per hour). Try again later.")
    q.append(now)
    try:
        ctx = build_context(db, u, symbol, exchange, b.interval, b.include_portfolio)
    except Exception as e:
        raise HTTPException(422, f"Could not load market data for {symbol}: {str(e)[:150]}")
    want_draft = any(w in b.question.lower() for w in ("strategy", "idea", "draft", "rule", "setup", "backtest"))
    mode, warning, out = "offline", None, None
    if b.use_ai and s.anthropic_api_key:
        try:
            out = analyst.parse_model_json(analyst.call_claude(ctx, b.question)); mode = "claude"
        except analyst.AIError as e:
            warning = f"The AI provider could not be used ({e}); showing the built-in analyst instead."
    if out is None:
        out = analyst.offline_analysis(ctx, want_draft)
    draft, note = analyst.sanitize_draft(out.get("strategy_draft"), symbol, exchange, b.interval)
    return {"mode": mode, "model": s.ai_model if mode == "claude" else None, "summary": out["summary"], "points": out["points"], "risks": out["risks"], "strategy_draft": draft, "draft_note": note,
            "facts": ctx["facts"], "data_source": ctx["data_source"], "synthetic": ctx["data_is_synthetic"], "sent_portfolio": b.include_portfolio and mode == "claude",
            "warning": warning, "disclaimer": analyst.DISCLAIMER}

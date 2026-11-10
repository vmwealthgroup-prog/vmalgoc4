from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..data import get_candles
from ..db import get_db
from ..deps import current_user
from ..engine.rules import eval_group, indicator, validate_group
from ..models import User
from .backtests import resolve_data

router = APIRouter(prefix="/api/scanner", tags=["scanner"])
PRESETS = [
    {"key": "oversold", "name": "Oversold (RSI 14 < 30)", "conditions": {"all": [{"left": {"ind": "rsi", "period": 14}, "op": "<", "right": {"value": 30}}]}},
    {"key": "ema_cross", "name": "Bullish EMA 9/21 cross", "conditions": {"all": [{"left": {"ind": "ema", "period": 9}, "op": "crosses_above", "right": {"ind": "ema", "period": 21}}]}},
    {"key": "breakout", "name": "Closes above 20-bar high", "conditions": {"all": [{"left": {"ind": "close"}, "op": ">", "right": {"ind": "hh", "period": 20}}]}},
    {"key": "trend", "name": "Trend: close > EMA 50 and RSI > 55", "conditions": {"all": [{"left": {"ind": "close"}, "op": ">", "right": {"ind": "ema", "period": 50}}, {"left": {"ind": "rsi", "period": 14}, "op": ">", "right": {"value": 55}}]}},
]


class ScanIn(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=50)
    exchange: str = "NSE"
    interval: str = "1d"
    source: str = "auto"
    conditions: dict


@router.get("/presets")
def presets(_: User = Depends(current_user)):
    return PRESETS


@router.post("/run")
def run(b: ScanIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        validate_group(b.conditions, "conditions")
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(422, str(e))
    source, client = resolve_data(db, u, b.exchange, b.source)
    rows, errors = [], []
    for sym in dict.fromkeys(s.strip().upper() for s in b.symbols if s.strip()):
        try:
            df = get_candles(sym, b.exchange, b.interval, 250, source, client, db=db)
            hit = bool(eval_group(df, b.conditions).iloc[-2])                    # last completed bar
            rows.append({"symbol": sym, "match": hit, "close": round(float(df["close"].iloc[-1]), 2),
                         "rsi": round(float(indicator(df, "rsi", 14).iloc[-1]), 1), "ema20": round(float(indicator(df, "ema", 20).iloc[-1]), 2)})
        except Exception as e:
            errors.append({"symbol": sym, "error": str(e)[:120]})
    rows.sort(key=lambda r: (not r["match"], r["symbol"]))
    return {"data_source": source, "scanned": len(rows), "matches": sum(r["match"] for r in rows), "results": rows, "errors": errors}

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..brokers.factory import get_broker
from ..data import get_candles
from ..db import get_db
from ..deps import current_user
from ..engine.backtest import run_backtest
from ..engine.rules import validate_spec
from ..models import Backtest, BrokerAccount, Strategy, User

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


def resolve_data(db, user, exchange, source):
    """-> (source, client). auto: the user's OpenAlgo account for Indian exchanges, ccxt for CRYPTO, else demo data."""
    client = None
    if source == "recorded":
        return "recorded", None
    if source in ("auto", "openalgo") and exchange != "CRYPTO":
        a = db.scalar(select(BrokerAccount).where(BrokerAccount.user_id == user.id, BrokerAccount.kind == "openalgo"))
        if a:
            try:
                client = get_broker(db, a).history_client()
            except Exception:
                if source == "openalgo": raise HTTPException(403, "Broker data needs login on a hosted server. Turn on login in Settings.")
        elif source == "openalgo":
            raise HTTPException(400, "Add an OpenAlgo broker account first")
    if source == "auto":
        source = "crypto" if exchange == "CRYPTO" else ("openalgo" if client else "demo")
    return source, client


class BacktestIn(BaseModel):
    strategy_id: int | None = None
    spec: dict | None = None
    source: str = "auto"                       # auto | demo | openalgo | crypto
    bars: int = Field(default=1000, ge=60, le=5000)
    cost_bps: float = Field(default=5.0, ge=0, le=200)


def _summary(b: Backtest):
    return {
        "id": b.id,
        "name": b.name,
        "strategy_id": b.strategy_id,
        "metrics": b.metrics,
        "open_position": b.metrics.get("open_position") if isinstance(b.metrics, dict) else None,
        "created_at": b.created_at.isoformat(),
    }


@router.post("", status_code=201)
def run(b: BacktestIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if b.strategy_id:
        st = db.get(Strategy, b.strategy_id)
        if not st or st.user_id != u.id: raise HTTPException(404, "Strategy not found")
        spec, name = st.spec, st.name
    elif b.spec:
        spec, name = b.spec, "Ad-hoc test"
    else:
        raise HTTPException(400, "Provide strategy_id or spec")
    try:
        validate_spec(spec)
        source, client = resolve_data(db, u, spec["exchange"], b.source)
        df = get_candles(spec["symbol"], spec["exchange"], spec["interval"], b.bars, source, client, db=db)
        res = run_backtest(df, spec, b.cost_bps, spec["interval"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(422, f"Backtest failed: {e}")
    row = Backtest(user_id=u.id, strategy_id=b.strategy_id, name=name, params={"spec": spec, "source": source, "bars": b.bars, "cost_bps": b.cost_bps},
                   metrics={**res["metrics"], "data_source": source, "open_position": res["open_position"]},
                   equity=res["equity"], trades=res["trades"])
    db.add(row); db.commit()
    return {**_summary(row), "params": row.params, "equity": row.equity, "trades": row.trades}


@router.get("")
def list_(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_summary(b) for b in db.scalars(select(Backtest).where(Backtest.user_id == u.id).order_by(Backtest.id.desc()).limit(100))]


@router.get("/{bid}")
def get(bid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.get(Backtest, bid)
    if not b or b.user_id != u.id: raise HTTPException(404, "Backtest not found")
    return {**_summary(b), "params": b.params, "equity": b.equity, "trades": b.trades}


@router.delete("/{bid}", status_code=204)
def delete(bid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.get(Backtest, bid)
    if not b or b.user_id != u.id: raise HTTPException(404, "Backtest not found")
    db.delete(b); db.commit()

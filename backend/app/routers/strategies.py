from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import current_user, owned_account
from ..engine.rules import TEMPLATES, validate_spec
from ..models import Strategy, User
from ..policy import live_allowed

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class StrategyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    spec: dict


def _out(s: Strategy):
    return {"id": s.id, "name": s.name, "spec": s.spec, "mode": s.mode, "account_id": s.account_id, "last_target": s.last_target,
            "last_run": s.last_run.isoformat() if s.last_run else None, "created_at": s.created_at.isoformat()}


def _check(spec):
    try:
        return validate_spec(spec)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(422, f"Invalid strategy: {e}")


def _own(db, u, sid) -> Strategy:
    s = db.get(Strategy, sid)
    if not s or s.user_id != u.id: raise HTTPException(404, "Strategy not found")
    return s


@router.get("/templates")
def templates(_: User = Depends(current_user)):
    return TEMPLATES


@router.get("")
def list_(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_out(s) for s in db.scalars(select(Strategy).where(Strategy.user_id == u.id).order_by(Strategy.id.desc()))]


@router.post("", status_code=201)
def create(b: StrategyIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    s = Strategy(user_id=u.id, name=b.name, spec=_check(b.spec)); db.add(s); db.commit(); return _out(s)


@router.get("/{sid}")
def get(sid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(_own(db, u, sid))


@router.put("/{sid}")
def update(sid: int, b: StrategyIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _own(db, u, sid)
    if s.mode != "off": raise HTTPException(409, "Turn the strategy off before editing it")
    s.name, s.spec = b.name, _check(b.spec); db.commit(); return _out(s)


@router.delete("/{sid}", status_code=204)
def delete(sid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own(db, u, sid)); db.commit()


class Mode(BaseModel):
    mode: str
    account_id: int | None = None


@router.patch("/{sid}/mode")
def set_mode(sid: int, b: Mode, u: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _own(db, u, sid)
    if b.mode not in ("off", "paper", "live"): raise HTTPException(400, "mode must be off, paper or live")
    if b.mode == "live":
        if not live_allowed(db): raise HTTPException(403, "Live trading needs login. Turn on login in Settings first.")
        if not b.account_id: raise HTTPException(400, "live mode needs a broker account_id")
        a = owned_account(db, u, b.account_id)
        if a.kind == "paper" or not a.live_enabled: raise HTTPException(400, "that broker account is not enabled for live trading")
        s.account_id = a.id
    s.mode = b.mode; db.commit(); return _out(s)

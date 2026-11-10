from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..models import User
from ..policy import auth_required, brokers_allowed, live_allowed, set_auth_required
from ..security import hash_password, verify_password

router = APIRouter(prefix="/api/app", tags=["app"])


@router.get("/config")
def config(db: Session = Depends(get_db)):
    """Public: the web app reads this first to know whether to show a login screen."""
    s = get_settings(); req = auth_required(db)
    return {"mode": "login" if req else "open", "auth_required": req, "env": s.env, "allow_registration": s.allow_registration,
            "brokers_available": brokers_allowed(db), "live_available": live_allowed(db), "live_trading_enabled_on_server": s.live_trading_enabled}


class AuthChange(BaseModel):
    required: bool
    email: EmailStr | None = None
    password: str | None = Field(default=None, max_length=128)


@router.put("/auth")
def change_auth(b: AuthChange, u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Turn login on or off from inside the app. Turning ON sets the owner's email and password first, so you cannot lock yourself out.
    Turning OFF needs the current admin's password."""
    if u.role != "admin": raise HTTPException(403, "Admin only")
    if b.required:
        if auth_required(db): return {"auth_required": True}
        if not b.email or not b.password or len(b.password) < 8:
            raise HTTPException(422, "Choose an email and a password of at least 8 characters for the owner account before turning login on")
        taken = db.scalar(select(User).where(User.email == b.email.lower(), User.id != u.id))
        if taken: raise HTTPException(409, "That email is already used by another account")
        u.email, u.password_hash, u.is_active = b.email.lower(), hash_password(b.password), True
        set_auth_required(db, True); db.commit()
        return {"auth_required": True, "owner_email": u.email}
    if not auth_required(db): return {"auth_required": False}
    if not b.password or not verify_password(b.password, u.password_hash): raise HTTPException(403, "Wrong password")
    set_auth_required(db, False); db.commit()
    return {"auth_required": False}

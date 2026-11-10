import time
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..models import User
from ..security import hash_password, make_token, verify_password

router = APIRouter(prefix="/api", tags=["auth"])
_fails: dict[str, list[float]] = {}   # per-process login throttle; use Redis/proxy rate limits across processes


class Register(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=120)


class Login(BaseModel):
    email: EmailStr
    password: str


def _user_out(u: User):
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role}


@router.post("/accounts/register", status_code=201)
def register(b: Register, db: Session = Depends(get_db)):
    s = get_settings()
    if not s.allow_registration:
        raise HTTPException(403, "Registration is closed")
    email = b.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    u = User(email=email, name=b.name, password_hash=hash_password(b.password), role="admin" if s.admin_email and email == s.admin_email.lower() else "user")
    db.add(u); db.commit()
    return {"token": make_token(u.id, u.role), "user": _user_out(u)}


@router.post("/accounts/login")
def login(b: Login, request: Request, db: Session = Depends(get_db)):
    key = f"{request.client.host if request.client else '?'}:{b.email.lower()}"; now = time.time()
    recent = [t for t in _fails.get(key, []) if now - t < 300]
    if len(recent) >= 8:
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    u = db.scalar(select(User).where(User.email == b.email.lower()))
    if not u or not u.is_active or not verify_password(b.password, u.password_hash):
        _fails[key] = recent + [now]
        raise HTTPException(401, "Invalid email or password")
    _fails.pop(key, None)
    return {"token": make_token(u.id, u.role), "user": _user_out(u)}


@router.get("/me")
def me(u: User = Depends(current_user)):
    return _user_out(u)


class Profile(BaseModel):
    name: str = Field(max_length=120)


@router.patch("/me")
def update_me(b: Profile, u: User = Depends(current_user), db: Session = Depends(get_db)):
    u.name = b.name; db.commit(); return _user_out(u)


class Password(BaseModel):
    current: str
    new: str = Field(min_length=8, max_length=128)


@router.post("/me/password")
def change_password(b: Password, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(b.current, u.password_hash):
        raise HTTPException(400, "Current password is wrong")
    u.password_hash = hash_password(b.new); db.commit(); return {"ok": True}

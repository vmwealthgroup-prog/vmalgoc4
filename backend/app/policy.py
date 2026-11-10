"""Access policy. Two modes:
  open   (default): no login. Everyone who can reach the server is the single 'owner' admin. Paper trading, backtests and scanners only.
  login:  accounts and passwords required (multi-user).
Guardrails: real-money trading ALWAYS needs login; on a production (hosted) server broker connections also need login."""
import secrets
from sqlalchemy import select
from .config import get_settings
from .models import AppSetting, User
from .security import hash_password

OWNER_EMAIL = "owner@local"


def auth_required(db) -> bool:
    row = db.get(AppSetting, "auth_required")
    return (row.value == "1") if row else get_settings().auth_required


def set_auth_required(db, flag: bool):
    row = db.get(AppSetting, "auth_required")
    if row is None:
        db.add(AppSetting(key="auth_required", value="1" if flag else "0"))
    else:
        row.value = "1" if flag else "0"


def live_allowed(db) -> bool:
    return auth_required(db)


def brokers_allowed(db) -> bool:
    return auth_required(db) or get_settings().env != "production"


def ensure_owner(db) -> User:
    u = db.scalar(select(User).where(User.role == "admin").order_by(User.id).limit(1))
    if u is None:
        u = User(email=OWNER_EMAIL, name="Owner", role="admin", password_hash=hash_password(secrets.token_hex(24)))   # unusable until a password is set
        db.add(u); db.flush()
    return u

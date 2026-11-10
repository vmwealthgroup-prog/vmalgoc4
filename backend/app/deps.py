from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .db import get_db
from .models import BrokerAccount, User
from .policy import auth_required, ensure_owner
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not auth_required(db):                      # open mode: no login, single owner
        o = ensure_owner(db); db.commit(); return o
    if cred is None:
        raise HTTPException(401, "Not authenticated")
    try:
        uid = int(decode_token(cred.credentials)["sub"])
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    u = db.get(User, uid)
    if u is None or not u.is_active:
        raise HTTPException(401, "Account disabled or missing")
    return u


def admin_user(u: User = Depends(current_user)) -> User:
    if u.role != "admin":
        raise HTTPException(403, "Admin only")
    return u


def owned_account(db: Session, user: User, account_id: int) -> BrokerAccount:
    a = db.get(BrokerAccount, account_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Broker account not found")
    return a

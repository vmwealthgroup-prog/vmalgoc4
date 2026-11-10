from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import admin_user
from ..models import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def users(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [{"id": u.id, "email": u.email, "name": u.name, "role": u.role, "is_active": u.is_active, "created_at": u.created_at.isoformat()} for u in db.scalars(select(User).order_by(User.id))]


class Patch(BaseModel):
    role: str | None = None
    is_active: bool | None = None


@router.patch("/users/{uid}")
def patch(uid: int, b: Patch, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u: raise HTTPException(404, "User not found")
    if u.id == admin.id: raise HTTPException(400, "You cannot change your own role or status")
    if b.role is not None:
        if b.role not in ("user", "admin"): raise HTTPException(400, "role must be user or admin")
        u.role = b.role
    if b.is_active is not None: u.is_active = b.is_active
    db.commit(); return {"id": u.id, "role": u.role, "is_active": u.is_active}

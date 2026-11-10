"""Liveness markers in app_settings so the API (a different process from the worker) can show whether feed and runner are alive."""
from datetime import datetime, timezone
from .models import AppSetting


def beat(db, name: str):
    row = db.get(AppSetting, f"hb:{name}")
    stamp = datetime.now(timezone.utc).isoformat()
    if row is None: db.add(AppSetting(key=f"hb:{name}", value=stamp))
    else: row.value = stamp
    db.commit()


def put(db, key: str, value: str):
    row = db.get(AppSetting, key)
    if row is None: db.add(AppSetting(key=key, value=value[:255]))
    else: row.value = value[:255]
    db.commit()


def get(db, key: str):
    row = db.get(AppSetting, key)
    return row.value if row else None


def age_seconds(db, name: str):
    row = db.get(AppSetting, f"hb:{name}")
    if row is None:
        return None
    return round((datetime.now(timezone.utc) - datetime.fromisoformat(row.value)).total_seconds(), 1)

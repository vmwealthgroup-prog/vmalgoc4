"""Exchange sessions (IST). Holidays come from MARKET_HOLIDAYS because exchange calendars change every year and must be maintained by you."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from .config import get_settings

IST = ZoneInfo("Asia/Kolkata")
SESSIONS = {"NSE": ("09:15", "15:30"), "BSE": ("09:15", "15:30"), "NFO": ("09:15", "15:30"), "BFO": ("09:15", "15:30"), "MCX": ("09:00", "23:30")}
INDIAN_INTRADAY = {"NSE", "BSE", "NFO", "BFO"}


def holidays() -> set[date]:
    out = set()
    for p in get_settings().market_holidays.split(","):
        p = p.strip()
        if p:
            out.add(date.fromisoformat(p))
    return out


def is_open(exchange: str, now: datetime | None = None) -> bool:
    ex = exchange.upper()
    if ex == "CRYPTO":
        return True
    if ex not in SESSIONS:
        return False
    t = (now or datetime.now(IST)).astimezone(IST)
    if t.weekday() >= 5 or t.date() in holidays():
        return False
    start, end = SESSIONS[ex]
    return start <= t.strftime("%H:%M") <= end


def square_off_due(exchange: str, product: str, spec_time: str | None = None, now: datetime | None = None) -> bool:
    """True from the square-off time on, for intraday (MIS) positions on Indian exchanges."""
    if exchange.upper() not in INDIAN_INTRADAY or product.upper() != "MIS":
        return False
    t = (now or datetime.now(IST)).astimezone(IST)
    return t.strftime("%H:%M") >= (spec_time or get_settings().square_off_time)

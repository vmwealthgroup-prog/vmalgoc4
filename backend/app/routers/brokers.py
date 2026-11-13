import json
from datetime import datetime
from zoneinfo import ZoneInfo
import ccxt
from fastapi import APIRouter, Depends, HTTPException
import re
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..brokers import kite, kotak_neo_auth, kotak_neo_data
from ..brokers.base import BrokerError
from ..brokers.factory import ensure_paper_account, get_broker, live_account_error
from ..config import get_settings
from ..db import get_db
from ..deps import current_user, owned_account
from ..models import BrokerAccount, User
from ..policy import brokers_allowed, live_allowed
from ..security import decrypt, encrypt, verify_password

router = APIRouter(prefix="/api/brokers", tags=["brokers"])


def _out(a: BrokerAccount):
    d = {"id": a.id, "kind": a.kind, "label": a.label, "broker_name": a.broker_name, "host": a.host, "live_enabled": a.live_enabled, "has_key": bool(a.api_key_enc), "token_ok": None}
    if a.kind == "ccxt":
        try: c = json.loads(decrypt(a.api_key_enc)); d["crypto"] = {"trade": bool(c.get("trade")), "sandbox": bool(c.get("sandbox"))}
        except Exception: d["crypto"] = None
    if a.kind == "kite":
        try: d["token_ok"] = kite.token_ok(json.loads(decrypt(a.api_key_enc)))     # Zerodha needs a fresh login every trading day
        except Exception: d["token_ok"] = False
    if a.kind == "kotak_neo":
        try:
            creds = json.loads(decrypt(a.api_key_enc))
            d["token_ok"] = bool(creds.get("trade_token") and creds.get("trade_sid") and creds.get("base_url") and creds.get("token_date") == datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat())
            d["auth_stage"] = "connected" if d["token_ok"] else ("view_session" if creds.get("view_token") else "not_logged_in")
        except Exception:
            d["token_ok"] = False
            d["auth_stage"] = "credential_error"
    return d



@router.get("/accounts")
def accounts(u: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_paper_account(db, u); db.commit()
    return [_out(a) for a in db.scalars(select(BrokerAccount).where(BrokerAccount.user_id == u.id).order_by(BrokerAccount.id))]


@router.delete("/accounts/{aid}", status_code=204)
def delete(aid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned_account(db, u, aid)
    if a.kind == "paper": raise HTTPException(400, "The paper account cannot be deleted")
    db.delete(a); db.commit()


@router.post("/accounts/{aid}/test")
def test(aid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned_account(db, u, aid)
    if a.kind == "openalgo": raise HTTPException(410, "OpenAlgo integration has been removed. This legacy account can only be deleted.")
    try:
        return {"ok": True, "funds": get_broker(db, a).funds()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


class Live(BaseModel):
    enabled: bool
    password: str


@router.patch("/accounts/{aid}/live")
def live(aid: int, b: Live, u: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned_account(db, u, aid)
    if b.enabled and not live_allowed(db): raise HTTPException(403, "Live trading needs login. Turn on login in Settings first.")
    if b.enabled:
        reason = live_account_error(a)
        if reason: raise HTTPException(400, reason)
    if a.kind == "paper": raise HTTPException(400, "Paper accounts are always paper")
    if b.enabled and not get_settings().live_trading_enabled:
        raise HTTPException(400, "Live trading is switched off on this server (LIVE_TRADING_ENABLED=false)")
    if not verify_password(b.password, u.password_hash): raise HTTPException(403, "Wrong password")
    a.live_enabled = b.enabled; db.commit(); return _out(a)


# ---------------- direct Zerodha (official kiteconnect client) with the daily login
class KiteIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    api_key: str = Field(min_length=6, max_length=100)
    api_secret: str = Field(min_length=6, max_length=100)


@router.post("/accounts/kite", status_code=201)
def add_kite(b: KiteIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not brokers_allowed(db): raise HTTPException(403, "Broker connections need login on a hosted server. Turn on login in Settings.")
    a = BrokerAccount(user_id=u.id, kind="kite", label=b.label, broker_name="zerodha", host="https://kite.zerodha.com",
                      api_key_enc=encrypt(json.dumps({"api_key": b.api_key.strip(), "api_secret": b.api_secret.strip()})))
    db.add(a); db.commit(); return _out(a)


def _kite(db, u, aid):
    if not brokers_allowed(db): raise HTTPException(403, "Broker connections need login on a hosted server. Turn on login in Settings.")
    a = owned_account(db, u, aid)
    if a.kind != "kite": raise HTTPException(400, "This is not a Zerodha (Kite) account")
    return a, json.loads(decrypt(a.api_key_enc))


@router.get("/accounts/{aid}/kite/login-url")
def kite_login_url(aid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    a, creds = _kite(db, u, aid)
    return {"url": kite.login_url(creds["api_key"], a.id)}


class KiteSession(BaseModel):
    request_token: str = Field(min_length=6, max_length=120)


@router.post("/accounts/{aid}/kite/session")
def kite_session(aid: int, b: KiteSession, u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Finish the daily login: exchange the request_token Zerodha sent back for today's access token (stored encrypted)."""
    a, creds = _kite(db, u, aid)
    try:
        creds["access_token"] = kite.exchange_request_token(creds["api_key"], creds["api_secret"], b.request_token.strip())
    except BrokerError as e:
        raise HTTPException(400, str(e))
    creds["token_date"] = kite.today(); a.api_key_enc = encrypt(json.dumps(creds)); db.commit()
    return _out(a)


# ---------------- read-only crypto exchange account (ccxt)
class CryptoIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    exchange: str = Field(max_length=40)
    api_key: str = Field(min_length=4, max_length=200)
    api_secret: str = Field(min_length=4, max_length=500)
    password: str = Field(default="", max_length=200)
    quote: str = Field(default="USDT", max_length=10)
    sandbox: bool = False            # use the exchange's test network (no real money)
    trade: bool = False              # False = read-only (balances only). True = may place orders (still needs live trading enabled)


@router.post("/accounts/crypto", status_code=201)
def add_crypto(b: CryptoIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not brokers_allowed(db): raise HTTPException(403, "Broker connections need login on a hosted server. Turn on login in Settings.")
    if b.exchange not in ccxt.exchanges: raise HTTPException(422, "unknown exchange (use a ccxt exchange id such as coinbase, kraken, bybit, okx)")
    if b.sandbox:
        try: getattr(ccxt, b.exchange)().set_sandbox_mode(True)
        except Exception: raise HTTPException(422, "This exchange has no test network in ccxt. Untick test mode, or pick an exchange that has one (for example binance, bybit, okx).")
    a = BrokerAccount(user_id=u.id, kind="ccxt", label=b.label, broker_name=b.exchange, host="", api_key_enc=encrypt(json.dumps(b.model_dump())))
    db.add(a); db.commit(); return _out(a)


# ---------------- Kotak Neo direct API (TOTP -> MPIN). MPIN/TOTP are request-only.
class KotakNeoAccountIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    consumer_key: str = Field(min_length=12, max_length=300)
    mobile_number: str = Field(min_length=10, max_length=20)
    ucc: str = Field(min_length=2, max_length=40)

    @field_validator("mobile_number")
    @classmethod
    def normalize_mobile_number(cls, value: str) -> str:
        compact = re.sub(r"[^0-9+]", "", value.strip())
        digits = compact.lstrip("+")
        if len(digits) == 10:
            return "+91" + digits
        if len(digits) == 12 and digits.startswith("91"):
            return "+" + digits
        if compact.startswith("+") and 10 <= len(digits) <= 15:
            return "+" + digits
        raise ValueError("Enter a valid mobile number with country code, e.g. +919876543210")


def _kotak_neo(db, u, aid):
    if not brokers_allowed(db):
        raise HTTPException(403, "Broker connections need login on a hosted server. Turn on login in Settings.")
    account = owned_account(db, u, aid)
    if account.kind != "kotak_neo":
        raise HTTPException(400, "This is not a Kotak Neo account")
    try:
        creds = json.loads(decrypt(account.api_key_enc))
    except Exception:
        raise HTTPException(500, "Could not read encrypted Kotak Neo credentials")
    # Normalize older saved 10-digit Indian numbers too; Kotak's SDK requires country code.
    mobile = re.sub(r"[^0-9+]", "", str(creds.get("mobile_number", "")).strip())
    digits = mobile.lstrip("+")
    if len(digits) == 10:
        creds["mobile_number"] = "+91" + digits
    elif len(digits) == 12 and digits.startswith("91"):
        creds["mobile_number"] = "+" + digits
    return account, creds


@router.post("/accounts/kotak-neo", status_code=201)
def add_kotak_neo(b: KotakNeoAccountIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not brokers_allowed(db):
        raise HTTPException(403, "Broker connections need login on a hosted server. Turn on login in Settings.")
    creds = {
        "consumer_key": b.consumer_key.strip(),
        "mobile_number": b.mobile_number,
        "ucc": b.ucc.strip().upper(),
    }
    account = BrokerAccount(
        user_id=u.id, kind="kotak_neo", label=b.label,
        broker_name="kotak_neo", host="https://mis.kotaksecurities.com",
        api_key_enc=encrypt(json.dumps(creds)),
        live_enabled=False,
    )
    db.add(account)
    db.commit()
    return _out(account)


class KotakNeoTotpIn(BaseModel):
    totp: str = Field(pattern=r"^[0-9]{6}$")


@router.post("/accounts/{aid}/kotak-neo/totp")
def kotak_neo_totp(aid: int, b: KotakNeoTotpIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    account, creds = _kotak_neo(db, u, aid)
    try:
        view = kotak_neo_auth.totp_login(creds["consumer_key"], creds["mobile_number"], creds["ucc"], b.totp)
    except kotak_neo_auth.KotakNeoAuthError as exc:
        raise HTTPException(400, str(exc))
    creds.pop("trade_token", None)
    creds.pop("trade_sid", None)
    creds.pop("base_url", None)
    creds.update(view)
    account.api_key_enc = encrypt(json.dumps(creds))
    account.live_enabled = False
    db.commit()
    return {"ok": True, "stage": "view_session", "message": "TOTP accepted. Complete the second step with your MPIN."}


class KotakNeoMpinIn(BaseModel):
    mpin: str = Field(pattern=r"^[0-9]{6}$")


@router.post("/accounts/{aid}/kotak-neo/mpin")
def kotak_neo_mpin(aid: int, b: KotakNeoMpinIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    account, creds = _kotak_neo(db, u, aid)
    if not creds.get("view_token") or not creds.get("view_sid"):
        raise HTTPException(409, "Complete TOTP login first.")
    try:
        session = kotak_neo_auth.mpin_validate(
            creds["consumer_key"], creds["view_token"], creds["view_sid"], b.mpin
        )
    except kotak_neo_auth.KotakNeoAuthError as exc:
        raise HTTPException(400, str(exc))
    creds.pop("view_token", None)
    creds.pop("view_sid", None)
    creds.update(session)
    creds["token_date"] = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    account.api_key_enc = encrypt(json.dumps(creds))
    account.live_enabled = False
    db.commit()
    return {"ok": True, "stage": "connected", "message": "Kotak Neo session established. Live order execution remains disabled."}


@router.get("/accounts/{aid}/kotak-neo/status")
def kotak_neo_status(aid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    account, creds = _kotak_neo(db, u, aid)
    connected = bool(creds.get("trade_token") and creds.get("trade_sid") and creds.get("base_url") and creds.get("token_date") == datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat())
    return {
        "id": account.id,
        "connected": connected,
        "stage": "connected" if connected else ("view_session" if creds.get("view_token") else "not_logged_in"),
        "live_enabled": False,
    }



@router.get("/accounts/{aid}/kotak-neo/snapshot")
def kotak_neo_snapshot(aid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    account, creds = _kotak_neo(db, u, aid)
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    if creds.get("token_date") != today or not creds.get("trade_token"):
        raise HTTPException(401, "Kotak Neo session expired. Complete TOTP and MPIN login again.")
    try:
        return kotak_neo_data.account_snapshot(creds)
    except kotak_neo_data.KotakNeoDataError as exc:
        raise HTTPException(502, str(exc))



class KotakNeoScripSearchIn(BaseModel):
    exchange_segment: str = Field(min_length=3, max_length=16)
    symbol: str = Field(min_length=1, max_length=40)


class KotakNeoInstrumentIn(BaseModel):
    instrument_token: str = Field(min_length=1, max_length=24)
    exchange_segment: str = Field(min_length=3, max_length=16)


class KotakNeoQuotesIn(BaseModel):
    instruments: list[KotakNeoInstrumentIn] = Field(min_length=1, max_length=50)
    quote_type: str = Field(default="all", max_length=20)


@router.post("/accounts/{aid}/kotak-neo/scrip-search")
def kotak_neo_scrip_search(aid: int, b: KotakNeoScripSearchIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    _, creds = _kotak_neo(db, u, aid)
    try:
        return kotak_neo_data.search_scrip(creds, b.exchange_segment, b.symbol)
    except kotak_neo_data.KotakNeoDataError as exc:
        raise HTTPException(422, str(exc))


@router.post("/accounts/{aid}/kotak-neo/quotes")
def kotak_neo_quotes(aid: int, b: KotakNeoQuotesIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    _, creds = _kotak_neo(db, u, aid)
    try:
        return kotak_neo_data.quotes(
            creds,
            [item.model_dump() for item in b.instruments],
            b.quote_type,
        )
    except kotak_neo_data.KotakNeoDataError as exc:
        raise HTTPException(422, str(exc))

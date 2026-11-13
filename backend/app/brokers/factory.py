from sqlalchemy import select
from ..models import BrokerAccount, RiskLimits, User
from ..security import decrypt
from ..policy import brokers_allowed
from .base import Broker, BrokerError
import json
from .crypto import CcxtAdapter
from .kite import KiteAdapter, token_ok as kite_token_ok
from .paper import PaperBroker


def live_account_error(account: BrokerAccount) -> str | None:
    """Return a fail-closed reason when an account is not eligible for automated live execution."""
    if account.kind == "paper":
        return "live mode requires a supported broker account"
    if account.kind == "openalgo":
        return "OpenAlgo accounts are no longer supported; connect a supported broker directly"
    if account.kind == "kotak_neo":
        return "Kotak Neo automated execution is disabled until its live adapter is validated"
    if not account.live_enabled:
        return "live trading is not enabled for this broker account"
    try:
        creds = json.loads(decrypt(account.api_key_enc))
    except Exception:
        return "broker credentials could not be decrypted or are invalid"
    if account.kind == "kite":
        if not kite_token_ok(creds):
            return "Zerodha session is missing or expired; complete today's broker login"
        return None
    if account.kind == "ccxt":
        if creds.get("trade") is not True:
            return "crypto account is read-only; explicit trading permission is required"
        return None
    return f"automated live trading is not supported for account kind: {account.kind}"


def get_broker(db, account: BrokerAccount) -> Broker:
    if account.kind == "paper":
        return PaperBroker(db, account)
    if account.kind == "openalgo":
        raise BrokerError("OpenAlgo integration has been removed; this legacy account can only be deleted")
    if account.kind in ("kite", "ccxt"):
        if not brokers_allowed(db):
            raise BrokerError("Broker connections need login on a hosted server. Turn on login in Settings.")
        creds = json.loads(decrypt(account.api_key_enc))
        return KiteAdapter(creds) if account.kind == "kite" else CcxtAdapter(creds, db=db, account_id=account.id)
    raise ValueError(f"unsupported account kind {account.kind}")


def ensure_paper_account(db, user: User) -> BrokerAccount:
    a = db.scalar(select(BrokerAccount).where(BrokerAccount.user_id == user.id, BrokerAccount.kind == "paper"))
    if a is None:
        a = BrokerAccount(user_id=user.id, kind="paper", label="Paper account"); db.add(a); db.flush()
    return a


def ensure_limits(db, user_id: int) -> RiskLimits:
    r = db.get(RiskLimits, user_id)
    if r is None:
        r = RiskLimits(user_id=user_id, blocked=[]); db.add(r); db.flush()
    return r

from sqlalchemy import select
from ..models import BrokerAccount, RiskLimits, User
from ..security import decrypt
from ..policy import brokers_allowed
from .base import Broker, BrokerError
import json
from .crypto import CcxtAdapter
from .kite import KiteAdapter
from .openalgo import OpenAlgoAdapter
from .paper import PaperBroker

# Informational: brokers supported by OpenAlgo (from its VALID_BROKERS list). Availability depends on your OpenAlgo setup.
SUPPORTED_BROKERS = ("zerodha angel upstox dhan fyers kotak fivepaisa fivepaisaxts aliceblue arrow compositedge definedge deltaexchange firstock "
                     "flattrade groww hdfcsecurities hdfcsky ibulls iifl iiflcapital indmoney jainamxts motilal mstock nubra paytm pocketful "
                     "rmoney rupeezy samco shoonya tradejini tradesmart wisdom zebu dhan_sandbox").split()


def get_broker(db, account: BrokerAccount) -> Broker:
    if account.kind == "paper":
        return PaperBroker(db, account)
    if account.kind == "openalgo":
        if not brokers_allowed(db):
            raise BrokerError("Broker connections need login on a hosted server. Turn on login in Settings.")
        return OpenAlgoAdapter(account.host, decrypt(account.api_key_enc))
    if account.kind in ("kite", "ccxt"):
        if not brokers_allowed(db):
            raise BrokerError("Broker connections need login on a hosted server. Turn on login in Settings.")
        creds = json.loads(decrypt(account.api_key_enc))
        return KiteAdapter(creds) if account.kind == "kite" else CcxtAdapter(creds, db=db, account_id=account.id)
    raise ValueError(f"unknown account kind {account.kind}")


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

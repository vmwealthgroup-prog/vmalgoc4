import os, sys, pathlib
DB = "/tmp/vmalgo_test.db"
if os.path.exists(DB): os.remove(DB)
os.environ.update(DATABASE_URL=os.environ.get("TEST_DATABASE_URL", f"sqlite:///{DB}"), FEED_IN_API="false", REDIS_URL="", SECRET_KEY="test-secret-key-test-secret-key-123456", ADMIN_EMAIL="boss@example.com",
                  LIVE_TRADING_ENABLED="false", AUTH_REQUIRED="true", ENFORCE_MARKET_HOURS="false", CRYPTO_FEED="demo", MAX_ORDERS_PER_SECOND="50", ENV="development", OPENALGO_ALLOWED_HOSTS="")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
from app.db import Base, engine
from app.main import app
from app.pubsub import MemoryPubSub, set_pubsub


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine); set_pubsub(MemoryPubSub())
    with TestClient(app) as c:
        yield c


def signup(c, email="a@example.com", pw="password123"):
    r = c.post("/api/accounts/register", json={"email": email, "password": pw, "name": "T"}); assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def h(client):
    return signup(client)


EMA = {"symbol": "RELIANCE", "exchange": "NSE", "interval": "5m", "entry": {"all": [{"left": {"ind": "ema", "period": 9}, "op": "crosses_above", "right": {"ind": "ema", "period": 21}}]},
       "exit": {"all": [{"left": {"ind": "ema", "period": 9}, "op": "crosses_below", "right": {"ind": "ema", "period": 21}}]}}
ALWAYS = {"symbol": "TCS", "exchange": "NSE", "interval": "5m", "risk": {"qty": 3}, "entry": {"all": [{"left": {"ind": "close"}, "op": ">", "right": {"value": 0}}]}}

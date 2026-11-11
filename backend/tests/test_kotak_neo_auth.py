import pytest

from app.brokers import kotak_neo_auth as auth
from app.brokers import kotak_neo_data as data


class FakeConfig:
    def __init__(self):
        self.view_token = None
        self.sid = None


class FakeClient:
    def __init__(self, **kwargs):
        self.configuration = FakeConfig()
        self.kwargs = kwargs
        self.login_result = {"data": {"status": "success", "token": "view-token", "sid": "view-sid"}}
        self.validate_result = {"data": {
            "status": "success", "token": "trade-token", "sid": "trade-sid",
            "rid": "request-id", "baseUrl": "https://cis.kotaksecurities.com",
            "dataCenter": "E21", "ucc": "UCC1"
        }}
    def totp_login(self, **kwargs):
        self.login_args = kwargs
        return self.login_result
    def totp_validate(self, **kwargs):
        self.validate_args = kwargs
        return self.validate_result


def test_totp_login_uses_official_sdk(monkeypatch):
    clients = []
    monkeypatch.setattr(auth, "NeoAPI", lambda **kw: clients.append(FakeClient(**kw)) or clients[-1])
    result = auth.totp_login("consumer-key", "+919999999999", "UCC1", "123456")
    assert result == {"view_token": "view-token", "view_sid": "view-sid"}
    assert clients[0].kwargs == {"consumer_key": "consumer-key", "environment": "prod"}
    assert clients[0].login_args == {"mobile_number": "+919999999999", "ucc": "UCC1", "totp": "123456"}


def test_mpin_validate_uses_view_session_and_returns_trade_session(monkeypatch):
    clients = []
    monkeypatch.setattr(auth, "NeoAPI", lambda **kw: clients.append(FakeClient(**kw)) or clients[-1])
    result = auth.mpin_validate("consumer-key", "view-token", "view-sid", "654321")
    assert clients[0].configuration.view_token == "view-token"
    assert clients[0].configuration.sid == "view-sid"
    assert clients[0].validate_args == {"mpin": "654321"}
    assert result["trade_token"] == "trade-token"
    assert result["trade_sid"] == "trade-sid"
    assert result["trade_rid"] == "request-id"
    assert result["data_center"] == "E21"


def test_authentication_rejects_unsuccessful_response(monkeypatch):
    client = FakeClient()
    client.login_result = {"error": [{"message": "Invalid TOTP"}]}
    monkeypatch.setattr(auth, "NeoAPI", lambda **kw: client)
    with pytest.raises(auth.KotakNeoAuthError, match="Invalid TOTP"):
        auth.totp_login("consumer-key", "+919999999999", "UCC1", "123456")


def test_data_adapter_only_invokes_read_methods(monkeypatch):
    calls = []
    class ReadClient:
        def limits(self): calls.append("limits"); return {"stat": "Ok"}
        def holdings(self): calls.append("holdings"); return {"data": []}
        def positions(self): calls.append("positions"); return {"data": []}
        def order_report(self): calls.append("order_report"); return {"data": []}
        def trade_report(self): calls.append("trade_report"); return {"data": []}
    monkeypatch.setattr(data, "build_client", lambda _: ReadClient())
    snapshot = data.account_snapshot({
        "consumer_key": "key", "trade_token": "token", "trade_sid": "sid",
        "base_url": "https://cis.kotaksecurities.com"
    })
    assert all(snapshot[k]["ok"] for k in ("funds", "holdings", "positions", "orders", "trades"))
    assert calls == ["limits", "holdings", "positions", "order_report", "trade_report"]


def test_data_adapter_reports_partial_failures_without_exposing_exception(monkeypatch):
    class ReadClient:
        def limits(self): raise RuntimeError("sensitive upstream detail")
        def holdings(self): return {"data": []}
        def positions(self): return {"data": []}
        def order_report(self): return {"data": []}
        def trade_report(self): return {"data": []}
    monkeypatch.setattr(data, "build_client", lambda _: ReadClient())
    snapshot = data.account_snapshot({})
    assert snapshot["funds"]["ok"] is False
    assert "sensitive upstream detail" not in snapshot["funds"]["error"]
    assert snapshot["holdings"]["ok"] is True

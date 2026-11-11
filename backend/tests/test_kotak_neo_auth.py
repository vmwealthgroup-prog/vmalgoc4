import pytest

from app.brokers import kotak_neo_auth as neo


class FakeResponse:
    def __init__(self, body):
        self._body = body
    def raise_for_status(self):
        return None
    def json(self):
        return self._body


def test_totp_login_uses_documented_headers_and_payload(monkeypatch):
    seen = {}
    def fake_post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse({"data": {"status": "success", "token": "view-token", "sid": "view-sid"}})
    monkeypatch.setattr(neo.httpx, "post", fake_post)

    result = neo.totp_login("consumer", "+919999999999", "UCC1", "123456")

    assert result == {"view_token": "view-token", "view_sid": "view-sid"}
    assert seen["url"].endswith("/login/1.0/tradeApiLogin")
    assert seen["headers"]["Authorization"] == "consumer"
    assert seen["headers"]["neo-fin-key"] == "neotradeapi"
    assert seen["json"] == {"mobileNumber": "+919999999999", "ucc": "UCC1", "totp": "123456"}


def test_mpin_validate_returns_trade_session(monkeypatch):
    seen = {}
    def fake_post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse({"data": {
            "status": "success", "token": "trade-token", "sid": "trade-sid",
            "baseUrl": "https://cis.kotaksecurities.com"
        }})
    monkeypatch.setattr(neo.httpx, "post", fake_post)

    result = neo.mpin_validate("consumer", "view-token", "view-sid", "654321")

    assert result == {
        "trade_token": "trade-token", "trade_sid": "trade-sid",
        "base_url": "https://cis.kotaksecurities.com"
    }
    assert seen["url"].endswith("/login/1.0/tradeApiValidate")
    assert seen["headers"]["Auth"] == "view-token"
    assert seen["headers"]["sid"] == "view-sid"
    assert seen["json"] == {"mpin": "654321"}


def test_mpin_rejects_untrusted_base_url(monkeypatch):
    monkeypatch.setattr(
        neo.httpx, "post",
        lambda *a, **k: FakeResponse({"data": {
            "status": "success", "token": "trade-token", "sid": "trade-sid",
            "baseUrl": "https://attacker.example"
        }}),
    )
    with pytest.raises(neo.KotakNeoAuthError, match="valid trading session"):
        neo.mpin_validate("consumer", "view-token", "view-sid", "654321")


def test_authentication_error_does_not_leak_upstream_response(monkeypatch):
    monkeypatch.setattr(
        neo.httpx, "post",
        lambda *a, **k: FakeResponse({"status": "error", "message": "Invalid MPIN."}),
    )
    with pytest.raises(neo.KotakNeoAuthError, match="Invalid MPIN"):
        neo.mpin_validate("consumer", "view-token", "view-sid", "654321")

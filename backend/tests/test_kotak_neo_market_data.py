from app.brokers import kotak_neo_data as data


class FakeClient:
    def __init__(self):
        self.search_args = None
        self.quote_args = None
    def search_scrip(self, **kwargs):
        self.search_args = kwargs
        return {"data": [{"pSymbol": "2885", "pTrdSymbol": "RELIANCE-EQ"}]}
    def quotes(self, **kwargs):
        self.quote_args = kwargs
        return [{"ltp": "1234.5"}]


def test_quote_validates_instrument_and_calls_official_sdk(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(data, "_client", lambda _: client)
    result = data.quotes(
        {"consumer_key": "key"},
        [{"instrument_token": "2885", "exchange_segment": "nse_cm"}],
        "all",
    )
    assert result == [{"ltp": "1234.5"}]
    assert client.quote_args == {
        "instrument_tokens": [{"instrument_token": "2885", "exchange_segment": "nse_cm"}],
        "quote_type": "all",
    }


def test_quotes_reject_more_than_fifty_instruments():
    instruments = [{"instrument_token": str(i), "exchange_segment": "nse_cm"} for i in range(51)]
    try:
        data.quotes({"consumer_key": "key"}, instruments)
        assert False, "expected validation error"
    except data.KotakNeoDataError as exc:
        assert "1 and 50" in str(exc)


def test_quotes_reject_invalid_segment():
    try:
        data.quotes(
            {"consumer_key": "key"},
            [{"instrument_token": "2885", "exchange_segment": "bad"}],
        )
        assert False, "expected validation error"
    except data.KotakNeoDataError as exc:
        assert "numeric token" in str(exc)


def test_scrip_search_uses_supported_segment(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(data, "_client", lambda _: client)
    result = data.search_scrip({"consumer_key": "key"}, "nse_cm", "RELIANCE")
    assert result["data"][0]["pSymbol"] == "2885"
    assert client.search_args == {"exchange_segment": "nse_cm", "symbol": "RELIANCE"}


def test_scrip_search_rejects_unknown_segment():
    try:
        data.search_scrip({"consumer_key": "key"}, "invalid", "RELIANCE")
        assert False, "expected validation error"
    except data.KotakNeoDataError as exc:
        assert "Unsupported exchange segment" in str(exc)



def test_scrip_search_reports_safe_sdk_error_message(monkeypatch):
    class ErrorClient:
        def search_scrip(self, **kwargs):
            return {"Error": RuntimeError("internal"), "message": "Exchange segment is not available"}

    monkeypatch.setattr(data, "_client", lambda _: ErrorClient())
    try:
        data.search_scrip({"consumer_key": "key"}, "nse_cm", "RELIANCE")
        assert False, "expected safe broker error"
    except data.KotakNeoDataError as exc:
        assert "Exchange segment is not available" in str(exc)
        assert "internal" not in str(exc)

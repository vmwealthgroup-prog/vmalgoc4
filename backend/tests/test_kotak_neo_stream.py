import pytest

from app.brokers.kotak_neo_data import (
    KotakNeoDataError,
    normalize_stream_instruments,
    normalize_stream_tick,
)


def test_normalize_stream_instruments_accepts_verified_numeric_tokens():
    result = normalize_stream_instruments([
        {"instrument_token": "2885", "exchange_segment": "nse_cm", "symbol": "reliance"},
    ])
    assert result == [{
        "instrument_token": "2885",
        "exchange_segment": "nse_cm",
        "symbol": "RELIANCE",
    }]


@pytest.mark.parametrize("instruments", [
    [],
    [{"instrument_token": "not-a-token", "exchange_segment": "nse_cm", "symbol": "RELIANCE"}],
    [{"instrument_token": "2885", "exchange_segment": "unknown", "symbol": "RELIANCE"}],
    [{"instrument_token": "2885", "exchange_segment": "nse_cm", "symbol": ""}],
])
def test_normalize_stream_instruments_rejects_invalid_input(instruments):
    with pytest.raises(KotakNeoDataError):
        normalize_stream_instruments(instruments)


def test_normalize_stream_tick_maps_only_requested_instrument():
    instruments = [{"instrument_token": "2885", "exchange_segment": "nse_cm", "symbol": "RELIANCE"}]
    tick = normalize_stream_tick({
        "instrument_token": "2885",
        "exchange_segment": "nse_cm",
        "last_traded_price": "1350.25",
    }, instruments)
    assert tick is not None
    assert tick["symbol"] == "RELIANCE"
    assert tick["exchange"] == "nse_cm"
    assert tick["ltp"] == 1350.25
    assert tick["src"] == "kotak_neo"
    assert normalize_stream_tick({
        "instrument_token": "9999",
        "exchange_segment": "nse_cm",
        "last_traded_price": 100,
    }, instruments) is None

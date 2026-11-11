"""Read-only Kotak Neo market-data adapter using the official SDK."""
from typing import Any

from neo_api_client import NeoAPI

ALLOWED_SEGMENTS = {"nse_cm", "bse_cm", "nse_fo", "bse_fo", "mcx_fo", "nse_com"}


class KotakNeoDataError(Exception):
    pass


def _client(credentials: dict[str, Any]):
    if not credentials.get("consumer_key"):
        raise KotakNeoDataError("Kotak Neo consumer key is missing.")
    try:
        client = NeoAPI(consumer_key=credentials["consumer_key"], environment="prod")
        config = client.configuration
        if credentials.get("trade_token") and credentials.get("trade_sid"):
            config.edit_token = credentials["trade_token"]
            config.edit_sid = credentials["trade_sid"]
            config.edit_rid = credentials.get("trade_rid")
            config.base_url = credentials.get("base_url")
            config.data_center = credentials.get("data_center")
            config.ucc = credentials.get("ucc")
            config.neo_fin_key = "neotradeapi"
        return client
    except Exception as exc:
        raise KotakNeoDataError("Could not initialize Kotak Neo API client.") from exc


def _safe_response(result: Any, operation: str):
    if not isinstance(result, (dict, list)):
        raise KotakNeoDataError(f"Kotak Neo {operation} returned an unexpected response.")
    if isinstance(result, dict) and any(k in result for k in ("Error", "Error Message", "error")):
        raise KotakNeoDataError(f"Kotak Neo {operation} failed. Check inputs or retry.")
    return result


def _read(client, method_name: str):
    try:
        result = getattr(client, method_name)()
    except Exception as exc:
        raise KotakNeoDataError(f"Kotak Neo {method_name} request failed.") from exc
    return _safe_response(result, method_name)


def account_snapshot(credentials: dict[str, Any]) -> dict[str, Any]:
    """Fetch read-only account data; each section reports its own safe error."""
    if not credentials.get("trade_token") or not credentials.get("trade_sid"):
        raise KotakNeoDataError("Complete TOTP and MPIN authentication first.")
    client = _client(credentials)
    output: dict[str, Any] = {}
    for key, method in (
        ("funds", "limits"),
        ("holdings", "holdings"),
        ("positions", "positions"),
        ("orders", "order_report"),
        ("trades", "trade_report"),
    ):
        try:
            output[key] = {"ok": True, "data": _read(client, method)}
        except KotakNeoDataError as exc:
            output[key] = {"ok": False, "error": str(exc)}
    return output


def search_scrip(credentials: dict[str, Any], exchange_segment: str, symbol: str) -> Any:
    if exchange_segment not in ALLOWED_SEGMENTS:
        raise KotakNeoDataError("Unsupported exchange segment.")
    if not symbol or len(symbol) > 40:
        raise KotakNeoDataError("Enter a valid trading symbol.")
    client = _client(credentials)
    try:
        return _safe_response(
            client.search_scrip(exchange_segment=exchange_segment, symbol=symbol.strip()),
            "scrip search",
        )
    except KotakNeoDataError:
        raise
    except Exception as exc:
        raise KotakNeoDataError("Kotak Neo scrip search failed.") from exc


def quotes(credentials: dict[str, Any], instruments: list[dict[str, str]], quote_type: str = "all") -> Any:
    if not instruments or len(instruments) > 50:
        raise KotakNeoDataError("Select between 1 and 50 instruments per quote request.")
    if quote_type not in {"all", "market_depth", "ohlc", "ltp", "oi", "52w", "circuit_limits", "scrip_details"}:
        raise KotakNeoDataError("Unsupported quote type.")
    normalized = []
    for item in instruments:
        token = str(item.get("instrument_token", "")).strip()
        segment = str(item.get("exchange_segment", "")).strip()
        if not token.isdigit() or segment not in ALLOWED_SEGMENTS:
            raise KotakNeoDataError("Each instrument needs a numeric token and supported exchange segment.")
        normalized.append({"instrument_token": token, "exchange_segment": segment})
    client = _client(credentials)
    try:
        return _safe_response(
            client.quotes(instrument_tokens=normalized, quote_type=quote_type),
            "market quotes",
        )
    except KotakNeoDataError:
        raise
    except Exception as exc:
        raise KotakNeoDataError("Kotak Neo market quote request failed.") from exc

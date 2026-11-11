"""Read-only Kotak Neo account-data adapter using the official SDK."""
from typing import Any

from neo_api_client import NeoAPI


class KotakNeoDataError(Exception):
    pass


def build_client(credentials: dict[str, Any]):
    required = ("consumer_key", "trade_token", "trade_sid", "base_url")
    if any(not credentials.get(key) for key in required):
        raise KotakNeoDataError("Kotak Neo trading session is incomplete. Re-authenticate.")
    client = NeoAPI(consumer_key=credentials["consumer_key"], environment="prod")
    config = client.configuration
    config.edit_token = credentials["trade_token"]
    config.edit_sid = credentials["trade_sid"]
    config.edit_rid = credentials.get("trade_rid")
    config.base_url = credentials["base_url"]
    config.data_center = credentials.get("data_center")
    config.ucc = credentials.get("ucc")
    config.neo_fin_key = "neotradeapi"
    return client


def _read(client, method_name: str):
    try:
        result = getattr(client, method_name)()
    except Exception as exc:
        raise KotakNeoDataError(f"Kotak Neo {method_name} request failed.") from exc
    if not isinstance(result, (dict, list)):
        raise KotakNeoDataError(f"Kotak Neo {method_name} returned an unexpected response.")
    if isinstance(result, dict) and any(k in result for k in ("Error", "Error Message", "error")):
        raise KotakNeoDataError(f"Kotak Neo {method_name} could not be retrieved. Re-authenticate or retry.")
    return result


def account_snapshot(credentials: dict[str, Any]) -> dict[str, Any]:
    """Fetch read-only account data; each section reports its own safe error."""
    client = build_client(credentials)
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

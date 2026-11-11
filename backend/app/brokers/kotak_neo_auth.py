"""Kotak Neo authentication wrapper around the official kotakneoapi SDK.

TOTP and MPIN are transient request values. Only session fields are returned
to the router for encrypted persistence.
"""
from typing import Any

from neo_api_client import NeoAPI


class KotakNeoAuthError(Exception):
    pass


def _data(response: Any, stage: str) -> dict:
    if not isinstance(response, dict):
        raise KotakNeoAuthError(f"Kotak Neo {stage} returned an invalid response.")
    data = response.get("data")
    status = str(data.get("status", "")).lower() if isinstance(data, dict) else ""
    # SDK/API releases may omit the optional status field while still returning
    # the documented session token pair. Treat that as success only when the
    # caller can subsequently validate the required token and SID.
    if not isinstance(data, dict) or (status and status != "success"):
        # Do not return raw broker response; it may contain session/account data.
        error = response.get("error")
        message = "Authentication was not accepted."
        if isinstance(error, list) and error and isinstance(error[0], dict):
            message = str(error[0].get("message") or message)
        elif isinstance(response.get("message"), str):
            message = response["message"]
        raise KotakNeoAuthError(message[:160])
    return data


def totp_login(consumer_key: str, mobile_number: str, ucc: str, totp: str) -> dict:
    try:
        client = NeoAPI(consumer_key=consumer_key, environment="prod")
        data = _data(
            client.totp_login(mobile_number=mobile_number, ucc=ucc, totp=totp),
            "TOTP login",
        )
    except KotakNeoAuthError:
        raise
    except Exception as exc:
        raise KotakNeoAuthError("Kotak Neo TOTP login failed. Check the credentials and retry.") from exc
    token, sid = data.get("token"), data.get("sid")
    if not token or not sid:
        raise KotakNeoAuthError("Kotak Neo did not return a temporary view session.")
    return {"view_token": token, "view_sid": sid}


def mpin_validate(consumer_key: str, view_token: str, view_sid: str, mpin: str) -> dict:
    try:
        client = NeoAPI(consumer_key=consumer_key, environment="prod")
        client.configuration.view_token = view_token
        client.configuration.sid = view_sid
        data = _data(client.totp_validate(mpin=mpin), "MPIN validation")
    except KotakNeoAuthError:
        raise
    except Exception as exc:
        raise KotakNeoAuthError("Kotak Neo MPIN validation failed. Retry authentication.") from exc
    token, sid, base_url = data.get("token"), data.get("sid"), data.get("baseUrl")
    from urllib.parse import urlparse
    parsed = urlparse(str(base_url or ""))
    if not token or not sid or parsed.scheme != "https" or not (
        parsed.hostname == "kotaksecurities.com" or (parsed.hostname or "").endswith(".kotaksecurities.com")
    ):
        raise KotakNeoAuthError("Kotak Neo did not return a valid trading session.")
    return {
        "trade_token": token,
        "trade_sid": sid,
        "trade_rid": data.get("rid"),
        "base_url": base_url,
        "data_center": data.get("dataCenter"),
        "ucc": data.get("ucc"),
    }

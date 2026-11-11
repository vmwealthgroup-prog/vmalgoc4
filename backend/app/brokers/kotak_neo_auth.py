"""Minimal, server-side Kotak Neo authentication calls.

Only the Consumer Key and returned session material are persisted, encrypted by
the router. TOTP and MPIN are request-only values and are never logged/stored.
"""
from urllib.parse import urlparse
import httpx

LOGIN_BASE = "https://mis.kotaksecurities.com"
NEO_FIN_KEY = "neotradeapi"
TIMEOUT = httpx.Timeout(12.0, connect=5.0)


class KotakNeoAuthError(Exception):
    pass


def _post(path: str, headers: dict, payload: dict) -> dict:
    try:
        response = httpx.post(
            f"{LOGIN_BASE}{path}",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
    except httpx.TimeoutException as exc:
        raise KotakNeoAuthError("Kotak Neo authentication timed out. Retry with a fresh TOTP.") from exc
    except httpx.HTTPStatusError as exc:
        # Do not forward upstream body: it can contain account/session details.
        raise KotakNeoAuthError(f"Kotak Neo rejected the authentication request (HTTP {exc.response.status_code}).") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise KotakNeoAuthError("Could not read a valid response from Kotak Neo.") from exc

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or str(data.get("status", "")).lower() != "success":
        message = body.get("message") if isinstance(body, dict) else None
        safe_message = str(message or "Authentication was not accepted.")[:160]
        raise KotakNeoAuthError(safe_message)
    return data


def totp_login(consumer_key: str, mobile_number: str, ucc: str, totp: str) -> dict:
    data = _post(
        "/login/1.0/tradeApiLogin",
        {"Authorization": consumer_key, "neo-fin-key": NEO_FIN_KEY},
        {"mobileNumber": mobile_number, "ucc": ucc, "totp": totp},
    )
    token, sid = data.get("token"), data.get("sid")
    if not token or not sid:
        raise KotakNeoAuthError("Kotak Neo response did not contain the temporary view session.")
    return {"view_token": token, "view_sid": sid}


def mpin_validate(consumer_key: str, view_token: str, view_sid: str, mpin: str) -> dict:
    data = _post(
        "/login/1.0/tradeApiValidate",
        {
            "Authorization": consumer_key,
            "neo-fin-key": NEO_FIN_KEY,
            "sid": view_sid,
            "Auth": view_token,
        },
        {"mpin": mpin},
    )
    token, sid, base_url = data.get("token"), data.get("sid"), data.get("baseUrl")
    parsed = urlparse(str(base_url or ""))
    if not token or not sid or parsed.scheme != "https" or not (
        parsed.hostname == "kotaksecurities.com" or (parsed.hostname or "").endswith(".kotaksecurities.com")
    ):
        raise KotakNeoAuthError("Kotak Neo response did not contain a valid trading session.")
    return {"trade_token": token, "trade_sid": sid, "base_url": base_url}

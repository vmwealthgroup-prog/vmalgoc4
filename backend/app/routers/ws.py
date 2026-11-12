import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..brokers import kotak_neo_data
from ..db import SessionLocal
from ..models import BrokerAccount, User
from ..policy import auth_required, brokers_allowed, ensure_owner
from ..pubsub import get_pubsub
from ..security import decode_token, decrypt

router = APIRouter()


@router.websocket("/ws/stream")
async def stream(ws: WebSocket, token: str = "", symbols: str = ""):
    """Live ticks (filtered by `symbols`) and this user's order/signal events.
    Open mode: no token needed (you are the owner). Login mode: JWT in ?token= (browsers cannot set WS headers)."""
    with SessionLocal() as db:
        open_mode = not auth_required(db)
        if open_mode:
            uid = ensure_owner(db).id; db.commit()
    if not open_mode:
        try:
            uid = int(decode_token(token)["sub"])
        except Exception:
            await ws.close(code=4401); return
    await ws.accept()
    wanted = {s.strip() for s in symbols.split(",") if s.strip()}

    async def sender():
        async for ch, msg in get_pubsub().subscribe(["ticks", f"events:{uid}"]):
            if ch == "ticks" and wanted and msg.get("symbol") not in wanted:
                continue
            await ws.send_json(msg)

    async def receiver():
        while True:
            m = await ws.receive_json()
            if m.get("type") == "subscribe":
                wanted.clear(); wanted.update(str(s) for s in m.get("symbols", [])[:50])

    tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks: t.cancel()
        try: await ws.close()
        except Exception: pass



@router.websocket("/ws/kotak-neo/{aid}")
async def kotak_neo_market_stream(ws: WebSocket, aid: int, token: str = ""):
    """Account-scoped, read-only Kotak Neo SFeed stream.

    The browser sends one initial JSON frame:
    {"type":"subscribe","instruments":[{"instrument_token":"...","exchange_segment":"nse_cm","symbol":"RELIANCE"}]}
    Instrument tokens must come from this account's Kotak scrip search. Market data is sent only
    to this authenticated account's socket; it is not broadcast to other users.
    """
    with SessionLocal() as db:
        open_mode = not auth_required(db)
        if not brokers_allowed(db):
            await ws.close(code=4403, reason="Broker connections require login mode.")
            return
        if open_mode:
            user = ensure_owner(db)
            db.commit()
        else:
            try:
                uid = int(decode_token(token)["sub"])
            except Exception:
                await ws.close(code=4401, reason="Invalid or expired login.")
                return
            user = db.get(User, uid)
            if user is None or not user.is_active:
                await ws.close(code=4401, reason="Account disabled or missing.")
                return
        account = db.get(BrokerAccount, aid)
        if account is None or account.user_id != user.id or account.kind != "kotak_neo":
            await ws.close(code=4404, reason="Kotak Neo account not found.")
            return
        try:
            credentials = json.loads(decrypt(account.api_key_enc))
        except Exception:
            await ws.close(code=1011, reason="Could not read the encrypted broker session.")
            return
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
        if credentials.get("token_date") != today or not credentials.get("trade_token") or not credentials.get("trade_sid"):
            await ws.close(code=4401, reason="Kotak Neo session expired. Complete TOTP and MPIN login again.")
            return

    await ws.accept()
    try:
        request = await ws.receive_json()
        if not isinstance(request, dict) or request.get("type") != "subscribe":
            await ws.send_json({"type": "error", "message": "Send a subscribe message with verified instruments."})
            return
        instruments = kotak_neo_data.normalize_stream_instruments(request.get("instruments"))
        from neo_api_client.websocket.feed import WsToken
        feed = kotak_neo_data.create_market_websocket(credentials)
        async with feed as neo_ws:
            await neo_ws.subscribe_scrips([WsToken(item["exchange_segment"], item["instrument_token"]) for item in instruments])
            await ws.send_json({"type": "status", "status": "connected", "source": "kotak_neo"})
            async for message in neo_ws:
                tick = kotak_neo_data.normalize_stream_tick(message, instruments)
                if tick:
                    await ws.send_json(tick)
    except WebSocketDisconnect:
        pass
    except kotak_neo_data.KotakNeoDataError as exc:
        try:
            await ws.send_json({"type": "error", "message": str(exc)[:160]})
        except Exception:
            pass
    except Exception:
        try:
            await ws.send_json({"type": "error", "message": "Kotak Neo live feed stopped. Check the session, token and network, then reconnect."})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass

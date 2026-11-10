import asyncio
from fastapi import APIRouter, WebSocket
from ..db import SessionLocal
from ..policy import auth_required, ensure_owner
from ..pubsub import get_pubsub
from ..security import decode_token

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

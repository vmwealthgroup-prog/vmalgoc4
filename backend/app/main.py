import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import get_settings
from .db import Base, SessionLocal, engine
from .feed import Feeder
from .pubsub import get_pubsub
from .routers import admin, ai, appconfig, auth, backtests, brokers, portfolio, scanner, strategies, system, webhooks, ws
from . import notify
from .heartbeat import beat
from .runner import run_once


async def runner_loop(interval: int):
    ps = get_pubsub()
    def work():
        with SessionLocal() as db:
            ev = run_once(db); beat(db, "runner"); return ev
    while True:
        try:
            for e in await asyncio.to_thread(work):
                await ps.publish(f"events:{e['user_id']}", e)
                fm = notify.format_event(e)
                if fm: await asyncio.to_thread(notify.notify, *fm)
        except Exception:
            pass
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.env != "production":
        Base.metadata.create_all(engine)   # development convenience. Production uses `alembic upgrade head` (the Docker image does this on start)
    tasks = []
    if s.feed_in_api:
        tasks.append(asyncio.create_task(Feeder(get_pubsub()).run()))
        if s.runner_enabled:
            tasks.append(asyncio.create_task(runner_loop(s.runner_interval_s)))
    yield
    for t in tasks: t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)          # let the feeder flush its last candle and write final stats


def create_app() -> FastAPI:
    s = get_settings()
    prod = s.env == "production"   # no interactive API docs in production
    app = FastAPI(title="VM Algo API", version="1.0.0", lifespan=lifespan, docs_url=None if prod else "/docs", redoc_url=None, openapi_url=None if prod else "/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    for r in (ai.router, webhooks.manage, webhooks.public, system.router, appconfig.router, auth.router, strategies.router, backtests.router, scanner.router, brokers.router, portfolio.router, admin.router, ws.router):
        app.include_router(r)

    @app.get("/health")
    async def health():
        from sqlalchemy import text
        try:
            with engine.connect() as c: c.execute(text("select 1"))
            db_ok = True
        except Exception:
            db_ok = False
        from .db import SessionLocal
        from .heartbeat import age_seconds
        from .policy import auth_required
        try:
            with SessionLocal() as d: mode = "login" if auth_required(d) else "open"; workers = {"runner_age_s": age_seconds(d, "runner"), "feed_age_s": age_seconds(d, "feed")}
        except Exception: mode, workers = "unknown", {}
        return {"status": "ok" if db_ok else "degraded", "access_mode": mode, "workers": workers, "db": db_ok, "pubsub": await get_pubsub().ping(), "live_trading_enabled": s.live_trading_enabled}

    return app


app = create_app()

"""Standalone worker: tick feeder + strategy runner. Run:  python -m app.worker  (set FEED_IN_API=false on the API).
SIGTERM / SIGINT (docker stop, systemd stop, Ctrl+C) stop it gracefully: the last candle is saved and final feed stats are written."""
import asyncio, signal
from .config import get_settings
from .db import Base, engine
from .feed import Feeder
from .main import runner_loop
from .pubsub import get_pubsub


async def main():
    s = get_settings()
    if s.env != "production":
        Base.metadata.create_all(engine)
    jobs = [Feeder(get_pubsub()).run()]
    if s.runner_enabled:
        jobs.append(runner_loop(s.runner_interval_s))
    main_task, loop = asyncio.current_task(), asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try: loop.add_signal_handler(sig, main_task.cancel)
        except NotImplementedError: pass                       # Windows
    for r in await asyncio.gather(*jobs, return_exceptions=True):
        if isinstance(r, BaseException) and not isinstance(r, asyncio.CancelledError): raise r


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        pass

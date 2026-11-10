"""External watchdog: run it every couple of minutes from cron or a systemd timer (see deploy/systemd). It alerts you (Telegram/Discord/webhook) when
the API is unreachable, the database is down, or the strategy runner / price feed has gone silent, and again when things recover.
    python -m app.watchdog --url http://127.0.0.1:8000        exit code 0 = healthy, 2 = problem
Alerts are rate-limited by a small state file so you get one message per incident, not one every two minutes."""
import argparse, json, pathlib, sys, time
import httpx
from . import notify
from .config import get_settings


def problems_in(health: dict, runner_limit: float, feed_limit: float = 90.0, need_workers: bool = True) -> list[str]:
    out = []
    if health.get("status") != "ok": out.append("database is unhealthy")
    if need_workers:
        w = health.get("workers") or {}
        r, f = w.get("runner_age_s"), w.get("feed_age_s")
        if r is None: out.append("the worker has never reported in")
        elif r > runner_limit: out.append(f"strategy runner silent for {r:.0f}s")
        if f is not None and f > feed_limit: out.append(f"price feed silent for {f:.0f}s")
    return out


def run(url: str, state_file: str, cooldown_s: int = 1800, need_workers: bool = True, transport=None, now: float | None = None) -> list[str]:
    now = now or time.time(); s = get_settings(); path = pathlib.Path(state_file)
    state = json.loads(path.read_text()) if path.exists() else {}
    try:
        with httpx.Client(timeout=5, transport=transport) as c:
            r = c.get(url.rstrip("/") + "/health"); r.raise_for_status(); problems = problems_in(r.json(), s.runner_interval_s * 3 + 15, need_workers=need_workers)
    except Exception as e:
        problems = [f"API unreachable ({type(e).__name__})"]
    key = "|".join(problems)
    if problems and (key != state.get("key") or now - state.get("t", 0) >= cooldown_s):
        notify.notify("WATCHDOG: " + "; ".join(problems), level="error", force=True); state = {"key": key, "t": now}
    elif not problems and state.get("key"):
        notify.notify("WATCHDOG: all systems recovered.", level="info", force=True); state = {}
    path.write_text(json.dumps(state))
    return problems


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--url", default="http://127.0.0.1:8000"); p.add_argument("--state", default="/tmp/vmalgo-watchdog.json")
    p.add_argument("--cooldown", type=int, default=1800); p.add_argument("--no-workers", action="store_true", help="API only (no separate worker expected)")
    a = p.parse_args(); bad = run(a.url, a.state, a.cooldown, need_workers=not a.no_workers)
    print("OK" if not bad else "PROBLEMS: " + "; ".join(bad)); sys.exit(2 if bad else 0)

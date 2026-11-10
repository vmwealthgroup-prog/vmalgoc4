import httpx, pytest
from app import notify, watchdog
from app.config import get_settings

OK = {"status": "ok", "workers": {"runner_age_s": 5.0, "feed_age_s": 3.0}}


@pytest.fixture()
def alerts(monkeypatch):
    sent = []
    notify._transport = httpx.MockTransport(lambda req: (sent.append(req.content.decode()), httpx.Response(200))[1])
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/h"); get_settings.cache_clear(); notify._recent.clear()
    yield sent
    notify._transport = None; monkeypatch.undo(); get_settings.cache_clear()


def api(payload=None, status=200):
    return httpx.MockTransport(lambda r: httpx.Response(status, json=payload if payload is not None else OK))


def test_problem_detection():
    assert watchdog.problems_in(OK, 105) == []
    assert "database" in watchdog.problems_in({**OK, "status": "degraded"}, 105)[0]
    assert "never reported" in watchdog.problems_in({"status": "ok", "workers": {"runner_age_s": None, "feed_age_s": None}}, 105)[0]
    assert "runner silent for 200s" in watchdog.problems_in({"status": "ok", "workers": {"runner_age_s": 200, "feed_age_s": 3}}, 105)[0]
    assert "feed silent" in watchdog.problems_in({"status": "ok", "workers": {"runner_age_s": 5, "feed_age_s": 500}}, 105)[0]
    assert watchdog.problems_in({"status": "ok", "workers": {}}, 105, need_workers=False) == []


def test_alert_once_per_incident_then_recovery(tmp_path, alerts):
    st = str(tmp_path / "s.json"); down = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    assert watchdog.run("http://x", st, 1800, transport=api(), now=1000) == [] and alerts == []                    # healthy: silent
    assert "unreachable" in watchdog.run("http://x", st, 1800, transport=down, now=2000)[0] and len(alerts) == 1  # first failure alerts
    watchdog.run("http://x", st, 1800, transport=down, now=2120); watchdog.run("http://x", st, 1800, transport=down, now=2240)
    assert len(alerts) == 1                                                                                        # same incident inside cooldown: no spam
    watchdog.run("http://x", st, 1800, transport=api({"status": "ok", "workers": {"runner_age_s": 999, "feed_age_s": 1}}), now=2300); assert len(alerts) == 2   # different problem: alerts again
    watchdog.run("http://x", st, 1800, transport=api({"status": "ok", "workers": {"runner_age_s": 999, "feed_age_s": 1}}), now=2300 + 1800); assert len(alerts) == 3   # reminder after cooldown
    assert watchdog.run("http://x", st, 1800, transport=api(), now=9000) == [] and len(alerts) == 4 and "recovered" in alerts[-1]
    watchdog.run("http://x", st, 1800, transport=api(), now=9100); assert len(alerts) == 4                         # no repeated "recovered"


def test_health_endpoint_reports_worker_ages(client):
    from app.db import SessionLocal
    from app.heartbeat import beat
    assert client.get("/health").json()["workers"] == {"runner_age_s": None, "feed_age_s": None}
    with SessionLocal() as db: beat(db, "runner")
    assert client.get("/health").json()["workers"]["runner_age_s"] < 5

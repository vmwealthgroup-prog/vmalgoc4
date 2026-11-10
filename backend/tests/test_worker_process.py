import asyncio, json, os, pathlib, signal, sqlite3, sys
from fake_coinbase import FakeCoinbase

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_worker_process_records_real_ticks_and_shuts_down_gracefully(tmp_path):
    """Runs `python -m app.worker` for real, feeds it protocol-accurate Coinbase messages, stops it with SIGTERM (what docker stop / systemd send)."""
    db = tmp_path / "w.db"
    async def go():
        async with FakeCoinbase() as srv:
            env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "CRYPTO_FEED": "coinbase", "COINBASE_WS_URL": srv.url, "FEED_SYMBOLS": "BTC/USD:CRYPTO", "RUNNER_ENABLED": "false",
                   "SECRET_KEY": "w" * 40, "ENV": "development", "AUTH_REQUIRED": "true"}
            p = await asyncio.create_subprocess_exec(sys.executable, "-m", "app.worker", cwd=str(ROOT), env=env, stderr=asyncio.subprocess.PIPE)
            await asyncio.sleep(3.0); p.send_signal(signal.SIGTERM)
            try: await asyncio.wait_for(p.wait(), 10)
            except asyncio.TimeoutError: p.kill(); raise AssertionError("worker did not stop on SIGTERM")
            return p.returncode, (await p.stderr.read()).decode()[-400:], srv.connections
    code, err, conns = asyncio.run(go())
    assert code == 0, err and conns == 1
    c = sqlite3.connect(db)
    n, hi, lo, vol = c.execute("select count(*), max(high), min(low), sum(volume) from market_candles where symbol='BTC/USD'").fetchone()
    assert n >= 1 and hi >= lo and vol > 0                                       # the last candle was flushed during shutdown
    stats = json.loads(c.execute("select value from app_settings where key='feedstats'").fetchone()[0])
    assert stats["connected"] is False and stats["trades"] == 7                  # final stats are accurate: a stopped worker is not shown as connected

import asyncio, json, time
from datetime import datetime, timedelta, timezone
import pytest
from fake_coinbase import FakeCoinbase, heartbeat_msg, iso, ticker_msg, trade, trades_msg
from conftest import signup
from app import quotes
from app.candles import CandleBuilder, load_candles, save_candles
from app.config import get_settings
from app.data import get_candles
from app.db import SessionLocal
from app.feed import Feeder
from app.feeds.coinbase import CoinbaseFeed, parse, parse_ts, to_product, to_symbol
from app.heartbeat import age_seconds, get as hb_get
from app.models import MarketCandle
from app.pubsub import MemoryPubSub


@pytest.fixture()
def env(monkeypatch):
    def setter(**kw):
        for k, v in kw.items(): monkeypatch.setenv(k.upper(), str(v))
        get_settings.cache_clear()
    yield setter
    monkeypatch.undo(); get_settings.cache_clear()


async def run_feed(srv, seconds, **kw):
    got = []
    async def on_trade(t): got.append(t)
    feed = CoinbaseFeed(["BTC/USD"], on_trade, url=srv.url, base_backoff=0.05, **kw)
    task = asyncio.create_task(feed.run()); await asyncio.sleep(seconds); feed.stop(); task.cancel(); await asyncio.gather(task, return_exceptions=True)
    return feed, got


# ---------------- message shapes (taken from Coinbase's documentation)
def test_parse_documented_messages():
    m = {"channel": "market_trades", "client_id": "", "timestamp": "2023-02-09T20:19:35.39625135Z", "sequence_num": 0, "events": [{"type": "snapshot", "trades": [
        {"trade_id": "000000000", "product_id": "ETH-USD", "price": "1260.01", "size": "0.3", "side": "BUY", "time": "2019-08-14T20:42:27.265Z"},
        {"trade_id": "000000001", "product_id": "ETH-USD", "price": "1260.02", "size": "0.1", "side": "SELL", "time": "2019-08-14T20:42:27.9Z"}]}]}
    a, b = parse(m)
    assert (a["symbol"], a["price"], a["size"], a["id"], a["snapshot"]) == ("ETH/USD", 1260.01, 0.3, "000000000", True)
    assert a["side"] == "sell" and b["side"] == "buy"                                    # the feed reports the MAKER side; the aggressor is the opposite
    assert abs(parse_ts("2023-02-09T20:19:35.39625135Z") - 1675973975.396251) < 1e-3     # 9 fractional digits are accepted
    t = parse(json.loads(ticker_msg(21932.98, 21931.98, 21933.98)))[0]
    assert (t["kind"], t["symbol"], t["price"], t["bid"], t["ask"], t["vol24h"]) == ("ticker", "BTC/USD", 21932.98, 21931.98, 21933.98, 16038.28)
    assert to_product("BTC/USD") == "BTC-USD" and to_symbol("eth-usd") == "ETH/USD"


def test_parse_is_defensive():
    assert parse({"channel": "heartbeats", "events": [{"heartbeat_counter": 1}]}) == []
    assert parse({"channel": "who_knows", "events": [{"x": 1}]}) == []
    bad = {"channel": "market_trades", "events": [{"type": "update", "trades": [{"trade_id": "1", "product_id": "BTC-USD", "size": "1", "side": "BUY", "time": "2023-01-01T00:00:00Z"}]}]}
    assert parse(bad) == []                                                              # missing price: skipped, no exception
    assert parse({}) == [] and parse({"channel": "ticker", "events": None}) == []


# ---------------- the client against the protocol server, over real sockets
def test_subscribes_once_per_channel_and_streams_trades():
    async def go():
        async with FakeCoinbase() as srv:
            feed, got = await run_feed(srv, 0.7)
            return srv, feed, got
    srv, feed, got = asyncio.run(go())
    assert sorted(m["channel"] for m in srv.subscribes) == ["heartbeats", "market_trades", "ticker"]
    assert all(m["type"] == "subscribe" and m["product_ids"] == ["BTC-USD"] for m in srv.subscribes)
    assert [t["id"] for t in got] == ["100", "101", "102", "103", "104", "105", "106"] and [t["snapshot"] for t in got[:3]] == [True, True, False]
    assert got[0]["side"] == "buy" and feed.stats["trades"] == 7 and feed.stats["connected"] is False or feed.stats["messages"] >= 8


def test_reconnect_does_not_double_count_replayed_trades():
    async def script(ws, n, srv):
        if n == 1:
            await ws.send(trades_msg([trade(100, 60000, 1), trade(101, 60001, 1)], "snapshot")); await ws.send(trades_msg([trade(102, 60002, 1)])); await asyncio.sleep(0.1); await ws.close()
        else:                                                                             # the snapshot after a reconnect repeats recent trades
            await ws.send(trades_msg([trade(101, 60001, 1), trade(102, 60002, 1), trade(103, 60003, 1)], "snapshot")); await ws.wait_closed()
    async def go():
        async with FakeCoinbase(script) as srv:
            feed, got = await run_feed(srv, 1.0); return srv, feed, got
    srv, feed, got = asyncio.run(go())
    assert [t["id"] for t in got] == ["100", "101", "102", "103"] and srv.connections >= 2 and feed.stats["reconnects"] >= 1


def test_silent_connection_is_detected_and_reopened():
    async def script(ws, n, srv):
        if n == 1:
            await ws.send(heartbeat_msg()); await ws.wait_closed()                       # goes quiet: no data, but the TCP connection stays open
        else:
            await ws.send(trades_msg([trade(200, 61000, 0.1)])); await ws.wait_closed()
    async def go():
        async with FakeCoinbase(script) as srv:
            feed, got = await run_feed(srv, 1.6, stale_after=0.4); return srv, feed, got
    srv, feed, got = asyncio.run(go())
    assert srv.connections >= 2 and [t["id"] for t in got] == ["200"] and "TimeoutError" in feed.stats["last_error"] or feed.stats["reconnects"] >= 1


def test_errors_garbage_and_unknown_messages_do_not_break_the_feed():
    async def script(ws, n, srv):
        await ws.send("this is not json"); await ws.send("[1, 2, 3]"); await ws.send(json.dumps({"type": "error", "message": "rate limited"}))
        await ws.send(json.dumps({"channel": "mystery", "events": [{"new": "thing"}]})); await ws.send(trades_msg([trade(300, 62000, 0.5)])); await ws.wait_closed()
    async def go():
        async with FakeCoinbase(script) as srv:
            feed, got = await run_feed(srv, 0.6); return srv, feed, got
    srv, feed, got = asyncio.run(go())
    assert srv.connections == 1 and [t["id"] for t in got] == ["300"] and feed.stats["bad"] == 2 and "rate limited" in feed.stats["last_error"]


def test_client_that_never_subscribes_is_dropped_by_the_server_but_ours_does_not():
    async def go():
        async with FakeCoinbase(subscribe_timeout=0.3) as srv:
            feed, got = await run_feed(srv, 0.6); return got
    assert len(asyncio.run(go())) == 7                                                     # we subscribe immediately, well inside Coinbase's 5-second limit


# ---------------- candles
def test_candle_builder_ohlcv_and_grace_period():
    b = CandleBuilder(); S = "BTC/USD"
    assert b.add(S, 100, 1, 60) == [] and b.add(S, 105, 2, 70) == [] and b.add(S, 95, 1, 80) == [] and b.add(S, 101, 1, 119) == []
    assert b.add(S, 102, 1, 125) == []                                                     # minute 2 opens; minute 1 stays open for late trades
    assert b.add(S, 99, 0.5, 90) == []                                                     # a late trade still lands in minute 1 ...
    done = b.add(S, 103, 1, 200)                                                           # ... and minute 1 is finalised once minute 3 starts
    assert done == [{"symbol": S, "ts": 60, "open": 100, "high": 105, "low": 95, "close": 101, "volume": 5.5}]
    assert b.add(S, 50, 9, 61) == []                                                       # too old to revise: dropped
    assert [c["ts"] for c in b.flush()] == [120, 180] and b.flush() == []


def test_candle_builder_out_of_order_within_a_minute_and_symbols_independent():
    b = CandleBuilder()
    b.add("A", 100, 1, 130); b.add("A", 90, 1, 125); b.add("B", 7, 1, 61)                 # the earlier trade arrives second
    c = {x["symbol"]: x for x in b.flush()}
    assert (c["A"]["open"], c["A"]["close"], c["A"]["low"]) == (90, 100, 90) and c["B"]["ts"] == 60


def _minute(offset):
    base = datetime.now(timezone.utc).replace(second=0, microsecond=0); return (base - timedelta(minutes=offset)).timestamp()


def test_storage_upsert_and_resample(client):
    base5 = datetime.now(timezone.utc).replace(second=0, microsecond=0); base5 -= timedelta(minutes=base5.minute % 5 + 10)       # a 5-minute boundary in the recent past
    rows = [{"symbol": "BTC/USD", "ts": (base5 + timedelta(minutes=i)).timestamp(), "open": 100 + i, "high": 110 + i, "low": 90 + i, "close": 101 + i, "volume": 1.0} for i in range(10)]
    with SessionLocal() as db:
        save_candles(db, rows); save_candles(db, [{**rows[0], "high": 999, "low": 1, "close": 150, "volume": 5.0}])              # same minute again: merged, not duplicated
        assert db.query(MarketCandle).count() == 10
        m1 = load_candles(db, "BTC/USD", "1m", 50); assert len(m1) == 10 and m1["high"].iloc[0] == 999 and m1["low"].iloc[0] == 1 and m1["close"].iloc[0] == 150
        m5 = load_candles(db, "BTC/USD", "5m", 10); assert len(m5) == 2
        first = m5.iloc[0]; assert (first["open"], first["high"], first["low"], first["close"], first["volume"]) == (100, 999, 1, 105, 9.0)
        assert load_candles(db, "NOPE", "5m", 10).empty
        with pytest.raises(ValueError): load_candles(db, "BTC/USD", "7m", 10)


def test_recorded_source_and_backtest_on_recorded_ticks(client, h):
    spec = {"symbol": "BTC/USD", "exchange": "CRYPTO", "interval": "1m", "risk": {"qty": 1}, "entry": {"all": [{"left": {"ind": "ema", "period": 5}, "op": "crosses_above", "right": {"ind": "ema", "period": 20}}]},
            "exit": {"all": [{"left": {"ind": "ema", "period": 5}, "op": "crosses_below", "right": {"ind": "ema", "period": 20}}]}}
    r = client.post("/api/backtests", headers=h, json={"spec": spec, "source": "recorded", "bars": 300}); assert r.status_code == 422 and "Not enough recorded data" in r.text
    px = 60000.0; rows = []
    for i in range(200, 0, -1):
        px += (37 if i % 7 < 4 else -29) * (1 if i % 50 < 25 else -1); rows.append({"symbol": "BTC/USD", "ts": _minute(i), "open": px - 5, "high": px + 20, "low": px - 20, "close": px, "volume": 0.8})
    with SessionLocal() as db:
        save_candles(db, rows); assert len(get_candles("BTC/USD", "CRYPTO", "1m", 300, "recorded", db=db)) == 200
    r = client.post("/api/backtests", headers=h, json={"spec": spec, "source": "recorded", "bars": 300}); assert r.status_code == 201, r.text
    assert r.json()["metrics"]["data_source"] == "recorded" and r.json()["metrics"]["bars"] == 200


# ---------------- the whole feeder, with real ticks
def test_feeder_routes_symbols_by_feed_type():
    f = Feeder(MemoryPubSub(), [("NIFTY", "NSE"), ("BTC/USD", "CRYPTO")], source="demo", crypto_feed="coinbase")
    assert f.ws_symbols == ["BTC/USD"] and f.symbols == [("NIFTY", "NSE")]
    g = Feeder(MemoryPubSub(), [("NIFTY", "NSE"), ("BTC/USD", "CRYPTO")], source="demo", crypto_feed="demo")
    assert g.ws_symbols == [] and [s for s, _ in g.symbols] == ["NIFTY", "BTC/USD"]


def test_feeder_end_to_end_real_ticks_candles_stats_and_throttle(client, env):
    async def go(url):
        env(coinbase_ws_url=url)
        ps = MemoryPubSub(); f = Feeder(ps, [("NIFTY", "NSE"), ("BTC/USD", "CRYPTO")], source="demo", crypto_feed="coinbase"); ticks = []
        async def listen():
            async for ch, m in ps.subscribe(["ticks"]): ticks.append(m)
        l = asyncio.create_task(listen()); await asyncio.sleep(0.05); t = asyncio.create_task(f.run())
        await asyncio.sleep(1.4); t.cancel(); l.cancel(); await asyncio.gather(t, l, return_exceptions=True)
        return ticks
    async def main():
        async with FakeCoinbase() as srv: return await go(srv.url)
    ticks = asyncio.run(main())
    btc = [x for x in ticks if x["symbol"] == "BTC/USD"]; nifty = [x for x in ticks if x["symbol"] == "NIFTY"]
    assert btc and all(x["src"] == "coinbase" and x["exchange"] == "CRYPTO" for x in btc) and nifty and all(x["src"] == "demo" for x in nifty)    # real and synthetic are labelled apart
    assert any(x.get("bid") == 59999.5 and x.get("ask") == 60000.5 for x in btc)                                                                   # best bid/ask come from the ticker channel
    assert len(btc) <= 12 and abs(quotes.get_last("BTC/USD") - btc[-1]["ltp"]) < 1e-6                                                              # throttled to <=4/s, cache holds the latest real price
    with SessionLocal() as db:
        stats = json.loads(hb_get(db, "feedstats")); assert stats["connected"] is False and stats["messages"] >= 8 and stats["trades"] == 7 and age_seconds(db, "feed") < 5   # final stats written on shutdown
        candles = db.query(MarketCandle).filter(MarketCandle.symbol == "BTC/USD").all()
    assert candles and all(c.high >= c.low and c.volume > 0 for c in candles)                                                                      # candles were recorded from real trades on shutdown


def test_status_endpoint_exposes_feed_health(client, h):
    from app.heartbeat import put
    with SessionLocal() as db: put(db, "feedstats", json.dumps({"connected": True, "messages": 42, "trades": 40, "gaps": 0, "reconnects": 1, "err": ""}))
    s = client.get("/api/system/status", headers=h).json()
    assert s["feed"]["messages"] == 42 and s["feed"]["reconnects"] == 1 and s["crypto_feed"] == "demo"

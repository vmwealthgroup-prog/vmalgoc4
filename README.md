# VM Algo: automated trading platform for Indian markets and crypto

Strategy builder, backtesting, scanner, portfolio, TradingView alerts and an **automated strategy runner** with layered safety. Paper trading by default.
Real orders are impossible until the server owner flips a hard switch, and even then every order passes a risk gate.

| Layer | Stack |
|---|---|
| Web | Next.js 14, React 18, TypeScript, Tailwind CSS, Recharts, NextAuth |
| API | FastAPI, SQLAlchemy 2, Alembic migrations, PostgreSQL, Redis, WebSockets |
| Worker | tick feeder + strategy runner (one process, run exactly one) |
| Brokers | Zerodha direct (official `kiteconnect`), paper broker, crypto exchanges via ccxt (read-only or trading) |
| Data | real BTC trade ticks from Coinbase's public WebSocket, recorded as candles; demo feed for offline development |
| AI | advisory analyst (Claude with your API key, or a built-in rule-based analyst); it can never place orders |
| Hosting | Docker Compose (Postgres, Redis, API, worker, web, Caddy with automatic HTTPS) or systemd units; CI workflow included |

Which suggested repositories were used, and why others were not: **[docs/REPO-SELECTION.md](docs/REPO-SELECTION.md)**.
India's algo rules and what this software does about them: **[docs/COMPLIANCE-INDIA.md](docs/COMPLIANCE-INDIA.md)**. Read it before going live.

## How automatic is it?
**Runs by itself, all day:** evaluates every deployed strategy on fresh candles; trades only while the exchange is open; flattens intraday positions at square-off time;
sizes trades by ATR risk; blocks anything outside your limits; engages a **kill switch** when the daily loss limit is hit; **switches a strategy off** if its recent trades lose
too much or its orders keep failing; caps order rate; tells you on Telegram/Discord/webhook about fills, blocks, trips and expired logins; a **watchdog** alerts if the worker or API goes quiet.

**Needs a human (by design, and by Indian rules):**
- **A fresh broker login every trading day.** Zerodha does not allow automating its login, and directly connected brokers require their own supported login flow. The app reminds you; the login takes under a minute.
- **A registered static IP** with your broker (the Brokers page shows your server's IP).
- **Turning live trading on**: server switch + login mode + per-account enable (with your password) + strategy set to live.
- **The exchange holiday list** (`MARKET_HOLIDAYS`) each year, and reading your alerts.
So "fully automatic" means hands-off between those steps, not unattended forever. Start with weeks of paper trading, then a tiny live size.

## Features
- **Access: login is optional.** Opens with no login (open mode); turn login on or off inside the app (Settings, Access). Open mode is paper only. Live trading and, on hosted servers, broker connections need login.
- **Strategy builder:** no-code rules (EMA/SMA/RSI/ATR/breakout levels, comparisons, crossovers, ALL/ANY), stop-loss, take-profit, ATR sizing, square-off, circuit-breaker settings; templates included
- **Backtesting:** next-candle execution (no lookahead), costs, equity vs buy-and-hold, Sharpe, drawdown, win rate, profit factor, trade list
- **Paper trading with realistic costs:** brokerage, STT, exchange charges, SEBI fee, stamp duty and GST (approximate, editable), net P&L
- **Scanner:** run any rule set over up to 50 symbols; presets included
- **Portfolio:** positions, holdings, funds and P&L from paper, Zerodha, legacy gateway brokers and crypto exchange accounts
- **TradingView alerts:** per-webhook secret URL (shown once, only a hash stored); `buy`, `sell`, `close`; same risk gate as everything else
- **Real-time dashboard:** live ticks, your order events over WebSocket, system health (feed, worker, market, kill switch)
- **Alerts:** Telegram, Discord or generic webhook; one message per incident, not a flood

## Real BTC ticks, crypto trading and the AI analyst
**Real tick data.** With `CRYPTO_FEED=coinbase` (the default) the worker streams every BTC trade from Coinbase's public WebSocket (no API key). Prices on the dashboard are labelled **LIVE** (real) or **DEMO** (synthetic) so the two are never confused.
Trades are also built into 1-minute candles and **recorded**, so you can backtest and analyze on real data from your own server (choose "Recorded live ticks"). Recording only runs while the worker runs, and a candle is saved about two minutes after its minute ends.
The feed reconnects with backoff, treats a silent connection as dead, ignores duplicate trades after a reconnect, and a dead feed shows as a problem on the health card (it is never papered over with fake prices).
Add more pairs with `FEED_SYMBOLS` (for example `BTC/USD:CRYPTO,ETH/USD:CRYPTO`).

**TradingView to crypto trades.** Create a webhook (Settings) and send `{"action": "buy", "symbol": "BTCUSDT", "exchange": "CRYPTO", "qty": 0.01}`. `BTCUSDT` and `BINANCE:BTCUSDT` are understood. Add a crypto account on the Brokers page with
"allow this account to place orders" ticked, API keys with trading permission and **withdrawals disabled**, and the exchange's **test network** on while you learn. Real-money orders need every live switch (see Safety model) and pass the same risk gate, daily-loss guard and kill switch as everything else.

**AI Analyst** (sidebar). It reads the market facts and indicators the platform computes (price changes, EMAs, RSI, ATR, 20-bar range, trend), explains them, lists risks, and can draft a strategy in the builder's own format.
- It has **no tools and no access to orders, brokers or settings.** Its output is text and, optionally, a draft that is validated like any strategy, forced to the market you asked about, and saved *switched off*. You backtest and deploy it yourself.
- Works with no key (a built-in rule-based analyst). Set `ANTHROPIC_API_KEY` to use Claude (`AI_MODEL`, default `claude-sonnet-5-5`). If the provider fails, you automatically get the built-in analyst, with a notice.
- Your portfolio is **never** sent to the AI provider unless you tick the box for that request. Data labelled SIMULATED is called out as such. A per-user hourly limit applies (`AI_MAX_PER_HOUR`).

## Safety model (every layer must agree before a real order goes out)
0. Live trading needs **login mode**. In open mode, live orders and live broker toggles are refused by the server
1. `LIVE_TRADING_ENABLED=false` by default: server-wide hard stop
2. Per broker account: live must be enabled by the user, confirmed with their password
3. Per strategy: mode `live` needs an enabled broker account
4. **Risk gate on every order** (manual, webhook or automated): kill switch, max quantity, order value, position value, orders/day, **daily loss**, trading window, blocked symbols, no shorting unless allowed, duplicate cooldown
5. **You can always get out:** orders that reduce or close a position pass the kill switch, daily-loss and window checks. Opening or increasing is what gets blocked
6. Orders per second capped globally; daily-loss kill switch is sticky until you reset it; strategy circuit breaker
7. Broker keys encrypted (Fernet) and never returned by the API; production refuses to start with weak secrets; every decision, including blocked ones, is logged with its reason

## Run it locally
```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000                      # SQLite, in-process pub/sub, demo feed: no Docker needed
cd frontend && npm ci && npm run dev                                          # http://localhost:3000, no login needed, no .env file needed
```
Start the API first (port 8000): the web app forwards every `/api/*` call to it (`API_INTERNAL_URL`, default `http://127.0.0.1:8000`), and in development the live-price WebSocket connects to port 8000 of the same host.
Open Strategies, pick a template, Run backtest, then "Run in paper mode". The demo feed is synthetic: use broker or crypto data for real results.

## Deploy
```bash
python scripts/init_env.py        # writes .env with generated secrets. BACK UP ENCRYPTION_KEY
# edit .env: DOMAIN (A record to a STATIC IP), ADMIN_EMAIL, AUTH_REQUIRED=true for any internet-facing server, alert channels, MARKET_HOLIDAYS
docker compose up -d --build      # the API container runs `alembic upgrade head` first
```
Without Docker: use `deploy/systemd/` (API, worker, watchdog timer). Backups: `make backup` (Postgres dump, keeps 14). Logs: `make logs`.
Other hosts (Render, Railway, Fly): deploy `backend`, a second service running `python -m app.worker`, `frontend`, managed Postgres and Redis, same environment variables, one public domain
(route `/api/auth/*` to the web app and the rest of `/api`, `/ws`, `/health` to the API).

## Day-to-day
1. Morning: Brokers page, **Daily login** for Zerodha. A reminder is sent if it is missing during market hours.
2. Watch the dashboard health card or your alerts. Set up the watchdog so silence is noticed.
3. After a kill-switch or breaker trip: review, then reset in Settings / re-enable the strategy.

## Configuration (see `.env.example`)
`AUTH_REQUIRED`, `LIVE_TRADING_ENABLED`, `FEED_SOURCE` (demo / crypto), `ENFORCE_MARKET_HOURS`, `MARKET_HOLIDAYS`, `SQUARE_OFF_TIME`, `MAX_ORDERS_PER_SECOND`,
`BREAKER_DEFAULT_*`, `TELEGRAM_*` / `DISCORD_WEBHOOK_URL` / `NOTIFY_WEBHOOK_URL`, `CHARGES_JSON`, `KITE_MARKET_PROTECTION`.

## Troubleshooting
**`GET /api/app/config 404`, Register fails with 404, or the app says "Cannot reach the API".** The web app cannot find the API. Start it (`cd backend && uvicorn app.main:app --port 8000`).
If the API runs elsewhere, set `API_INTERNAL_URL` for the web server (for example `API_INTERNAL_URL=http://127.0.0.1:9000 npm run dev`), or set `NEXT_PUBLIC_API_URL` to call it directly (then add the web origin to `CORS_ORIGINS`).

**Browser shows `Invariant: Missing ActionQueueContext`, a hydration error "in <#document>", or the dev server prints `Cannot find module './NNN.js'`.**
This means the page loaded mixed or stale Next.js build files. Fix:
```bash
# stop every `next dev` / `next start` / `npm run build`, then:
cd frontend && rm -rf .next .next-dev node_modules/.cache && npm ci && npm run dev
```
Run only `npm run dev` for development. This project now keeps dev output in `.next-dev` and production output in `.next`, so building no longer breaks a running dev server;
if you see the error with an older copy of the project, delete its `.next` folder and `node_modules` first. If it persists, try a private window with extensions off: the line
`A listener indicated an asynchronous response ... message channel closed` is printed by a browser extension, not by this app, and extensions that edit the page can disturb hydration.
Use `npm ci` (not `npm install`) so you get exactly one copy of `next` 14.2.35 and `react` 18.3.1.

## Tests and what is verified
```bash
cd backend && pip install pytest fakeredis && python -m pytest tests       # 117 tests; TEST_DATABASE_URL=postgresql+psycopg://... runs them on Postgres
cd frontend && npx tsc --noEmit && npm run build
```
**Verified in development:** the whole backend suite on SQLite and real PostgreSQL 16; migrations upgrade, match the models exactly (`alembic check`) and downgrade, on both;
the direct Zerodha adapter against a fake of the official client whose method signatures were checked
against the installed library; strict TypeScript and production build from a clean checkout; end-to-end runs with real processes (open mode with no login, login switched on and off, WebSocket, paper automation, no duplicate orders).

**NOT verified** (no broker account, Docker, browser or Redis server in the build environment, and no route to Coinbase or an AI key): the Coinbase WebSocket against the REAL service (it was tested against a local server built to Coinbase's documented message formats; the build sandbox could not reach Coinbase); real Claude replies (the request and every reply shape were tested with a mock; the exact model id depends on your account); live crypto orders on any real exchange (tested with a fake exchange); any real broker login, real order, or live market data; Zerodha's exact response fields on your account;
building the Docker images, the Caddyfile, the systemd units and the CI workflow; a real Redis (tested with fakeredis); the UI clicked through in a browser; Telegram/Discord delivery to real accounts (tested against mocks).
Paper-trade for weeks first. Charge rates and the holiday calendar are yours to confirm.

## Known limits
- Live crypto orders are spot **market** orders only, tested against a fake exchange, not a real one. Exchanges differ (minimum sizes, market-buy rules, test networks): start on the exchange's test network. Positions and P&L come from our own fill ledger, so orders placed outside VM Algo are not seen.
- No direct Fyers adapter is included. Zerodha's direct adapter supports orders, portfolio and funds; Indian-market historical candles are not supplied by this adapter.
- The daily-loss guard uses the broker's day P&L; if a broker reports it differently, check the number against your broker app.
- Paper fills use the latest tick, with no slippage. Backtests use a flat cost in bps.
- Login throttling is per process; no 2FA or refresh tokens on VM Algo's own login. The API container runs with `--no-access-log` because the WebSocket token travels in the URL.
- Hosting this for **other people** may make you a regulated algo provider in India. See docs/COMPLIANCE-INDIA.md.

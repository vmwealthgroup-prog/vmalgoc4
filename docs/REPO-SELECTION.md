# Which of the suggested repositories VM Algo uses, and why

Licences below were read from each repository's own LICENSE file on the date this was prepared (GitHub's API was rate-limited, so the files were fetched directly). Re-check before you rely on them: licences can change.

| Repository | What it is | Licence | Decision | How it is used / why not |
|---|---|---|---|---|
| zerodha/pykiteconnect | Official Zerodha Kite Connect Python client | MIT | **ADOPTED** | Dependency `kiteconnect` (PyPI, MIT, v5.2.2). Powers the direct Zerodha adapter and its daily-login flow. Method signatures were checked against the installed package. |
| ccxt/ccxt | Unified crypto exchange library | MIT | **ADOPTED** | Dependency. Crypto candles and prices, and exchange accounts (balances; spot market orders when trading is enabled). |
| marketcalls/openalgo | Self-hosted broker gateway | AGPL-3.0 | **EVALUATED, REMOVED** | Was previously integrated as a separate service; removed from the active VM Algo runtime. No active dependency or adapter remains. |
| dhruv7539/zerodha-trading-bot | Multi-strategy Zerodha bot (paper/live, risk limits, systemd) | MIT | **IDEAS ONLY** | Read for design. Re-implemented from scratch: Indian charge model, strategy circuit breaker, heartbeat + watchdog, alerts, systemd units. No code copied. |
| fabston/TradingView-Webhook-Bot | TradingView alerts forwarded to chat apps | MIT | **IDEA ONLY** | VM Algo has its own webhook receiver (alert -> risk-gated order) and its own Telegram/Discord notifier. |
| alwin48/fyers-trading-bot | Modular Fyers intraday bot | MIT | **REFERENCE ONLY** | Not integrated. No direct Fyers adapter is included. |
| ivopetiz/algotrading | Older crypto strategy examples | MIT | **REFERENCE ONLY** | Not integrated (crypto, not maintained recently). |
| CryptoGnome/Tradingview-Webhook-Bot | TradingView alerts to crypto trades | NO LICENSE FILE | **NOT USED** | No licence file: all rights reserved, so it cannot legally be reused. VM Algo's own TradingView receiver places crypto orders through ccxt instead (see README). |
| FyersDev/fyers-api-sample-code | Fyers sample code | NO LICENSE FILE | **NOT USED** | No licence file. A direct Fyers adapter was not built (see README); use Fyers through OpenAlgo. |
| shubhankarbanerjee/FyersTrading | Fyers backtesting and execution | NO LICENSE FILE | **NOT USED** | No licence file. |
| freqtrade/freqtrade | Full crypto trading bot framework | GPL-3.0 | **NOT EMBEDDED** | GPL-3.0 is copyleft and it is a complete competing application. If you want it, run it as a separate service. |
| polakowo/vectorbt | Vectorised backtesting library | Apache-2.0 + Commons Clause | **NOT EMBEDDED** | Apache-2.0 with the Commons Clause, which forbids selling software whose value derives substantially from it. VM Algo has its own backtester; use vectorbt only for private research. |
| TauricResearch/TradingAgents | LLM multi-agent trading research framework | Apache-2.0 | **NOT IN THE TRADING PATH** | LLM output is non-deterministic, costs API money and was not designed for unattended real orders. Fine as an offline research tool; do not wire it to order placement. |
| cheaper-inference/OmniRoute | LLM request gateway | MIT | **NOT USED** | Only relevant if you add LLM features. Not needed for execution. |
| affaan-m/ECC | Configuration toolkit for coding agents (Claude Code, Cursor, ...) | MIT | **NOT PART OF THE PRODUCT** | Development tooling. Use it while building if you like; it does not belong in a trading runtime. |
| morluto/rea | Reverse-engineering toolkit | MIT | **NOT USED** | Unrelated to trading. Inspected earlier in this project: clean, but it analyses binaries and websites. |
| JoasASantos/REA-Prompts | Prompts for the reverse-engineering assistant | MIT | **NOT USED** | Unrelated to trading. |

## Rules applied
- **Adopt** only permissively licensed, maintained libraries from official or widely used sources, as normal dependencies.
- **No licence file means all rights reserved:** nothing from those repositories was reused.
- **Copyleft (GPL/AGPL) code is never embedded.** OpenAlgo is AGPL, so it stays a separate service.
- **Ideas are not copyrightable, code is:** everything borrowed from reference bots is new code written for this project.
- **LLM tools stay out of the order path.** An automated system that places real orders should be deterministic and testable.

## Why Zerodha is direct but Fyers is not
Zerodha has an official, MIT-licensed client that was installed and inspected. For Fyers, the only licensed reference was a sample bot, and the official sample repo has no licence; a direct adapter would have rested on unverified response formats, with real money behind it. Fyers (and 35+ other brokers) work through OpenAlgo instead.

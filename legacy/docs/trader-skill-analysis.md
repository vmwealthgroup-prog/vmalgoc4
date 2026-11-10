# Analysis of trader-skill (uploaded archive)

**What it is:** a Claude plugin (MIT, v1.0.0, author Jake Schincariol) of 11 skills for US long-only investing:
copycat (SEC 13F), news, budget, pelosi (House trade disclosures), analyst (SEC XBRL), screener, risk, broker (order tickets), tax, alerts, rebalance.
Plain standard-library Python, 175 offline tests (all pass when run here).

**Safety audit (static read, not a guarantee):** contacts only SEC, House Clerk, Yahoo, Stooq, NYSE, OpenFIGI; the single
subprocess call runs `pdftotext`; no eval/exec/pickle/sockets; nothing can place an order, it only writes tickets for a
broker connector, with paper trading and a human "yes" as defaults.

**Fit for VM Algo (India, Nifty/BankNifty options, crypto):** low as a signal source. Its data (SEC filings, US Congress, NYSE calendar)
is US-only, 13F data is up to 45 days stale, and it has no intraday or options logic. It is a good source of *process*:
1. Risk gate before any order -> ported as risk/risk_gate.py
2. Capped, buffer-aware position sizing -> strategies/sizing.py (cap_weights, atr_qty)
3. Band rebalancing instead of calendar rebalancing -> sizing.rebalance_trades + backtest/rebalance_backtest.py
4. Paper-by-default and explicit approval -> DRY_RUN and KILL file in live_runner.py
Not ported: copycat/pelosi/analyst/tax (US-specific). Indian analogues (bulk/block deals, shareholding patterns) would need
their own verified data sources first.

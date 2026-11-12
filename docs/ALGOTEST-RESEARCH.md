# VM AlgoTest — product and research specification

## Objective
Build a single research workbench that lets a trader state a hypothesis, select an Indian-market instrument and data source, run the existing VM Algo backtest, and inspect net performance and risk. AlgoTest is a research-only surface: it does not connect a test button to broker order placement.

## Tradetron marketplace benchmark
Reviewed https://tradetron.tech/strategies and Tradetron's public strategy-builder and backtest product pages on 12 November 2026.

The marketplace exposes search, sort by latest/minimum fees/maximum deployment/minimum capital, strategy type, 51 strategy tags, exchange filters, and free/paid filters. Listings show creator, deployment count, strategy category, trade count/cost estimate, drawdown, minimum capital and subscription fee. This is useful product discovery, but public popularity and creator-supplied descriptions are not independent proof of a durable edge.

The product benchmark to adopt:
- Make the research path obvious: hypothesis → market/instrument → historical data and costs → run → inspect report.
- Surface net return, benchmark return, drawdown, Sharpe, trade count, win rate, profit factor and equity curve together.
- Make market, timeframe, costs and data provenance visible beside every result.
- Treat demo/synthetic data as UI testing only, never as evidence.
- Keep strategy creation/testing separate from live deployment and require a paper-trading stage.

Tradetron's published backtest page additionally describes event-driven, stateful replay, real historical OHLC/OI, explicit brokerage/tax/slippage modelling, walk-forward-like period selection, Monte-Carlo resampling, and report-level robustness grading. These are useful benchmarks, not capabilities VM Algo should claim before implementing and validating them.

## Current VM Algo implementation
The AlgoTest page reuses the existing `POST /api/backtests` endpoint and backtest engine. It includes four transparent, editable-at-source research presets:
1. VM Trend Filter: EMA 20 > 50 > 200, close > EMA20 and RSI > 50; exit on EMA20 crossing below EMA50.
2. EMA 5/20 crossover: simple baseline.
3. Prior 20-bar breakout with 10-bar low exit.
4. RSI recovery above 30 with price above EMA20; exit above RSI 55.

Controls include symbol, NSE/BSE/NFO/MCX/CRYPTO exchange, supported candle interval, sample bar count, source, estimated cost in basis points, stop and target. Results include net strategy return, buy-and-hold return, max drawdown, Sharpe, win rate, profit factor, closed trades, time in market, equity curve and returned trade log.

The existing backtest engine shifts the position by one bar (signal at close, trade next bar), which avoids the most direct same-bar lookahead. It currently calculates approximate costs from basis points per position change. It does not yet provide date-range selection, full Indian statutory charge modelling, spread/market-impact slippage, intrabar order simulation, options-chain/OI strategy replay, Monte-Carlo, walk-forward optimisation, or independent robustness grading.

## Best initial research recommendation
Use VM Trend Filter as the first candidate to investigate, not as a claim of a winning strategy. Compare it against EMA 5/20 on the same symbol, exact same history window, timeframe and cost assumptions. Prefer liquid NSE cash instruments first. Repeat across bull, bear and sideways periods and use chronological out-of-sample data.

Do not rank strategies on win rate alone. A candidate should be rejected if net expectancy is negative, results depend on a small number of trades/months, drawdown exceeds the user's pre-set tolerance, or modestly higher costs erase the edge. Require enough closed trades and a stable out-of-sample result before paper trading.

## Prioritised engineering roadmap
P0 — data integrity: persist data vendor/source, exchange, symbol, timezone, interval, start/end timestamp, missing-bar count and corporate-action adjustment status with every run. Validate symbol/exchange support and reject synthetic data in any production score.

P1 — realistic costs: model brokerage per order, STT, exchange transaction charges, SEBI fee, GST, stamp duty, slippage and segment-specific rules. Show gross and net P&L and allow cost stress testing.

P2 — research quality: add date-range selection, in-sample/out-of-sample split, rolling walk-forward evaluation, benchmark comparison, expectancy, Sortino, Calmar, average win/loss, MAE/MFE, streaks, monthly return concentration and days underwater.

P3 — robustness: implement Monte-Carlo trade-sequence resampling with fixed seed and disclosed assumptions; parameter sensitivity heatmaps; regime segmentation; survivorship and corporate-action controls. Do not present a composite grade until its formula is transparent and independently tested.

P4 — India derivatives: historical option contract master, expiry/strike selection, actual option premium candles, OI/Greeks where available, realistic lot sizes, margin/hedge modelling and leg-level execution simulation. Never substitute spot-index candles for option premium history.

P5 — validation workflow: promote a candidate from backtest to paper only after out-of-sample review and a documented risk checklist. Live execution remains disabled by default and is outside the AlgoTest page.

## Acceptance criteria
- Page is reachable at `/algotest` and navigation includes AlgoTest.
- Run uses only `POST /api/backtests`; no broker order endpoint is called.
- All data-source labels are explicit; demo results carry a warning.
- Results show metrics and curve from the server response; errors are visible and reruns are possible.
- Typecheck, lint/build and backend tests pass before merge.
- Existing routes, database, broker integrations and live-trading safety gates remain unchanged.

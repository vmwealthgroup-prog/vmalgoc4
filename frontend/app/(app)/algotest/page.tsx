"use client";

import { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "@/lib/api";
import { fmt } from "@/lib/types";
import { Button, Card, Field, Input, Notice, Pnl, Stat, Table, Select } from "@/components/ui";

type Preset = "vm_trend" | "ema_5_20" | "breakout_20" | "rsi_recovery";
type BacktestResult = {
  id: number;
  name: string;
  metrics: {
    bars: number; total_return_pct: number; buy_hold_pct: number; cagr_pct: number;
    sharpe: number; max_drawdown_pct: number; trades: number; win_rate_pct: number;
    profit_factor: number | null; in_market_pct: number; cost_bps: number; data_source: string;
  };
  params: { spec: { symbol: string; exchange: string; interval: string; side: string }; bars: number; cost_bps: number };
  equity: { t: string; equity: number; close: number }[];
  trades: { side: string; entry_time: string; entry: number; exit_time: string; exit: number; pnl_pct: number }[];
};

const PRESETS: Record<Preset, { label: string; interval: string; entry: any; exit: any; note: string; stop: number; target: number }> = {
  vm_trend: {
    label: "VM Trend Filter (recommended baseline)", interval: "1h",
    entry: { all: [
      { left: { ind: "ema", period: 20 }, op: ">", right: { ind: "ema", period: 50 } },
      { left: { ind: "ema", period: 50 }, op: ">", right: { ind: "ema", period: 200 } },
      { left: { ind: "close" }, op: ">", right: { ind: "ema", period: 20 } },
      { left: { ind: "rsi", period: 14 }, op: ">", right: { value: 50 } }
    ] },
    exit: { all: [{ left: { ind: "ema", period: 20 }, op: "crosses_below", right: { ind: "ema", period: 50 } }] },
    note: "Trend stack + price confirmation + RSI strength. A transparent starting hypothesis, not a proven edge.", stop: 2, target: 4
  },
  ema_5_20: {
    label: "EMA 5/20 crossover", interval: "5m",
    entry: { all: [{ left: { ind: "ema", period: 5 }, op: "crosses_above", right: { ind: "ema", period: 20 } }] },
    exit: { all: [{ left: { ind: "ema", period: 5 }, op: "crosses_below", right: { ind: "ema", period: 20 } }] },
    note: "Simple momentum baseline. Expect whipsaws in sideways markets; compare costs and drawdown.", stop: 1.5, target: 3
  },
  breakout_20: {
    label: "20-bar breakout", interval: "15m",
    entry: { all: [{ left: { ind: "close" }, op: ">", right: { ind: "hh", period: 20 } }] },
    exit: { all: [{ left: { ind: "close" }, op: "<", right: { ind: "ll", period: 10 } }] },
    note: "Uses previous-bar highs/lows, avoiding current-bar breakout lookahead.", stop: 1.5, target: 3
  },
  rsi_recovery: {
    label: "RSI recovery", interval: "15m",
    entry: { all: [
      { left: { ind: "rsi", period: 14 }, op: "crosses_above", right: { value: 30 } },
      { left: { ind: "close" }, op: ">", right: { ind: "ema", period: 20 } }
    ] },
    exit: { all: [{ left: { ind: "rsi", period: 14 }, op: ">", right: { value: 55 } }] },
    note: "Mean-reversion hypothesis; test separately in trending and range-bound regimes.", stop: 1.5, target: 2.5
  }

};

type StrategyCard = { id: string; name: string; market: string; style: string; summary: string; readiness: "ready" | "options-data"; preset?: Preset };
const STRATEGY_CATALOGUE: StrategyCard[] = [
  { id: "trend_filter", name: "VM Trend Filter", market: "NSE / BSE", style: "Trend following", summary: "EMA 20/50/200 alignment with RSI confirmation.", readiness: "ready", preset: "vm_trend" },
  { id: "ema_crossover", name: "EMA 5/20 Crossover", market: "NSE / BSE", style: "Momentum", summary: "Closed-candle moving-average crossover baseline.", readiness: "ready", preset: "ema_5_20" },
  { id: "breakout", name: "20-Bar Breakout", market: "NSE / BSE", style: "Breakout", summary: "Prior-high breakout with a prior-low exit.", readiness: "ready", preset: "breakout_20" },
  { id: "rsi_recovery", name: "RSI Recovery", market: "NSE / BSE", style: "Mean reversion", summary: "RSI recovery with EMA trend confirmation.", readiness: "ready", preset: "rsi_recovery" },
  { id: "directional_spread", name: "VM NIFTY Directional Spread with Hedge", market: "NFO", style: "Bullish / Bearish · Option selling", summary: "Bull put or bear call credit spread, selected by trend regime; protective long option defines risk.", readiness: "options-data" },
  { id: "iron_condor", name: "VM Hedged Iron Condor", market: "NFO", style: "Non-directional · Theta", summary: "OTM call and put credit spreads with wing protection and range/volatility filters.", readiness: "options-data" },
  { id: "iron_butterfly", name: "VM Hedged Iron Butterfly", market: "NFO", style: "Expiry · Short volatility", summary: "ATM short straddle with protective wings; strict gap, gamma and time exits.", readiness: "options-data" },
  { id: "momentum_options", name: "VM Momentum Options Buying", market: "NFO", style: "Directional · CE / PE", summary: "VWAP, EMA 9/21, RSI and opening-range confirmation for premium buying.", readiness: "options-data" },
  { id: "expiry_theta", name: "VM NIFTY Expiry Theta", market: "NFO", style: "Expiry · Earn theta", summary: "Expiry-session defined-risk premium selling with volatility and time filters.", readiness: "options-data" },
  { id: "calendar", name: "VM Calendar Spread", market: "NFO", style: "Volatility · Calendar", summary: "Different-expiry legs to research term structure, theta and vega exposure.", readiness: "options-data" },
  { id: "ratio_hedged", name: "VM Hedged Ratio Spread", market: "NFO", style: "Directional · Volatility", summary: "Ratio structure with protective wings, scenario-based risk and margin checks.", readiness: "options-data" },
  { id: "banknifty_monthly", name: "VM BANKNIFTY Monthly Trend", market: "NFO", style: "Positional · Trend", summary: "Monthly-expiry directional spread with higher-timeframe trend filter.", readiness: "options-data" },
  { id: "sensex_basket", name: "VM SENSEX Momentum Basket", market: "BFO", style: "Momentum · Breakout", summary: "Directional options basket with breadth and breakout confirmation.", readiness: "options-data" },
  { id: "crude_hedged", name: "VM Crude Oil Hedged Seller", market: "MCX", style: "Non-directional · Option selling", summary: "Defined-risk commodity option selling with contract and expiry-aware sizing.", readiness: "options-data" }
];

export default function AlgoTestPage() {
  const { ready, call } = useApi();
  const [preset, setPreset] = useState<Preset>("vm_trend");
  const [strategyId, setStrategyId] = useState("trend_filter");
  const activeStrategy = STRATEGY_CATALOGUE.find((item) => item.id === strategyId) ?? STRATEGY_CATALOGUE[0];
  const [symbol, setSymbol] = useState("RELIANCE");
  const [exchange, setExchange] = useState("NSE");
  const [interval, setInterval] = useState(PRESETS.vm_trend.interval);
  const [side, setSide] = useState("long");
  const [source, setSource] = useState("auto");
  const [bars, setBars] = useState(1000);
  const [cost, setCost] = useState(5);
  const [stop, setStop] = useState(2);
  const [target, setTarget] = useState(4);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const selected = PRESETS[preset];
  const baseClose = result?.equity[0]?.close || 1;
  const curve = useMemo(() => result ? result.equity.map((p) => ({
    time: p.t.slice(0, 16).replace("T", " "),
    Strategy: +((p.equity - 1) * 100).toFixed(2),
    "Buy & hold": +((p.close / baseClose - 1) * 100).toFixed(2)
  })) : [], [result, baseClose]);

  function choosePreset(value: Preset) {
    setPreset(value); setInterval(PRESETS[value].interval); setStop(PRESETS[value].stop); setTarget(PRESETS[value].target);
  }

  function chooseStrategy(item: StrategyCard) {
    setStrategyId(item.id);
    if (item.preset) choosePreset(item.preset);
    if (item.market === "NFO" || item.market === "BFO") { setExchange(item.market); setSource("auto"); setSymbol(item.market === "BFO" ? "SENSEX" : "NIFTY"); }
    if (item.market === "MCX") { setExchange("MCX"); setSource("auto"); setSymbol("CRUDEOIL"); }
  }

  async function runTest() {
    if (activeStrategy.readiness !== "ready") { setError("This options strategy needs historical option-contract candles and leg-level simulation. It is catalogued for research but cannot be backtested by the current underlying-candle engine."); return; }
    setBusy(true); setError(""); setResult(null);
    const spec = {
      symbol: symbol.trim().toUpperCase(), exchange, interval, side,
      entry: selected.entry, exit: selected.exit,
      risk: { qty: 1, stop_pct: stop, take_pct: target }
    };
    try {
      const data = await call<BacktestResult>("/api/backtests", {
        method: "POST",
        body: JSON.stringify({ spec, source, bars, cost_bps: cost })
      });
      setResult(data);
    } catch (e) {
      setError((e as Error).message || "Backtest failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><p className="text-xs font-semibold uppercase tracking-widest text-ink2">VM Algo Research Lab</p><h1 className="mt-1 text-2xl font-bold">AlgoTest</h1><p className="mt-1 text-sm text-ink2">Configure, backtest and inspect a strategy without placing broker orders.</p></div>
        <span className="rounded-full border border-gain/30 bg-gain/5 px-3 py-1 text-xs font-semibold text-gain">BACKTEST ONLY · NO LIVE ORDERS</span>
      </div>

      <Card title="Strategy catalogue">
        <p className="mb-3 text-sm text-ink2">Choose a research hypothesis. Strategies marked “Options data required” are catalogued but are not falsely backtested using index candles.</p>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {STRATEGY_CATALOGUE.map((item) => (
            <button key={item.id} type="button" onClick={() => chooseStrategy(item)} aria-pressed={strategyId === item.id}
              className={`rounded-xl border p-3 text-left transition ${strategyId === item.id ? "border-gold bg-gold/5 ring-1 ring-gold" : "border-line bg-white hover:border-ink2"}`}>
              <div className="flex items-start justify-between gap-2"><span className="text-sm font-semibold">{item.name}</span><span className={`shrink-0 rounded-full px-2 py-1 text-[10px] font-semibold ${item.readiness === "ready" ? "bg-gain/10 text-gain" : "bg-amber-100 text-amber-800"}`}>{item.readiness === "ready" ? "Backtest ready" : "Options data required"}</span></div>
              <p className="mt-2 text-xs font-medium text-ink2">{item.market} · {item.style}</p>
              <p className="mt-2 text-xs text-ink2">{item.summary}</p>
            </button>
          ))}
        </div>
        <div className="mt-4 rounded-lg bg-paper p-3 text-sm"><b>Selected:</b> {activeStrategy.name}<p className="mt-1 text-xs text-ink2">{activeStrategy.readiness === "ready" ? "Uses the existing candle-based backtest endpoint." : "Research specification only. Requires historical option-chain/contract data, option premiums, expiry/strike mapping, Greeks/OI where available, leg-level fills, margin and statutory charges before performance testing."}</p></div>
      </Card>

      <Card title="Strategy hypothesis">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Strategy preset">
            <Select value={preset} onChange={(e) => choosePreset(e.target.value as Preset)}>
              {Object.entries(PRESETS).map(([key, p]) => <option key={key} value={key}>{p.label}</option>)}
            </Select>
          </Field>
          <Field label="Direction">
            <Select value={side} onChange={(e) => setSide(e.target.value)}><option value="long">Long</option><option value="short">Short</option></Select>
          </Field>
        </div>
        <p className="mt-3 rounded-lg bg-paper p-3 text-sm text-ink2">{selected.note}</p>
      </Card>

      <Card title="Market and test settings">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Symbol"><Input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="RELIANCE" maxLength={40} /></Field>
          <Field label="Exchange"><Select value={exchange} onChange={(e) => { setExchange(e.target.value); setSource("auto"); }}>{["NSE", "BSE", "NFO", "BFO", "MCX", "CRYPTO"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
          <Field label="Candle interval"><Select value={interval} onChange={(e) => setInterval(e.target.value)}>{["1m", "5m", "15m", "1h", "1d"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
          <Field label="Historical candles (60–5,000)"><Input type="number" min={60} max={5000} value={bars} onChange={(e) => setBars(Number(e.target.value))} /></Field>
          <Field label="Estimated cost (bps per position change)"><Input type="number" min={0} max={200} step={0.5} value={cost} onChange={(e) => setCost(Number(e.target.value))} /></Field>
          <Field label="Historical data source"><Select value={source} onChange={(e) => setSource(e.target.value)}><option value="auto">Auto (best available)</option>{exchange !== "CRYPTO" && <option value="openalgo">OpenAlgo broker history</option>}<option value="recorded">Recorded live ticks</option>{exchange === "CRYPTO" && <option value="crypto">Public crypto exchange data</option>}<option value="demo">Demo / synthetic (not valid for evaluation)</option></Select></Field>
          <Field label="Stop-loss (%)"><Input type="number" min={0} max={100} step={0.1} value={stop} onChange={(e) => setStop(Number(e.target.value))} /></Field>
          <Field label="Take-profit (%)"><Input type="number" min={0} max={500} step={0.1} value={target} onChange={(e) => setTarget(Number(e.target.value))} /></Field>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button onClick={runTest} disabled={!ready || busy || activeStrategy.readiness !== "ready" || !symbol.trim() || bars < 60 || bars > 5000 || cost < 0 || cost > 200 || stop < 0 || target < 0}>{busy ? "Running backtest…" : activeStrategy.readiness === "ready" ? "Run AlgoTest" : "Options backtest not yet available"}</Button>
          <span className="text-xs text-ink2">Execution model: signal at candle close, fill on next candle. No lookahead. Research only; no broker orders.</span>
        </div>
        {error && <div className="mt-3"><Notice kind="error">{error}</Notice></div>}
      </Card>

      <Card title="Research recommendation">
        <div className="grid gap-3 md:grid-cols-3">
          <div><p className="text-sm font-semibold">1. Start with trend filter</p><p className="mt-1 text-sm text-ink2">Compare EMA 20/50/200 alignment plus RSI confirmation against the simpler EMA 5/20 crossover.</p></div>
          <div><p className="text-sm font-semibold">2. Stress the assumptions</p><p className="mt-1 text-sm text-ink2">Increase costs, test both directions, and repeat across liquid symbols and multiple market regimes.</p></div>
          <div><p className="text-sm font-semibold">3. Validate out of sample</p><p className="mt-1 text-sm text-ink2">Use chronological train/test periods and walk-forward checks before paper trading. Do not select on win rate alone.</p></div>
        </div>
        <p className="mt-3 text-xs text-ink2">The current engine exposes EMA, SMA, RSI, ATR and prior-bar high/low. VWAP, ADX, options Greeks, open interest, slippage-by-spread and date-range walk-forward testing are not yet part of this page.</p>
      </Card>

      {result && (
        <>
          {result.metrics.data_source === "demo" && <Notice kind="warn">Synthetic demo data was used. This result is for UI/testing only and is not evidence of a trading edge.</Notice>}
          {result.metrics.data_source === "openalgo" && <Notice kind="info">Historical data source: OpenAlgo. This existing backtest route does not yet query the separate Kotak Neo account adapter.</Notice>}
          <div><h2 className="mb-3 text-lg font-semibold">Test result · {result.params.spec.symbol} {result.params.spec.exchange} · {result.params.spec.interval}</h2>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Net strategy return" value={<Pnl v={result.metrics.total_return_pct} />} tone={result.metrics.total_return_pct >= 0 ? "gain" : "loss"} />
              <Stat label="Buy & hold" value={<>{fmt(result.metrics.buy_hold_pct)}%</>} />
              <Stat label="Max drawdown" value={<>{fmt(result.metrics.max_drawdown_pct)}%</>} tone="loss" />
              <Stat label="Sharpe" value={fmt(result.metrics.sharpe)} />
              <Stat label="Win rate" value={<>{fmt(result.metrics.win_rate_pct, 1)}%</>} />
              <Stat label="Profit factor" value={result.metrics.profit_factor ?? "—"} />
              <Stat label="Closed trades" value={result.metrics.trades} />
              <Stat label="Time in market" value={<>{fmt(result.metrics.in_market_pct, 1)}%</>} />
            </div>
          </div>
          <Card title="Equity curve · strategy vs buy & hold">
            <div className="h-72" role="img" aria-label="Backtest equity curve compared with buy and hold">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={curve} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
                  <CartesianGrid stroke="#dde3ec" /><XAxis dataKey="time" minTickGap={60} tick={{ fontSize: 11 }} /><YAxis unit="%" tick={{ fontSize: 11 }} width={55} /><Tooltip /><Legend />
                  <Line type="monotone" dataKey="Strategy" stroke="#f2a900" dot={false} strokeWidth={2} /><Line type="monotone" dataKey="Buy & hold" stroke="#10223b" dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card title={`Trade log · ${result.trades.length} returned trades`}>
            {result.trades.length === 0 ? <p className="text-sm text-ink2">No closed trades in the selected sample. Try a different interval, symbol or strategy.</p> :
              <Table head={["Side", "Entry time", "Entry", "Exit time", "Exit", "Trade P&L %"]}>
                {[...result.trades].reverse().map((t, i) => <tr key={i}><td>{t.side}</td><td>{t.entry_time.slice(0, 16)}</td><td>{fmt(t.entry)}</td><td>{t.exit_time.slice(0, 16)}</td><td>{fmt(t.exit)}</td><td><Pnl v={t.pnl_pct} /></td></tr>)}
              </Table>}
          </Card>
          <p className="text-xs text-ink2">Sample: {result.metrics.bars} candles · source: {result.metrics.data_source} · assumed costs: {result.metrics.cost_bps} bps. Backtest results are hypothetical, may omit real execution effects, and do not predict future performance.</p>
        </>
      )}
    </div>
  );
}

"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useApi, useLoad } from "@/lib/api";
import { fmt } from "@/lib/types";
import { Button, Card, Field, Input, Notice, Select } from "@/components/ui";

const QUICK = ["What is the trend right now?", "What are the risks at the moment?", "Give me a strategy idea I can backtest"];
const SOURCE: Record<string, { t: string; k: "ok" | "warn" | "info" }> = {
  recorded: { t: "REAL ticks recorded from the live feed", k: "ok" }, crypto: { t: "REAL candles from the exchange", k: "ok" },
  openalgo: { t: "REAL candles from your broker", k: "ok" }, demo: { t: "SIMULATED data: no live source was available", k: "warn" },
};

export default function AiAnalyst() {
  const { call } = useApi(); const router = useRouter();
  const st = useLoad<{ claude_configured: boolean; model: string | null; limit_per_hour: number }>("/api/ai/status");
  const [f, setF] = useState({ symbol: "BTC/USD", exchange: "CRYPTO", interval: "1h", question: "", include_portfolio: false, use_ai: true });
  const [res, setRes] = useState<any>(null); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false); const [note, setNote] = useState("");

  async function analyze(question?: string) {
    setBusy(true); setErr(""); setNote("");
    const body = { ...f, question: question ?? f.question }; if (question) setF((x) => ({ ...x, question }));
    try { setRes(await call("/api/ai/analyze", { method: "POST", body: JSON.stringify(body) })); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  async function saveDraft() {
    try { const s = await call("/api/strategies", { method: "POST", body: JSON.stringify({ name: res.strategy_draft.name, spec: res.strategy_draft.spec }) }); router.push(`/strategies/${s.id}`); }
    catch (e) { setErr((e as Error).message); }
  }
  async function backtestDraft() {
    setBusy(true); setErr("");
    try { const b = await call("/api/backtests", { method: "POST", body: JSON.stringify({ spec: res.strategy_draft.spec, source: res.data_source === "recorded" ? "recorded" : "auto", bars: 1000 }) }); router.push(`/backtests/${b.id}`); }
    catch (e) { setErr((e as Error).message); setBusy(false); }
  }
  const fa = res?.facts; const src = res ? SOURCE[res.data_source] ?? SOURCE.demo : null;

  return (
    <div className="grid gap-6">
      <div><h1 className="text-2xl font-bold">AI Analyst</h1>
        <p className="text-sm text-ink2">Reads the market data and indicators this platform computes, explains what they show, and can draft a strategy for you to test. <b>It cannot place orders</b>, and nothing it writes runs unless you save, backtest and deploy it yourself.</p></div>
      {st.data && (st.data.claude_configured
        ? <Notice kind="ok">Using Claude ({st.data.model}). Up to {st.data.limit_per_hour} analyses per hour.</Notice>
        : <Notice kind="info">No AI key is set on the server, so the built-in rule-based analyst answers (same data, fixed rules, no AI). The server owner can add <code>ANTHROPIC_API_KEY</code> to use Claude.</Notice>)}
      <Card title="Ask about a market">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Symbol"><Input value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value.toUpperCase() })} /></Field>
          <Field label="Exchange"><Select value={f.exchange} onChange={(e) => setF({ ...f, exchange: e.target.value })}>{["CRYPTO", "NSE", "BSE", "NFO", "MCX"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
          <Field label="Candle"><Select value={f.interval} onChange={(e) => setF({ ...f, interval: e.target.value })}>{["1m", "5m", "15m", "1h", "1d"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
        </div>
        <div className="mt-4 grid gap-3">
          <Field label="Your question (optional)"><textarea className="min-h-[72px] rounded-lg border border-line bg-white px-3 py-2 text-sm font-normal focus:outline-none focus:ring-2 focus:ring-gold" maxLength={600} value={f.question} onChange={(e) => setF({ ...f, question: e.target.value })} /></Field>
          <div className="flex flex-wrap gap-2">{QUICK.map((q) => <Button key={q} variant="ghost" disabled={busy} onClick={() => analyze(q)}>{q}</Button>)}</div>
          <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={f.use_ai} onChange={(e) => setF({ ...f, use_ai: e.target.checked })} />Use the AI provider when it is available (uncheck to keep everything on this server)</label>
          <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={f.include_portfolio} onChange={(e) => setF({ ...f, include_portfolio: e.target.checked })} /><span>Also share my paper positions, strategy names and backtest results with the AI provider. <span className="text-ink2">Off by default. Only used when the AI provider answers.</span></span></label>
          <div><Button disabled={busy} onClick={() => analyze()}>{busy ? "Analyzing…" : "Analyze"}</Button></div>
        </div>
      </Card>
      {err && <Notice kind="error">{err}</Notice>}
      {res && (
        <>
          {res.warning && <Notice kind="warn">{res.warning}</Notice>}
          {src && <Notice kind={src.k}>Data: {src.t}. {res.synthetic && "Nothing here says anything about the real market."} · Analyst: {res.mode === "claude" ? `Claude (${res.model})` : "built-in rules"}{res.sent_portfolio && " · your portfolio was shared"}</Notice>}
          <Card title="Summary"><p className="text-sm leading-relaxed">{res.summary}</p>
            {res.points.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{res.points.map((p: string, i: number) => <li key={i}>{p}</li>)}</ul>}</Card>
          {res.risks.length > 0 && <Card title="Risks and caveats"><ul className="list-disc space-y-1 pl-5 text-sm">{res.risks.map((p: string, i: number) => <li key={i}>{p}</li>)}</ul></Card>}
          {res.strategy_draft && (
            <Card title={`Strategy draft: ${res.strategy_draft.name}`}>
              <p className="mb-2 text-sm text-ink2">{res.draft_note}</p>
              <pre className="max-h-64 overflow-auto rounded-lg bg-paper p-3 text-xs">{JSON.stringify(res.strategy_draft.spec, null, 2)}</pre>
              <div className="mt-3 flex flex-wrap gap-2"><Button disabled={busy} onClick={backtestDraft}>Backtest this draft</Button><Button variant="ghost" onClick={saveDraft}>Save as strategy (starts switched off)</Button></div>
            </Card>
          )}
          {!res.strategy_draft && res.draft_note && <Notice kind="warn">{res.draft_note}</Notice>}
          {fa && (
            <Card title="The numbers behind it">
              <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
                <div><div className="text-xs uppercase text-ink2">Last close</div><div className="font-semibold">{fmt(fa.last_close, 2)}</div></div>
                <div><div className="text-xs uppercase text-ink2">Change 5 / 20 bars</div><div className="font-semibold">{fa.change_pct["5_bars"] ?? "-"}% / {fa.change_pct["20_bars"] ?? "-"}%</div></div>
                <div><div className="text-xs uppercase text-ink2">Trend</div><div className="font-semibold">{fa.trend}</div></div>
                <div><div className="text-xs uppercase text-ink2">RSI (14)</div><div className="font-semibold">{fa.rsi14 ?? "-"}</div></div>
                <div><div className="text-xs uppercase text-ink2">ATR (14) % of price</div><div className="font-semibold">{fa.atr14_pct_of_price}%</div></div>
                <div><div className="text-xs uppercase text-ink2">20-bar range</div><div className="font-semibold">{fmt(fa.range_20_bars.low, 2)} to {fmt(fa.range_20_bars.high, 2)}</div></div>
                <div><div className="text-xs uppercase text-ink2">Candles used</div><div className="font-semibold">{fa.bars}</div></div>
              </div>
            </Card>
          )}
          <p className="text-xs text-ink2">{res.disclaimer}</p>
        </>
      )}
    </div>
  );
}

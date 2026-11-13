"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useApi, useLoad } from "@/lib/api";
import type { Account, Spec, Strategy } from "@/lib/types";
import ConditionEditor from "@/components/StrategyBuilder";
import { Button, Card, Field, Input, Notice, Select } from "@/components/ui";

const BLANK: Spec = {
  symbol: "RELIANCE", exchange: "NSE", interval: "5m", side: "long",
  entry: { all: [{ left: { ind: "ema", period: 9 }, op: "crosses_above", right: { ind: "ema", period: 21 } }] },
  exit: { all: [{ left: { ind: "ema", period: 9 }, op: "crosses_below", right: { ind: "ema", period: 21 } }] },
  risk: { qty: 1 },
};

export default function StrategyPage() {
  const { id } = useParams<{ id: string }>(); const isNew = id === "new"; const router = useRouter(); const searchParams = useSearchParams();
  const requestedTemplate = searchParams.get("template") ?? ""; const [appliedTemplate, setAppliedTemplate] = useState("");
  const { ready, call, config } = useApi();
  const templates = useLoad<{ key: string; name: string; category?: string; description?: string; research_note?: string; spec: Partial<Spec> }[]>("/api/strategies/templates");
  const accounts = useLoad<Account[]>("/api/brokers/accounts");
  const [name, setName] = useState("My strategy"); const [spec, setSpec] = useState<Spec>(BLANK);
  const [saved, setSaved] = useState<Strategy | null>(null); const [msg, setMsg] = useState<{ k: "ok" | "error"; t: string } | null>(null); const [busy, setBusy] = useState(false);
  const [src, setSrc] = useState("auto"); const [bars, setBars] = useState(1000); const [cost, setCost] = useState(5);

  useEffect(() => { if (ready && !isNew) call<Strategy>(`/api/strategies/${id}`).then((s) => { setSaved(s); setName(s.name); setSpec(s.spec); }).catch((e) => setMsg({ k: "error", t: e.message })); }, [ready, id, isNew, call]);

  useEffect(() => {
    if (!isNew || !requestedTemplate || appliedTemplate === requestedTemplate || !templates.data) return;
    const selected = templates.data.find((t) => t.key === requestedTemplate);
    if (!selected) return;
    setName(selected.name);
    setSpec({ ...BLANK, ...selected.spec, risk: { ...BLANK.risk, ...(selected.spec.risk ?? {}) } } as Spec);
    setAppliedTemplate(requestedTemplate);
  }, [isNew, requestedTemplate, appliedTemplate, templates.data]);

  const up = (p: Partial<Spec>) => setSpec((s) => ({ ...s, ...p }));
  const risk = spec.risk ?? {}; const upRisk = (p: Record<string, number | string | undefined>) => up({ risk: { ...risk, ...p } });
  const num = (v: string) => (v === "" ? undefined : Number(v));
  const locked = saved?.mode !== undefined && saved.mode !== "off";

  async function save() {
    setBusy(true); setMsg(null);
    try {
      const s = isNew ? await call<Strategy>("/api/strategies", { method: "POST", body: JSON.stringify({ name, spec }) }) : await call<Strategy>(`/api/strategies/${id}`, { method: "PUT", body: JSON.stringify({ name, spec }) });
      setSaved(s); setMsg({ k: "ok", t: "Saved" }); if (isNew) router.replace(`/strategies/${s.id}`);
    } catch (e) { setMsg({ k: "error", t: (e as Error).message }); } finally { setBusy(false); }
  }
  async function backtest() {
    setBusy(true); setMsg(null);
    try { const b = await call("/api/backtests", { method: "POST", body: JSON.stringify({ spec, strategy_id: saved?.id, source: src, bars, cost_bps: cost }) }); router.push(`/backtests/${b.id}`); }
    catch (e) { setMsg({ k: "error", t: (e as Error).message }); setBusy(false); }
  }
  async function setMode(mode: string, account_id?: number) {
    setMsg(null);
    try { const s = await call<Strategy>(`/api/strategies/${saved!.id}/mode`, { method: "PATCH", body: JSON.stringify({ mode, account_id }) }); setSaved(s); setMsg({ k: "ok", t: `Mode: ${mode}` }); }
    catch (e) { setMsg({ k: "error", t: (e as Error).message }); }
  }
  const liveAccounts = (accounts.data ?? []).filter((a) => a.live_enabled && (a.kind === "kite" || (a.kind === "ccxt" && a.crypto?.trade === true)));

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-bold">{isNew ? "New strategy" : "Edit strategy"}</h1>
      {locked && <Notice kind="warn">This strategy is running in <b>{saved?.mode}</b> mode. Turn it off to edit.</Notice>}
      <Card title="Start from a template">
        <div className="flex flex-wrap gap-2">{(templates.data ?? []).map((t) => <Button key={t.key} variant="ghost" disabled={locked} onClick={() => { setName(t.name); setSpec({ ...spec, ...t.spec, risk: { ...(t.spec.risk ?? {}), qty: risk.qty ?? 1 } } as Spec); }}>{t.name}</Button>)}</div>
      </Card>
      <Card title="Market">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} disabled={locked} /></Field>
          <Field label="Symbol"><Input value={spec.symbol} onChange={(e) => up({ symbol: e.target.value.toUpperCase() })} disabled={locked} /></Field>
          <Field label="Exchange"><Select value={spec.exchange} onChange={(e) => up({ exchange: e.target.value })} disabled={locked}>{["NSE", "BSE", "NFO", "MCX", "CRYPTO"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
          <Field label="Candle"><Select value={spec.interval} onChange={(e) => up({ interval: e.target.value })} disabled={locked}>{["1m", "5m", "15m", "1h", "1d"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
        </div>
      </Card>
      <Card title="Rules">
        <div className="grid gap-4">
          <Field label="Direction"><Select value={spec.side ?? "long"} onChange={(e) => up({ side: e.target.value as "long" | "short" })} disabled={locked}><option value="long">Long (buy)</option><option value="short">Short (sell; needs shorting enabled in risk limits)</option></Select></Field>
          <ConditionEditor title="Enter when" group={spec.entry} onChange={(entry) => !locked && up({ entry })} />
          <ConditionEditor title="Exit when" group={spec.exit ?? { all: [] }} onChange={(exit) => !locked && up({ exit })} />
        </div>
      </Card>
      <Card title="Risk and size">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Fixed quantity"><Input type="number" min={1} value={risk.qty ?? ""} onChange={(e) => upRisk({ qty: num(e.target.value) })} disabled={locked} /></Field>
          <Field label="Stop-loss %"><Input type="number" step="0.1" min={0} value={risk.stop_pct ?? ""} onChange={(e) => upRisk({ stop_pct: num(e.target.value) })} disabled={locked} /></Field>
          <Field label="Take-profit %"><Input type="number" step="0.1" min={0} value={risk.take_pct ?? ""} onChange={(e) => upRisk({ take_pct: num(e.target.value) })} disabled={locked} /></Field>
          <Field label="Square off at (HH:MM, IST)"><Input placeholder="15:15" value={risk.square_off ?? ""} onChange={(e) => upRisk({ square_off: e.target.value || undefined })} disabled={locked} /></Field>
          <Field label="ATR sizing: equity"><Input type="number" min={0} value={risk.equity ?? ""} onChange={(e) => upRisk({ equity: num(e.target.value) })} disabled={locked} /></Field>
          <Field label="ATR sizing: risk % per trade"><Input type="number" step="0.1" min={0} value={risk.risk_pct ?? ""} onChange={(e) => upRisk({ risk_pct: num(e.target.value) })} disabled={locked} /></Field>
          <Field label="Max quantity"><Input type="number" min={1} value={risk.max_qty ?? ""} onChange={(e) => upRisk({ max_qty: num(e.target.value) })} disabled={locked} /></Field>
          <Field label="Capital for this strategy"><Input type="number" min={0} value={risk.capital ?? ""} onChange={(e) => upRisk({ capital: num(e.target.value) })} disabled={locked} /></Field>
          <Field label="Circuit breaker: last N trades"><Input type="number" min={2} value={risk.breaker_trades ?? ""} placeholder="10" onChange={(e) => upRisk({ breaker_trades: num(e.target.value) })} disabled={locked} /></Field>
          <Field label="Circuit breaker: switch off if loss exceeds % of capital"><Input type="number" step="0.5" min={0} value={risk.breaker_loss_pct ?? ""} placeholder="3" onChange={(e) => upRisk({ breaker_loss_pct: num(e.target.value) })} disabled={locked} /></Field>
        </div>
        <p className="mt-2 text-xs text-ink2">The circuit breaker switches the strategy off automatically if its recent closed trades lose more than the set share of its capital, or if orders keep failing. If both ATR fields are set, quantity is sized so a 2-ATR stop loses about that percent of equity. Otherwise the fixed quantity is used.</p>
      </Card>
      {msg && <Notice kind={msg.k}>{msg.t}</Notice>}
      <Card title="Test">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Data"><Select value={src} onChange={(e) => setSrc(e.target.value)}><option value="auto">Auto</option><option value="demo">Demo (synthetic)</option><option value="crypto">Crypto (public)</option><option value="recorded">Recorded live ticks (real, from this server)</option></Select></Field>
          <Field label="Candles"><Input type="number" min={60} max={5000} value={bars} onChange={(e) => setBars(Number(e.target.value))} className="w-28" /></Field>
          <Field label="Cost (bps per change)"><Input type="number" min={0} step="0.5" value={cost} onChange={(e) => setCost(Number(e.target.value))} className="w-28" /></Field>
          <Button onClick={backtest} disabled={busy}>Run backtest</Button><Button variant="ghost" onClick={save} disabled={busy || locked}>Save</Button>
        </div>
        <p className="mt-2 text-xs text-ink2">Demo data is random and proves nothing. Use your broker or crypto data for real results.</p>
      </Card>
      {saved && (
        <Card title="Automation">
          <p className="mb-3 text-sm text-ink2">Current: <b className="uppercase">{saved.mode}</b>{saved.last_run && <> · last check {new Date(saved.last_run).toLocaleString()} · target position {saved.last_target}</>}</p>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" onClick={() => setMode("off")} disabled={saved.mode === "off"}>Off</Button>
            <Button onClick={() => setMode("paper")} disabled={saved.mode === "paper"}>Run in paper mode</Button>
            {liveAccounts.length === 0 ? <span className="text-sm text-ink2">{config?.live_available === false ? "Real-money trading needs login: turn it on in Settings, Access." : "Live needs a broker account with live trading enabled (Brokers page)."}</span> :
              liveAccounts.map((a) => <Button key={a.id} variant="danger" onClick={() => confirm(`Trade REAL money on ${a.label}?`) && setMode("live", a.id)}>Go live on {a.label}</Button>)}
          </div>
        </Card>
      )}
    </div>
  );
}

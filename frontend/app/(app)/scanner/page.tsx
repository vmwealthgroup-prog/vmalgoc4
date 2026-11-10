"use client";
import { useState } from "react";
import { useApi, useLoad } from "@/lib/api";
import { fmt } from "@/lib/types";
import { Button, Card, Field, Input, Notice, Select, Table } from "@/components/ui";

export default function Scanner() {
  const { call } = useApi(); const presets = useLoad<{ key: string; name: string; conditions: any }[]>("/api/scanner/presets");
  const [preset, setPreset] = useState("oversold"); const [symbols, setSymbols] = useState("RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, SBIN, ITC, LT, AXISBANK, KOTAKBANK");
  const [exchange, setExchange] = useState("NSE"); const [interval, setIv] = useState("1d"); const [source, setSource] = useState("auto");
  const [res, setRes] = useState<any>(null); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true); setErr("");
    try {
      const conditions = presets.data?.find((p) => p.key === preset)?.conditions;
      setRes(await call("/api/scanner/run", { method: "POST", body: JSON.stringify({ symbols: symbols.split(/[,\s]+/).filter(Boolean), exchange, interval, source, conditions }) }));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-bold">Stock scanner</h1>
      <Card>
        <div className="grid gap-4 md:grid-cols-4">
          <Field label="Scan for"><Select value={preset} onChange={(e) => setPreset(e.target.value)}>{(presets.data ?? []).map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}</Select></Field>
          <Field label="Exchange"><Select value={exchange} onChange={(e) => setExchange(e.target.value)}>{["NSE", "BSE", "NFO", "MCX", "CRYPTO"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
          <Field label="Candle"><Select value={interval} onChange={(e) => setIv(e.target.value)}>{["5m", "15m", "1h", "1d"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
          <Field label="Data"><Select value={source} onChange={(e) => setSource(e.target.value)}><option value="auto">Auto</option><option value="demo">Demo (synthetic)</option><option value="openalgo">My OpenAlgo broker</option><option value="recorded">Recorded live ticks</option></Select></Field>
        </div>
        <div className="mt-4 grid gap-4"><Field label="Symbols (comma separated, up to 50)"><Input value={symbols} onChange={(e) => setSymbols(e.target.value)} /></Field><div><Button onClick={run} disabled={busy}>{busy ? "Scanning…" : "Run scan"}</Button></div></div>
      </Card>
      {err && <Notice kind="error">{err}</Notice>}
      {res && (
        <Card title={`${res.matches} match${res.matches === 1 ? "" : "es"} of ${res.scanned} scanned`} right={<span className="text-xs text-ink2">data: {res.data_source}</span>}>
          {res.data_source === "demo" && <div className="mb-3"><Notice kind="warn">Demo data is synthetic: these matches are not real market setups.</Notice></div>}
          <Table head={["Symbol", "Match", "Close", "RSI 14", "EMA 20"]}>
            {res.results.map((r: any) => <tr key={r.symbol} className={r.match ? "bg-gain/5" : ""}><td className="font-medium">{r.symbol}</td><td>{r.match ? "✔ Yes" : "No"}</td><td>{fmt(r.close)}</td><td>{fmt(r.rsi, 1)}</td><td>{fmt(r.ema20)}</td></tr>)}
          </Table>
          {res.errors.length > 0 && <div className="mt-3"><Notice kind="warn">Could not scan: {res.errors.map((e: any) => `${e.symbol} (${e.error})`).join("; ")}</Notice></div>}
          <p className="mt-3 text-xs text-ink2">Matches use the last completed candle.</p>
        </Card>
      )}
    </div>
  );
}

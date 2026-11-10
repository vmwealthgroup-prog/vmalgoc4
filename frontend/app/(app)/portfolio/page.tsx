"use client";
import { useState } from "react";
import { useApi, useLoad } from "@/lib/api";
import { fmt, type Account, type Position } from "@/lib/types";
import { Button, Card, Field, Input, Notice, Pnl, Select, Stat, Table } from "@/components/ui";

export default function Portfolio() {
  const accounts = useLoad<Account[]>("/api/brokers/accounts"); const [aid, setAid] = useState<number | "">("");
  const { data, error, reload } = useLoad<any>(`/api/portfolio${aid ? `?account_id=${aid}` : ""}`, 10000);
  const { call } = useApi(); const [f, setF] = useState({ symbol: "RELIANCE", exchange: "NSE", side: "BUY", qty: 1, price: 100 }); const [out, setOut] = useState<any>(null); const [err, setErr] = useState("");
  async function order() {
    setErr(""); setOut(null);
    try { setOut(await call("/api/orders", { method: "POST", body: JSON.stringify({ ...f, mode: "paper" }) })); reload(); } catch (e) { setErr((e as Error).message); }
  }
  const rows = (ps: Position[]) => ps.map((p, i) => <tr key={i}><td className="font-medium">{p.symbol} <span className="text-ink2">{p.exchange}</span></td><td>{fmt(p.qty, 0)}</td><td>{fmt(p.avg_price)}</td><td>{fmt(p.ltp)}</td><td><Pnl v={p.pnl} /></td></tr>);
  const funds = data?.funds ?? {};
  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">Portfolio</h1>
        <Select aria-label="Account" value={aid} onChange={(e) => setAid(e.target.value ? Number(e.target.value) : "")}><option value="">Paper account</option>{(accounts.data ?? []).filter((a) => a.kind !== "paper").map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}</Select></div>
      {(error || data?.error) && <Notice kind="error">{error || data.error}</Notice>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Cash" value={fmt(funds.cash, 0)} /><Stat label="Equity" value={funds.equity ? fmt(funds.equity, 0) : "-"} />
        <Stat label="Open positions" value={data?.positions.length ?? "-"} /><Stat label="P&L" value={data ? <Pnl v={data.totals.pnl} /> : "-"} tone={data && data.totals.pnl >= 0 ? "gain" : "loss"} />
      </div>
      <Card title="Positions">{!data ? <p className="text-ink2">Loading…</p> : data.positions.length === 0 ? <p className="text-sm text-ink2">No open positions.</p> : <Table head={["Instrument", "Qty", "Avg price", "LTP", "P&L"]}>{rows(data.positions)}</Table>}</Card>
      {data && data.holdings.length > 0 && <Card title="Holdings"><Table head={["Instrument", "Qty", "Avg price", "LTP", "P&L"]}>{rows(data.holdings)}</Table></Card>}
      {!aid && (
        <Card title="Manual paper order">
          <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <Field label="Symbol"><Input value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value.toUpperCase() })} /></Field>
            <Field label="Exchange"><Select value={f.exchange} onChange={(e) => setF({ ...f, exchange: e.target.value })}>{["NSE", "BSE", "NFO", "MCX", "CRYPTO"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
            <Field label="Side"><Select value={f.side} onChange={(e) => setF({ ...f, side: e.target.value })}><option>BUY</option><option>SELL</option></Select></Field>
            <Field label="Qty"><Input type="number" min={1} value={f.qty} onChange={(e) => setF({ ...f, qty: Number(e.target.value) })} /></Field>
            <Field label="Ref. price"><Input type="number" min={0} step="any" value={f.price} onChange={(e) => setF({ ...f, price: Number(e.target.value) })} /></Field>
            <div className="self-end"><Button onClick={order}>Place order</Button></div>
          </div>
          {err && <div className="mt-3"><Notice kind="error">{err}</Notice></div>}
          {out && <div className="mt-3"><Notice kind={out.status === "filled" ? "ok" : "warn"}>{out.status.toUpperCase()}: {out.message}</Notice></div>}
          <p className="mt-2 text-xs text-ink2">Every order passes the risk gate (Settings). Paper fills use the latest feed price.</p>
        </Card>
      )}
    </div>
  );
}

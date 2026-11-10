"use client";
import { useState } from "react";
import { API } from "@/lib/env";
import { useApi, useLoad } from "@/lib/api";
import { Button, Card, Field, Input, Notice, Table } from "./ui";

type Hook = { id: number; name: string; mode: string; hits: number; last_used_at: string | null };

export default function Webhooks() {
  const { call } = useApi(); const hooks = useLoad<Hook[]>("/api/webhooks");
  const [name, setName] = useState("TradingView"); const [created, setCreated] = useState<{ url: string } | null>(null); const [err, setErr] = useState("");
  const base = API || (typeof window !== "undefined" ? window.location.origin : "");
  async function create() {
    setErr(""); setCreated(null);
    try { const r = await call("/api/webhooks", { method: "POST", body: JSON.stringify({ name, mode: "paper" }) }); setCreated({ url: `${base}${r.path}` }); hooks.reload(); }
    catch (e) { setErr((e as Error).message); }
  }
  async function del(id: number) { if (confirm("Delete this webhook? Alerts using it will stop working.")) { await call(`/api/webhooks/${id}`, { method: "DELETE" }); hooks.reload(); } }
  return (
    <Card title="TradingView alerts (webhooks)">
      <p className="mb-3 text-sm text-ink2">Send TradingView alerts here and they become orders, through the same risk checks as everything else. New webhooks are <b>paper only</b>.</p>
      <div className="flex flex-wrap items-end gap-3"><Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} className="w-56" /></Field><Button onClick={create}>Create webhook</Button></div>
      {err && <div className="mt-3"><Notice kind="error">{err}</Notice></div>}
      {created && (
        <div className="mt-3 grid gap-2"><Notice kind="warn">Copy this URL now. It contains a secret and is not shown again.</Notice>
          <input readOnly aria-label="Webhook URL" value={created.url} onFocus={(e) => e.target.select()} className="w-full rounded-lg border border-line bg-paper px-3 py-2 font-mono text-xs" /></div>
      )}
      <div className="mt-4 text-sm"><div className="mb-1 font-medium">Alert message to use in TradingView</div>
        <pre className="overflow-x-auto rounded-lg bg-paper p-3 text-xs">{`{"action": "buy", "symbol": "TCS", "exchange": "NSE", "qty": 5}

Crypto (BTCUSDT and BINANCE:BTCUSDT both work):
{"action": "buy", "symbol": "BTCUSDT", "exchange": "CRYPTO", "qty": 0.01}`}</pre>
        <p className="mt-1 text-xs text-ink2">action: buy, sell or close (close flattens what is open). Optional: price, product (MIS, CNC, NRML). Paste the webhook URL into the alert's Webhook URL box.</p></div>
      {(hooks.data?.length ?? 0) > 0 && (
        <div className="mt-4"><Table head={["Name", "Mode", "Alerts received", "Last used", ""]}>
          {hooks.data!.map((h) => <tr key={h.id}><td>{h.name}</td><td>{h.mode}</td><td>{h.hits}</td><td>{h.last_used_at ? new Date(h.last_used_at).toLocaleString() : "never"}</td><td className="text-right"><Button variant="ghost" onClick={() => del(h.id)}>Delete</Button></td></tr>)}
        </Table></div>
      )}
    </Card>
  );
}

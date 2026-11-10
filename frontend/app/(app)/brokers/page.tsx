"use client";
import { useState } from "react";
import { useApi, useLoad } from "@/lib/api";
import type { Account } from "@/lib/types";
import { Button, Card, Field, Input, Notice, Select } from "@/components/ui";

const CRYPTO = ["coinbase", "kraken", "bybit", "okx", "binance", "kucoin"];
type Kind = "openalgo" | "kite" | "crypto";

export default function Brokers() {
  const { call, config } = useApi();
  const accounts = useLoad<Account[]>("/api/brokers/accounts"); const sup = useLoad<{ brokers: string[]; live_trading_enabled_on_server: boolean }>("/api/brokers/supported");
  const ip = useLoad<{ ip: string | null; note?: string; error?: string }>("/api/system/egress-ip");
  const [kind, setKind] = useState<Kind>("openalgo");
  const [f, setF] = useState({ label: "", broker_name: "zerodha", host: "http://127.0.0.1:5000", api_key: "", api_secret: "", exchange: "coinbase", quote: "USDT", trade: false, sandbox: true });
  const [msg, setMsg] = useState<{ k: "ok" | "error" | "warn"; t: string } | null>(null); const [tests, setTests] = useState<Record<number, string>>({}); const [rt, setRt] = useState<Record<number, string>>({});
  const say = (k: "ok" | "error" | "warn", t: string) => setMsg({ k, t });

  async function add(e: React.FormEvent) {
    e.preventDefault(); setMsg(null);
    try {
      if (kind === "openalgo") await call("/api/brokers/accounts", { method: "POST", body: JSON.stringify({ label: f.label, broker_name: f.broker_name, host: f.host, api_key: f.api_key }) });
      else if (kind === "kite") await call("/api/brokers/accounts/kite", { method: "POST", body: JSON.stringify({ label: f.label, api_key: f.api_key, api_secret: f.api_secret }) });
      else await call("/api/brokers/accounts/crypto", { method: "POST", body: JSON.stringify({ label: f.label, exchange: f.exchange, api_key: f.api_key, api_secret: f.api_secret, quote: f.quote, trade: f.trade, sandbox: f.sandbox }) });
      setF({ ...f, label: "", api_key: "", api_secret: "" }); accounts.reload(); say("ok", kind === "kite" ? "Added. Now press Daily login to get today's access token." : "Account added. Test the connection before use.");
    } catch (x) { say("error", (x as Error).message); }
  }
  async function test(id: number) {
    setTests((t) => ({ ...t, [id]: "Testing…" }));
    const r = await call(`/api/brokers/accounts/${id}/test`, { method: "POST" });
    setTests((t) => ({ ...t, [id]: r.ok ? `Connected. Cash ${r.funds.cash}` : `Failed: ${r.error}` }));
  }
  async function dailyLogin(id: number) {
    try { const r = await call(`/api/brokers/accounts/${id}/kite/login-url`); window.open(r.url, "_blank", "noopener"); say("warn", "Log in to Zerodha in the new tab. If you are not sent back here automatically, paste the request_token from the address bar below."); }
    catch (x) { say("error", (x as Error).message); }
  }
  async function finishLogin(id: number) {
    try { await call(`/api/brokers/accounts/${id}/kite/session`, { method: "POST", body: JSON.stringify({ request_token: rt[id] }) }); setRt((t) => ({ ...t, [id]: "" })); accounts.reload(); say("ok", "Zerodha login complete for today."); }
    catch (x) { say("error", (x as Error).message); }
  }
  async function live(a: Account, enabled: boolean) {
    setMsg(null);
    const password = enabled ? prompt("This allows REAL orders on this account when a strategy is set to live. Enter your password to confirm.") : "x";
    if (!password) return;
    try { await call(`/api/brokers/accounts/${a.id}/live`, { method: "PATCH", body: JSON.stringify({ enabled, password }) }); accounts.reload(); }
    catch (x) { say("error", (x as Error).message); }
  }
  async function del(id: number) { if (confirm("Remove this broker account?")) { await call(`/api/brokers/accounts/${id}`, { method: "DELETE" }); accounts.reload(); } }
  const serverLive = sup.data?.live_trading_enabled_on_server;
  const label = (a: Account) => (a.kind === "paper" ? "paper" : a.kind === "ccxt" ? `${a.broker_name} (${a.crypto?.trade ? "trading" : "read-only"}${a.crypto?.sandbox ? ", test network" : ""})` : a.broker_name || "openalgo");

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-bold">Brokers</h1>
      <Notice kind="info">Connect <b>Zerodha</b> directly, or any of 35+ Indian brokers (Angel One, Upstox, Dhan, Fyers, Kotak and more) through your own <b>OpenAlgo</b> gateway. Keys are encrypted at rest. Indian brokers require a fresh login each trading day.</Notice>
      {config && !config.brokers_available && <Notice kind="warn">Broker connections are disabled while this hosted server is in open mode. Turn on login in Settings, Access, to connect a broker.</Notice>}
      {config && config.brokers_available && !config.live_available && <Notice kind="info">Open mode is paper only: real-money trading needs login. You can still connect a broker here to read its portfolio and data.</Notice>}
      {sup.data && !serverLive && <Notice kind="warn">Live trading is switched <b>off</b> on this server, so all orders stay paper. The server owner enables it with LIVE_TRADING_ENABLED=true.</Notice>}
      {msg && <Notice kind={msg.k}>{msg.t}</Notice>}
      <Card title="Your server's IP address">
        {ip.data?.ip ? <><p className="font-mono text-lg">{ip.data.ip}</p><p className="mt-1 text-sm text-ink2">Indian brokers accept API orders only from a static IP you have registered with them. Register this one (and keep it fixed: use a static/elastic IP on your host).</p></>
          : <p className="text-sm text-ink2">{ip.data?.error ?? "Checking…"}</p>}
      </Card>
      <Card title="Your accounts">
        <ul className="grid gap-3">
          {(accounts.data ?? []).map((a) => (
            <li key={a.id} className="grid gap-2 rounded-lg border border-line p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div><div className="font-medium">{a.label} <span className="text-xs uppercase text-ink2">{label(a)}</span></div>
                  {a.kind !== "paper" && <div className="text-xs text-ink2">{a.kind === "openalgo" ? `${a.host} · ` : ""}live trading {a.live_enabled ? <b className="text-loss">ENABLED</b> : "disabled"}{a.kind === "kite" && (a.token_ok ? <> · <b className="text-gain">logged in today</b></> : <> · <b className="text-loss">daily login needed</b></>)}</div>}
                  {tests[a.id] && <div className="text-xs">{tests[a.id]}</div>}</div>
                {a.kind !== "paper" && <div className="flex flex-wrap gap-2">
                  {a.kind === "kite" && <Button onClick={() => dailyLogin(a.id)}>Daily login</Button>}
                  <Button variant="ghost" onClick={() => test(a.id)}>Test</Button>
                  {(a.kind !== "ccxt" || a.crypto?.trade) && <Button variant={a.live_enabled ? "ghost" : "danger"} onClick={() => live(a, !a.live_enabled)}>{a.live_enabled ? "Disable live" : "Enable live"}</Button>}
                  <Button variant="ghost" onClick={() => del(a.id)}>Remove</Button></div>}
              </div>
              {a.kind === "kite" && !a.token_ok && (
                <div className="flex flex-wrap items-end gap-2"><Field label="request_token from the redirect address"><Input value={rt[a.id] ?? ""} onChange={(e) => setRt((t) => ({ ...t, [a.id]: e.target.value }))} className="w-72" /></Field><Button variant="ghost" onClick={() => finishLogin(a.id)} disabled={!rt[a.id]}>Finish login</Button></div>
              )}
            </li>
          ))}
        </ul>
      </Card>
      {config?.brokers_available !== false && (
        <Card title="Add an account">
          <div className="mb-4 max-w-xs"><Field label="Type"><Select value={kind} onChange={(e) => setKind(e.target.value as Kind)}><option value="openalgo">Any Indian broker via OpenAlgo</option><option value="kite">Zerodha direct (Kite Connect)</option><option value="crypto">Crypto exchange (read-only or trading)</option></Select></Field></div>
          <form onSubmit={add} className="grid gap-4 sm:grid-cols-2">
            <Field label="Label"><Input required value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} placeholder="My account" /></Field>
            {kind === "openalgo" && <>
              <Field label="Broker"><Select value={f.broker_name} onChange={(e) => setF({ ...f, broker_name: e.target.value })}>{(sup.data?.brokers ?? ["zerodha", "angel"]).map((b) => <option key={b}>{b}</option>)}</Select></Field>
              <Field label="OpenAlgo URL"><Input required value={f.host} onChange={(e) => setF({ ...f, host: e.target.value })} /></Field>
              <Field label="OpenAlgo API key"><Input required type="password" minLength={8} autoComplete="off" value={f.api_key} onChange={(e) => setF({ ...f, api_key: e.target.value })} /></Field></>}
            {kind === "kite" && <>
              <Field label="Kite Connect API key"><Input required type="password" minLength={6} autoComplete="off" value={f.api_key} onChange={(e) => setF({ ...f, api_key: e.target.value })} /></Field>
              <Field label="Kite Connect API secret"><Input required type="password" minLength={6} autoComplete="off" value={f.api_secret} onChange={(e) => setF({ ...f, api_secret: e.target.value })} /></Field>
              <p className="text-xs text-ink2 sm:col-span-2">Set the redirect URL of your Kite Connect app to <span className="font-mono">{typeof window !== "undefined" ? window.location.origin : ""}/brokers/kite-callback</span> so the daily login completes automatically.</p></>}
            {kind === "crypto" && <>
              <Field label="Exchange"><Select value={f.exchange} onChange={(e) => setF({ ...f, exchange: e.target.value })}>{CRYPTO.map((x) => <option key={x}>{x}</option>)}</Select></Field>
              <Field label="API key (read-only permission only)"><Input required type="password" autoComplete="off" value={f.api_key} onChange={(e) => setF({ ...f, api_key: e.target.value })} /></Field>
              <Field label="API secret"><Input required type="password" autoComplete="off" value={f.api_secret} onChange={(e) => setF({ ...f, api_secret: e.target.value })} /></Field>
              <Field label="Quote currency"><Input value={f.quote} onChange={(e) => setF({ ...f, quote: e.target.value.toUpperCase() })} /></Field>
              <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={f.sandbox} onChange={(e) => setF({ ...f, sandbox: e.target.checked })} />Use the exchange's test network (no real money). Untick for the real exchange.</label>
              <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={f.trade} onChange={(e) => setF({ ...f, trade: e.target.checked })} /><span>Allow this account to place orders. Leave off for balances only. Use API keys with trading permission and <b>withdrawals disabled</b>. Real orders still need every live switch.</span></label></>}
            <div className="sm:col-span-2"><Button>Add account</Button></div>
          </form>
        </Card>
      )}
    </div>
  );
}

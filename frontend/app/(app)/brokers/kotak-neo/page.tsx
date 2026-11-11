"use client";

import { useState } from "react";
import { useApi, useLoad } from "@/lib/api";
import type { Account } from "@/lib/types";
import { Button, Card, Field, Input, Notice } from "@/components/ui";

type NeoAccount = Account & { auth_stage?: string };
export default function KotakNeoPage() {
  const { call, config } = useApi();
  const accounts = useLoad<NeoAccount[]>("/api/brokers/accounts");
  const [label, setLabel] = useState("My Kotak Neo");
  const [consumerKey, setConsumerKey] = useState("");
  const [mobile, setMobile] = useState("");
  const [ucc, setUcc] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [totp, setTotp] = useState("");
  const [mpin, setMpin] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "error" | "warn"; text: string } | null>(null);
  const [snapshot, setSnapshot] = useState<Record<string, { ok: boolean; data?: unknown; error?: string }> | null>(null);
  const [exchangeSegment, setExchangeSegment] = useState("nse_cm");
  const [symbol, setSymbol] = useState("RELIANCE");
  const [scripResult, setScripResult] = useState<unknown>(null);
  const [instrumentToken, setInstrumentToken] = useState("");
  const [quoteResult, setQuoteResult] = useState<unknown>(null);
  const neoAccounts = (accounts.data ?? []).filter((a) => a.kind === "kotak_neo");
  const activeId = selected ?? neoAccounts[0]?.id ?? null;

  async function addAccount(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setNotice(null);
    try {
      const created = await call<NeoAccount>("/api/brokers/accounts/kotak-neo", {
        method: "POST",
        body: JSON.stringify({ label, consumer_key: consumerKey, mobile_number: mobile, ucc }),
      });
      setConsumerKey(""); setMobile(""); setUcc(""); setSelected(created.id);
      await accounts.reload();
      setNotice({ kind: "ok", text: "Kotak Neo account saved with encrypted credentials. Continue with TOTP login." });
    } catch (e) { setNotice({ kind: "error", text: (e as Error).message }); }
    finally { setBusy(false); }
  }

  async function authenticate(step: "totp" | "mpin") {
    if (!activeId) return;
    setBusy(true); setNotice(null);
    try {
      await call(`/api/brokers/accounts/${activeId}/kotak-neo/${step}`, {
        method: "POST", body: JSON.stringify(step === "totp" ? { totp } : { mpin }),
      });
      setTotp(""); setMpin("");
      await accounts.reload();
      setNotice({ kind: "ok", text: step === "totp" ? "TOTP accepted. Enter MPIN to complete authentication." : "Kotak Neo session established. Live trading remains disabled." });
    } catch (e) { setNotice({ kind: "error", text: (e as Error).message }); }
    finally { setBusy(false); }
  }

  async function loadSnapshot() {
    if (!activeId) return;
    setBusy(true); setNotice(null);
    try {
      const result = await call<Record<string, { ok: boolean; data?: unknown; error?: string }>>(
        `/api/brokers/accounts/${activeId}/kotak-neo/snapshot`,
      );
      setSnapshot(result);
      const failed = Object.values(result).filter((v) => !v.ok).length;
      setNotice({ kind: failed ? "warn" : "ok", text: failed ? `Account data loaded with ${failed} section(s) unavailable.` : "Read-only account data refreshed successfully." });
    } catch (e) { setNotice({ kind: "error", text: (e as Error).message }); }
    finally { setBusy(false); }
  }

  async function searchScrip() {
    if (!activeId) return;
    setBusy(true); setNotice(null);
    try {
      const result = await call<unknown>(`/api/brokers/accounts/${activeId}/kotak-neo/scrip-search`, {
        method: "POST", body: JSON.stringify({ exchange_segment: exchangeSegment, symbol }),
      });
      setScripResult(result);
      setNotice({ kind: "ok", text: "Scrip search completed. Verify the returned instrument token and exchange before requesting quotes." });
    } catch (e) { setNotice({ kind: "error", text: (e as Error).message }); }
    finally { setBusy(false); }
  }

  async function fetchQuote() {
    if (!activeId || !instrumentToken.trim()) return;
    setBusy(true); setNotice(null);
    try {
      const result = await call<unknown>(`/api/brokers/accounts/${activeId}/kotak-neo/quotes`, {
        method: "POST",
        body: JSON.stringify({ instruments: [{ instrument_token: instrumentToken.trim(), exchange_segment: exchangeSegment }], quote_type: "all" }),
      });
      setQuoteResult(result);
      setNotice({ kind: "ok", text: "Market quote request completed." });
    } catch (e) { setNotice({ kind: "error", text: (e as Error).message }); }
    finally { setBusy(false); }
  }

  async function removeAccount(id: number) {
    if (!confirm("Remove this Kotak Neo account and its encrypted session?")) return;
    setBusy(true);
    try { await call(`/api/brokers/accounts/${id}`, { method: "DELETE" }); setSelected(null); await accounts.reload(); setNotice({ kind: "ok", text: "Kotak Neo account removed." }); }
    catch (e) { setNotice({ kind: "error", text: (e as Error).message }); }
    finally { setBusy(false); }
  }

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-gold">Broker integration</p><h1 className="mt-1 text-2xl font-bold">Kotak Neo API</h1><p className="mt-1 text-sm text-ink2">Secure two-step authentication and session management.</p></div>
        <span className="rounded-full border border-gold/50 bg-gold/10 px-3 py-1 text-xs font-semibold text-ink">PAPER MODE · LIVE DISABLED</span>
      </div>
      {config && !config.brokers_available && <Notice kind="warn">Broker connections are disabled in hosted open mode. Enable login in Settings → Access.</Notice>}
      {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}
      <Card title="Kotak Neo accounts">
        {neoAccounts.length === 0 ? <p className="text-sm text-ink2">No Kotak Neo account configured yet.</p> : <div className="grid gap-2">
          {neoAccounts.map((a) => <div key={a.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line p-3">
            <button className="text-left" onClick={() => setSelected(a.id)}><span className="font-semibold">{a.label}</span><span className="ml-2 text-xs text-ink2">{a.auth_stage === "connected" ? "CONNECTED" : a.auth_stage === "view_session" ? "TOTP VERIFIED · MPIN REQUIRED" : "LOGIN REQUIRED"}</span></button>
            <Button variant="ghost" disabled={busy} onClick={() => removeAccount(a.id)}>Remove</Button>
          </div>)}
        </div>}
      </Card>
      <Card title="Add Kotak Neo account">
        <form onSubmit={addAccount} className="grid gap-3 sm:grid-cols-2">
          <Field label="Account label"><Input required value={label} onChange={(e) => setLabel(e.target.value)} maxLength={80} /></Field>
          <Field label="Consumer key / API access token"><Input required type="password" autoComplete="off" value={consumerKey} onChange={(e) => setConsumerKey(e.target.value)} /></Field>
          <Field label="Registered mobile (+91...)"><Input required value={mobile} onChange={(e) => setMobile(e.target.value)} placeholder="+91XXXXXXXXXX" autoComplete="off" /></Field>
          <Field label="UCC / Client code"><Input required value={ucc} onChange={(e) => setUcc(e.target.value)} autoComplete="off" /></Field>
          <div className="sm:col-span-2"><Button disabled={busy || config?.brokers_available === false}>Save encrypted account</Button></div>
        </form>
        <p className="mt-3 text-xs text-ink2">Consumer key is encrypted by the backend before database storage. TOTP and MPIN are sent only for the login request and are not persisted.</p>
      </Card>
      {activeId !== null && <Card title="Daily authentication">
        <p className="mb-3 text-sm text-ink2">Complete TOTP first. Then submit your six-digit Kotak Neo MPIN. Never send either value in chat or save it in browser storage.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="6-digit authenticator TOTP"><Input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={totp} onChange={(e) => setTotp(e.target.value.replace(/\\D/g, "").slice(0, 6))} placeholder="Current TOTP" /></Field>
          <div className="flex items-end"><Button disabled={busy || totp.length !== 6} onClick={() => authenticate("totp")}>Verify TOTP</Button></div>
          <Field label="6-digit MPIN"><Input type="password" inputMode="numeric" autoComplete="off" maxLength={6} value={mpin} onChange={(e) => setMpin(e.target.value.replace(/\\D/g, "").slice(0, 6))} placeholder="Trading MPIN" /></Field>
          <div className="flex items-end"><Button disabled={busy || mpin.length !== 6} onClick={() => authenticate("mpin")}>Validate MPIN</Button></div>
        </div>
      </Card>}
      <Card title="Market quotes · NSE / BSE / F&O / MCX">
        <p className="mb-3 text-sm text-ink2">Search the broker scrip master, verify its instrument token, then request a read-only quote. Up to 50 instruments per request.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Exchange segment"><select className="w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm" value={exchangeSegment} onChange={(e) => setExchangeSegment(e.target.value)}><option value="nse_cm">NSE Cash</option><option value="bse_cm">BSE Cash</option><option value="nse_fo">NSE F&O</option><option value="bse_fo">BSE F&O</option><option value="mcx_fo">MCX F&O</option><option value="nse_com">NSE Commodity</option></select></Field>
          <Field label="Trading symbol"><Input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="RELIANCE" maxLength={40} /></Field>
          <div className="flex items-end"><Button disabled={busy || !activeId || !symbol.trim()} onClick={searchScrip}>Search scrip</Button></div>
        </div>
        {scripResult !== null && <div className="mt-3 rounded-lg border border-line p-3"><p className="mb-2 text-sm font-semibold">Scrip search result</p><pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all text-xs text-ink2">{JSON.stringify(scripResult, null, 2)}</pre></div>}
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Verified instrument token"><Input value={instrumentToken} onChange={(e) => setInstrumentToken(e.target.value.replace(/\\D/g, ""))} placeholder="Enter token from search result" maxLength={24} /></Field>
          <div className="flex items-end"><Button disabled={busy || !activeId || !instrumentToken.trim()} onClick={fetchQuote}>Fetch live quote</Button></div>
        </div>
        {quoteResult !== null && <div className="mt-3 rounded-lg border border-line p-3"><p className="mb-2 text-sm font-semibold">Quote response</p><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs text-ink2">{JSON.stringify(quoteResult, null, 2)}</pre></div>}
      </Card>
      <Card title="Read-only account data">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-ink2">Fetch funds, holdings, positions, order book and trade book from Kotak Neo.</p>
          <Button disabled={busy || !activeId || !neoAccounts.find((a) => a.id === activeId)?.token_ok} onClick={loadSnapshot}>Refresh account data</Button>
        </div>
        {snapshot && <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {Object.entries(snapshot).map(([key, section]) => <div key={key} className="min-w-0 rounded-lg border border-line p-3">
            <div className="flex items-center justify-between gap-2"><p className="font-semibold capitalize">{key === "funds" ? "Funds & margins" : key}</p><span className={section.ok ? "text-xs text-profit" : "text-xs text-loss"}>{section.ok ? "Loaded" : "Unavailable"}</span></div>
            {section.ok ? <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs text-ink2">{JSON.stringify(section.data, null, 2)}</pre> : <p className="mt-2 text-xs text-loss">{section.error}</p>}
          </div>)}
        </div>}
        {!snapshot && <p className="mt-3 text-xs text-ink2">No account data fetched in this session yet.</p>}
        <p className="mt-4 text-sm font-semibold text-loss">Read-only mode: live order placement, modification and cancellation remain blocked.</p>
      </Card>
    </div>
  );
}

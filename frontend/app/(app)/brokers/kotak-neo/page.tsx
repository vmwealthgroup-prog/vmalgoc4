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
      <Card title="Trading and data status">
        <div className="grid gap-3 sm:grid-cols-3">
          {["Funds & margins", "Positions & holdings", "Order & trade book", "Market quotes", "Session health", "API activity log"].map((item) => <div key={item} className="rounded-lg border border-line p-3"><p className="text-sm font-medium">{item}</p><p className="mt-1 text-xs text-ink2">Next integration stage</p></div>)}
        </div>
        <p className="mt-4 text-sm font-semibold text-loss">Live order placement is blocked server-side. This stage only establishes the authenticated session.</p>
      </Card>
    </div>
  );
}

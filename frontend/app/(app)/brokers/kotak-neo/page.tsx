"use client";

import { useState } from "react";
import { Card, Notice, Button, Field, Input } from "@/components/ui";

export default function KotakNeoPage() {
  const [showSetup, setShowSetup] = useState(false);
  const [checked, setChecked] = useState(false);

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gold">Broker integration</p>
          <h1 className="mt-1 text-2xl font-bold">Kotak Neo API</h1>
          <p className="mt-1 text-sm text-ink2">Dedicated connection workspace for your Kotak Neo trading account.</p>
        </div>
        <span className="rounded-full border border-gold/50 bg-gold/10 px-3 py-1 text-xs font-semibold text-ink">PAPER MODE · LIVE DISABLED</span>
      </div>

      <Notice kind="warn">
        This page is the first UI stage. API credentials are not submitted or stored here yet. Backend authentication and encrypted session storage must be completed before a connection can be established.
      </Notice>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card title="Connection">
          <p className="text-lg font-semibold">Not connected</p>
          <p className="mt-1 text-xs text-ink2">Authentication not configured</p>
        </Card>
        <Card title="Trading mode">
          <p className="text-lg font-semibold">Paper only</p>
          <p className="mt-1 text-xs text-ink2">Real orders are not available</p>
        </Card>
        <Card title="Broker">
          <p className="text-lg font-semibold">Kotak Neo</p>
          <p className="mt-1 text-xs text-ink2">Official Neo Trade API</p>
        </Card>
      </div>

      <Card title="Before you connect">
        <ol className="grid list-decimal gap-3 pl-5 text-sm">
          <li>In Kotak Neo, open <b>More → Trade API → API Dashboard</b> and create an application. Keep its access token private.</li>
          <li>Complete <b>TOTP Registration</b> from the API Dashboard using an authenticator app.</li>
          <li>Find your <b>UCC / Client Code</b> in your Kotak Neo profile.</li>
          <li>Keep your registered mobile number and 6-digit MPIN ready. Never share these values in chat or screenshots.</li>
        </ol>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={() => setShowSetup((v) => !v)} variant="ghost">{showSetup ? "Hide authentication flow" : "Show authentication flow"}</Button>
          <a className="rounded-lg border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-paper" href="https://github.com/Kotak-Neo/kotak-neo-python" target="_blank" rel="noreferrer">Official Python SDK</a>
          <a className="rounded-lg border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-paper" href="https://github.com/Kotak-Neo/Kotak-Neo/blob/main/docs/authentication.md" target="_blank" rel="noreferrer">Authentication guide</a>
        </div>
        {showSetup && (
          <div className="mt-4 rounded-lg border border-line bg-paper p-4 text-sm">
            <p className="font-semibold">Two-step login sequence</p>
            <ol className="mt-2 grid list-decimal gap-2 pl-5 text-ink2">
              <li>TOTP login validates mobile number, UCC and the current six-digit TOTP; the API returns a temporary View token and session ID.</li>
              <li>MPIN validation upgrades the session and returns the Trade token, session ID and base URL.</li>
              <li>VM Algo will encrypt the session data at rest and use it only from the backend.</li>
            </ol>
          </div>
        )}
      </Card>

      <Card title="Connection workspace">
        <p className="text-sm text-ink2">The secure credential form will be enabled after the backend authentication endpoints, encrypted session persistence and session-expiry handling are added.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Consumer / API access token">
            <Input type="password" disabled placeholder="Enabled in backend integration stage" autoComplete="off" />
          </Field>
          <Field label="Registered mobile number">
            <Input disabled placeholder="+91XXXXXXXXXX" autoComplete="off" />
          </Field>
          <Field label="UCC / Client Code">
            <Input disabled placeholder="Configured securely in next stage" autoComplete="off" />
          </Field>
          <Field label="TOTP and MPIN">
            <Input disabled placeholder="Entered only during secure login" autoComplete="off" />
          </Field>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button disabled>Connect Kotak Neo (backend pending)</Button>
          <Button variant="ghost" onClick={() => setChecked(true)}>Review security checklist</Button>
        </div>
        {checked && <Notice kind="ok">Security checklist: credentials must be sent only over HTTPS, encrypted before database storage, excluded from logs, and never returned to the browser.</Notice>}
      </Card>

      <Card title="Planned account data">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {["Funds & margins", "Positions & holdings", "Order book & trade book", "Live quotes", "Session health", "API activity log"].map((item) => (
            <div key={item} className="rounded-lg border border-line p-3">
              <p className="text-sm font-medium">{item}</p>
              <p className="mt-1 text-xs text-ink2">Available after authenticated API connection</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

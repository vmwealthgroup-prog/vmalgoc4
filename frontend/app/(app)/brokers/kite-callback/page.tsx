"use client";
import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useApi } from "@/lib/api";
import { Card, Notice } from "@/components/ui";

function Callback() {
  const sp = useSearchParams(); const { ready, call } = useApi(); const done = useRef(false);
  const [state, setState] = useState<{ k: "info" | "ok" | "error"; t: string }>({ k: "info", t: "Completing your Zerodha login…" });
  useEffect(() => {
    const token = sp.get("request_token"); const account = sp.get("account");
    if (!ready || done.current) return;
    if (sp.get("status") === "error" || !token || !account) { done.current = true; setState({ k: "error", t: "Zerodha did not return a login. Go back to Brokers and try Daily login again." }); return; }
    done.current = true;
    call(`/api/brokers/accounts/${encodeURIComponent(account)}/kite/session`, { method: "POST", body: JSON.stringify({ request_token: token }) })
      .then(() => setState({ k: "ok", t: "Zerodha login complete for today. You can close this tab or go back to Brokers." }))
      .catch((e) => setState({ k: "error", t: (e as Error).message }));
  }, [ready, sp, call]);
  return <Card title="Zerodha daily login"><Notice kind={state.k}>{state.t}</Notice><p className="mt-4"><Link className="font-semibold underline" href="/brokers">Back to Brokers</Link></p></Card>;
}
export default function KiteCallback() { return <Suspense fallback={<p className="text-ink2">Loading…</p>}><Callback /></Suspense>; }

"use client";
import { useState } from "react";
import { useApi, useLoad } from "@/lib/api";
import { Button, Card, Notice } from "./ui";

export default function Notifications({ isAdmin }: { isAdmin: boolean }) {
  const { call } = useApi(); const sys = useLoad<any>("/api/system/status");
  const [res, setRes] = useState<{ k: "ok" | "error" | "info"; t: string } | null>(null);
  const channels: string[] = sys.data?.notifications ?? [];
  async function test() {
    setRes(null);
    try {
      const r = await call("/api/system/notify-test", { method: "POST" });
      if (!r.channels.length) return setRes({ k: "info", t: r.message });
      const bad = Object.entries(r.results).filter(([, v]) => v !== "ok");
      setRes(bad.length ? { k: "error", t: `Failed: ${bad.map(([k, v]) => `${k} (${v})`).join(", ")}` } : { k: "ok", t: `Sent to ${r.channels.join(", ")}` });
    } catch (e) { setRes({ k: "error", t: (e as Error).message }); }
  }
  return (
    <Card title="Alerts">
      <p className="text-sm text-ink2">Get a message on every fill, blocked or failed order, circuit-breaker trip, kill-switch trigger and expired broker login. Channels are set on the server (Telegram, Discord or a webhook URL in the environment), so no secrets are stored in the app.</p>
      <p className="mt-2 text-sm">Active channels: <b>{channels.length ? channels.join(", ") : "none configured"}</b></p>
      {isAdmin && <div className="mt-3"><Button variant="ghost" onClick={test}>Send test alert</Button></div>}
      {res && <div className="mt-3"><Notice kind={res.k}>{res.t}</Notice></div>}
    </Card>
  );
}

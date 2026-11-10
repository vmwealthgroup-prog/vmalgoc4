"use client";
import Link from "next/link";
import { useLoad, useApi } from "@/lib/api";
import type { Strategy } from "@/lib/types";
import { Button, Card, Notice, Table } from "@/components/ui";

const tone = (m: string) => (m === "live" ? "bg-loss text-white" : m === "paper" ? "bg-gold text-ink" : "bg-line text-ink2");

export default function Strategies() {
  const { data, error, reload } = useLoad<Strategy[]>("/api/strategies");
  const { call } = useApi();
  async function del(id: number) { if (confirm("Delete this strategy?")) { await call(`/api/strategies/${id}`, { method: "DELETE" }); reload(); } }
  return (
    <div className="grid gap-6">
      <div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Strategies</h1><Link href="/strategies/new" className="rounded-lg bg-gold px-4 py-2 text-sm font-semibold">New strategy</Link></div>
      {error && <Notice kind="error">{error}</Notice>}
      <Card>
        {!data ? <p className="text-ink2">Loading…</p> : data.length === 0 ? <p className="text-ink2">No strategies yet. Build one from a template.</p> : (
          <Table head={["Name", "Market", "Interval", "Mode", "Target", ""]}>
            {data.map((s) => (
              <tr key={s.id}>
                <td><Link className="font-medium underline" href={`/strategies/${s.id}`}>{s.name}</Link></td>
                <td>{s.spec.symbol} <span className="text-ink2">{s.spec.exchange}</span></td><td>{s.spec.interval}</td>
                <td><span className={`rounded-full px-2 py-0.5 text-xs font-semibold uppercase ${tone(s.mode)}`}>{s.mode}</span></td>
                <td>{s.mode === "off" ? "-" : s.last_target}</td>
                <td className="text-right"><Button variant="ghost" onClick={() => del(s.id)}>Delete</Button></td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

"use client";
import Link from "next/link";
import { useLoad, useApi } from "@/lib/api";
import type { Strategy, Spec } from "@/lib/types";
import { Button, Card, Notice, Table } from "@/components/ui";

type Template = {
  key: string; name: string; category?: string; origin?: string;
  description?: string; research_note?: string; spec: Partial<Spec>;
};
const templateTone: Record<string, string> = {
  "Swing momentum": "border-gold/50", "Breakout": "border-blue-500/40",
  "Intraday": "border-violet-500/40", "Quant research": "border-cyan-500/40",
  "Trend following": "border-emerald-500/40", "Trend": "border-line",
  "Mean reversion": "border-amber-500/40",
};
const tone = (m: string) => (m === "live" ? "bg-loss text-white" : m === "paper" ? "bg-gold text-ink" : "bg-line text-ink2");

export default function Strategies() {
  const { data, error, reload } = useLoad<Strategy[]>("/api/strategies");
  const templates = useLoad<Template[]>("/api/strategies/templates");
  const { call } = useApi();
  async function del(id: number) { if (confirm("Delete this strategy?")) { await call(`/api/strategies/${id}`, { method: "DELETE" }); reload(); } }
  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-2xl font-bold">Strategies</h1><p className="mt-1 text-sm text-ink2">Research templates, build rules, backtest and deploy in paper mode.</p></div>
        <Link href="/strategies/new" className="rounded-lg bg-gold px-4 py-2 text-sm font-semibold">New strategy</Link>
      </div>

      <section className="grid gap-3">
        <div className="flex flex-wrap items-end justify-between gap-2"><div><h2 className="text-lg font-bold">Champion-inspired strategy library</h2><p className="text-sm text-ink2">Research interpretations of published trading principles—not proprietary systems or performance claims.</p></div><span className="rounded-full border border-line px-3 py-1 text-xs text-ink2">{templates.data?.length ?? "…"} templates</span></div>
        {templates.error && <Notice kind="error">Could not load strategy templates: {templates.error}</Notice>}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(templates.data ?? []).map((t) => (
            <Card key={t.key}>
              <div className={`mb-3 inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${templateTone[t.category ?? ""] ?? "border-line"}`}>{t.category ?? "Research"}</div>
              <h3 className="text-base font-bold">{t.name}</h3>
              <p className="mt-1 text-xs text-ink2">{t.origin ?? "VM Algo research"}</p>
              <p className="mt-3 min-h-12 text-sm">{t.description ?? "Rule-based strategy template for research and backtesting."}</p>
              {t.research_note && <p className="mt-3 rounded-lg bg-paper p-3 text-xs text-ink2">{t.research_note}</p>}
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Link href={`/strategies/new?template=${encodeURIComponent(t.key)}`} className="rounded-lg bg-gold px-3 py-2 text-sm font-semibold">Use template</Link>
                <span className="text-xs text-ink2">{t.spec.interval ?? "5m"} · {t.spec.exchange ?? "NSE"} · {t.spec.side ?? "long"}</span>
              </div>
            </Card>
          ))}
          {!templates.data && !templates.error && <Card><p className="text-sm text-ink2">Loading strategy research library…</p></Card>}
        </div>
      </section>

      {error && <Notice kind="error">{error}</Notice>}
      <Card title="My strategies">
        {!data ? <p className="text-ink2">Loading…</p> : data.length === 0 ? <p className="text-ink2">No saved strategies yet. Choose a research template above or build one from scratch.</p> : (
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
      <p className="text-xs text-ink2">All templates start as editable research configurations. Backtest with realistic costs and out-of-sample data. Paper trading only until risk and operational validation is complete.</p>
    </div>
  );
}

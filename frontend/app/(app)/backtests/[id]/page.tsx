"use client";
import { useParams } from "next/navigation";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useLoad } from "@/lib/api";
import { fmt } from "@/lib/types";
import { Card, Notice, Pnl, Stat, Table } from "@/components/ui";

export default function BacktestDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: b, error } = useLoad<any>(`/api/backtests/${id}`);
  if (error) return <Notice kind="error">{error}</Notice>;
  if (!b) return <p className="text-ink2">Loading…</p>;
  const m = b.metrics; const c0 = b.equity[0]?.close || 1;
  const series = b.equity.map((p: any) => ({ t: p.t.slice(0, 16).replace("T", " "), Strategy: +((p.equity - 1) * 100).toFixed(2), "Buy & hold": +((p.close / c0 - 1) * 100).toFixed(2) }));
  return (
    <div className="grid gap-6">
      <div><h1 className="text-2xl font-bold">{b.name}</h1><p className="text-sm text-ink2">{b.params.spec.symbol} {b.params.spec.exchange} · {b.params.spec.interval} · {m.bars} candles · data: <b>{m.data_source}</b> · cost {m.cost_bps} bps</p></div>
      {m.data_source === "demo" && <Notice kind="warn">This ran on synthetic demo data, which is random. The result says nothing about real markets.</Notice>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Strategy return" value={<Pnl v={m.total_return_pct} />} tone={m.total_return_pct >= 0 ? "gain" : "loss"} />
        <Stat label="Buy & hold" value={`${fmt(m.buy_hold_pct)}%`} />
        <Stat label="Max drawdown" value={`${fmt(m.max_drawdown_pct)}%`} tone="loss" />
        <Stat label="Sharpe" value={fmt(m.sharpe)} />
        <Stat label="Trades" value={m.trades} /><Stat label="Win rate" value={`${fmt(m.win_rate_pct, 1)}%`} />
        <Stat label="Profit factor" value={m.profit_factor ?? "-"} /><Stat label="Time in market" value={`${fmt(m.in_market_pct, 0)}%`} />
      </div>
      <Card title="Return over time (%)">
        <div className="h-80" role="img" aria-label="Strategy return compared with buy and hold">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
              <CartesianGrid stroke="#dde3ec" /><XAxis dataKey="t" minTickGap={60} tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} unit="%" width={55} />
              <Tooltip /><Legend />
              <Line type="monotone" dataKey="Strategy" stroke="#f2a900" dot={false} strokeWidth={2} /><Line type="monotone" dataKey="Buy & hold" stroke="#10223b" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title={`Trades (last ${b.trades.length})`}>
        {b.trades.length === 0 ? <p className="text-ink2">No trades in this period.</p> : (
          <Table head={["Side", "Entered", "Entry", "Exited", "Exit", "P&L %"]}>
            {[...b.trades].reverse().map((t: any, i: number) => <tr key={i}><td>{t.side}</td><td>{t.entry_time.slice(0, 16)}</td><td>{fmt(t.entry)}</td><td>{t.exit_time.slice(0, 16)}</td><td>{fmt(t.exit)}</td><td><Pnl v={t.pnl_pct} /></td></tr>)}
          </Table>
        )}
      </Card>
      <p className="text-xs text-ink2">Signals are decided at a candle's close and traded on the next candle. Past results do not predict future results.</p>
    </div>
  );
}

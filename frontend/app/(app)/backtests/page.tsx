"use client";
import Link from "next/link";
import { useLoad } from "@/lib/api";
import { fmt } from "@/lib/types";
import { Card, Notice, Pnl, Table } from "@/components/ui";

export default function Backtests() {
  const { data, error } = useLoad<any[]>("/api/backtests");
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-bold">Backtests</h1>
      {error && <Notice kind="error">{error}</Notice>}
      <Card>
        {!data ? <p className="text-ink2">Loading…</p> : data.length === 0 ? <p className="text-ink2">None yet. Open a strategy and press Run backtest.</p> : (
          <Table head={["Strategy", "Return %", "Buy & hold %", "Max DD %", "Sharpe", "Trades", "Data", "When"]}>
            {data.map((b) => (
              <tr key={b.id}>
                <td><Link className="font-medium underline" href={`/backtests/${b.id}`}>{b.name}</Link></td>
                <td><Pnl v={b.metrics.total_return_pct} /></td><td>{fmt(b.metrics.buy_hold_pct)}</td><td>{fmt(b.metrics.max_drawdown_pct)}</td>
                <td>{fmt(b.metrics.sharpe)}</td><td>{b.metrics.trades}</td><td>{b.metrics.data_source}</td><td>{new Date(b.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

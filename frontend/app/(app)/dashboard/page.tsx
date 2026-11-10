"use client";
import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";
import { useLoad } from "@/lib/api";
import { useStream } from "@/lib/stream";
import { fmt, type Order } from "@/lib/types";
import { Card, Input, Notice, Pnl, Stat, Table } from "@/components/ui";

const DEFAULT = "BTC/USD, NIFTY, BANKNIFTY, RELIANCE";

export default function Dashboard() {
  const [text, setText] = useState(DEFAULT); const [symbols, setSymbols] = useState(DEFAULT.split(", "));
  useEffect(() => { const s = localStorage.getItem("watchlist"); if (s) { setText(s); setSymbols(s.split(/[,\s]+/).filter(Boolean)); } }, []);
  const { ticks, events, status } = useStream(symbols);
  const { data, error } = useLoad<any>("/api/dashboard", 8000);
  const sys = useLoad<any>("/api/system/status", 10000);
  const [sel, setSel] = useState<string>(symbols[0]);
  const apply = () => { const s = text.split(/[,\s]+/).filter(Boolean).map((x) => x.toUpperCase()).slice(0, 20); setSymbols(s); setSel(s[0]); localStorage.setItem("watchlist", s.join(", ")); };
  const live = status === "live";
  const hist = (ticks[sel]?.hist ?? []).map((v, i) => ({ i, v }));
  const funds = data?.paper_funds ?? {};

  return (
    <div className="grid gap-6">
      <div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Dashboard</h1>
        <span role="status" className={`rounded-full px-3 py-1 text-xs font-semibold ${live ? "bg-gain/10 text-gain" : "bg-gold/20 text-ink"}`}>● {live ? "Live feed" : status}</span></div>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {symbols.map((s) => { const t = ticks[s]; const up = t?.prev === undefined ? undefined : t.ltp >= t.prev;
          return (
            <button key={s} onClick={() => setSel(s)} aria-pressed={sel === s} className={`rounded-lg border bg-white p-4 text-left ${sel === s ? "border-gold ring-2 ring-gold/40" : "border-line"}`}>
              <div className="flex items-center justify-between text-xs font-medium text-ink2"><span>{s}</span>{t?.src && <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${t.src === "demo" ? "bg-gold/20 text-ink" : "bg-gain/10 text-gain"}`}>{t.src === "demo" ? "DEMO" : "LIVE"}</span>}</div>
              <div className={`text-xl font-semibold tabular-nums ${up === undefined ? "" : up ? "text-gain" : "text-loss"}`}>{t ? fmt(t.ltp) : "…"}</div>
            </button>); })}
      </div>
      <Card title={`${sel} live`} right={<div className="flex items-center gap-2"><Input aria-label="Watchlist" className="w-72" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && apply()} /><button className="text-sm underline" onClick={apply}>Apply</button></div>}>
        <div className="h-48" role="img" aria-label={`Live price of ${sel}`}>
          {hist.length < 2 ? <p className="text-ink2">Waiting for ticks…</p> : (
            <ResponsiveContainer width="100%" height="100%"><LineChart data={hist}><YAxis domain={["auto", "auto"]} hide /><Line type="monotone" dataKey="v" stroke="#f2a900" strokeWidth={2} dot={false} isAnimationActive={false} /></LineChart></ResponsiveContainer>
          )}
        </div>
        <p className="mt-2 text-xs text-ink2">{ticks[sel]?.src === "coinbase" ? `Real trades streamed from Coinbase's public market-data feed.${ticks[sel]?.bid ? ` Best bid ${fmt(ticks[sel]!.bid!)} / ask ${fmt(ticks[sel]!.ask!)}.` : ""}` : ticks[sel]?.src === "demo" ? "These prices are SYNTHETIC demo data. Set CRYPTO_FEED=coinbase on the server for real BTC ticks." : "Waiting for ticks…"}</p>
      </Card>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Strategies live" value={data?.strategies.live ?? "-"} tone={data?.strategies.live ? "loss" : undefined} />
        <Stat label="Strategies paper" value={data?.strategies.paper ?? "-"} />
        <Stat label="Paper equity" value={funds.equity ? fmt(funds.equity, 0) : "-"} />
        <Stat label="Paper P&L" value={funds.unrealized_pnl !== undefined ? <Pnl v={funds.unrealized_pnl} /> : "-"} />
      </div>
      {sys.data && (
        <Card title="System health" right={<span role="status" className={`rounded-full px-3 py-1 text-xs font-semibold ${sys.data.healthy ? "bg-gain/10 text-gain" : "bg-loss/10 text-loss"}`}>{sys.data.healthy ? "All systems running" : "Attention needed"}</span>}>
          {sys.data.problems.length > 0 && <div className="mb-3"><Notice kind="error">{sys.data.problems.join(". ")}. Real orders only run while the worker is alive.</Notice></div>}
          {sys.data.kill_switch && <div className="mb-3"><Notice kind="warn">Kill switch is ON: no new positions will open. Closing orders still work. Reset it in Settings after reviewing.</Notice></div>}
          <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-5">
            <div><div className="text-xs uppercase text-ink2">Indian market</div><div className="font-semibold">{sys.data.markets.NSE ? "Open" : "Closed"}</div></div>
            <div><div className="text-xs uppercase text-ink2">Price feed</div><div className="font-semibold">{sys.data.feed_age_s == null ? "no signal" : `${sys.data.feed_age_s}s ago`}</div></div>
            <div><div className="text-xs uppercase text-ink2">Automation</div><div className="font-semibold">{sys.data.runner_age_s == null ? "no signal" : `${sys.data.runner_age_s}s ago`}</div></div>
            <div><div className="text-xs uppercase text-ink2">Alerts</div><div className="font-semibold">{sys.data.notifications.length ? sys.data.notifications.join(", ") : "none set up"}</div></div>
            <div><div className="text-xs uppercase text-ink2">Crypto feed</div><div className="font-semibold">{sys.data.crypto_feed !== "coinbase" ? "demo (synthetic)" : sys.data.feed ? (sys.data.feed.connected ? `live, ${sys.data.feed.trades} trades` : `down: ${sys.data.feed.err || "reconnecting"}`) : "no signal"}</div></div>
          </div>
        </Card>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Live events">
          {events.length === 0 ? <p className="text-sm text-ink2">Order and signal events from your strategies appear here instantly.</p> : (
            <ul className="grid gap-2 text-sm">{events.map((e, i) => <li key={i} className="rounded-lg border border-line p-2">{e.type === "order" ? <><b>{e.side} {e.qty}</b> {e.symbol} · {e.strategy} · <span className={e.status === "blocked" || e.status === "failed" ? "text-loss" : "text-gain"}>{e.status}</span>{e.status !== "filled" && e.status !== "sent" && <span className="text-ink2"> ({e.message})</span>}</> : <span className="text-loss">{e.strategy}: {e.message}</span>}</li>)}</ul>
          )}
        </Card>
        <Card title="Recent orders">
          {!data ? <p className="text-ink2">Loading…</p> : data.recent_orders.length === 0 ? <p className="text-sm text-ink2">No orders yet.</p> : (
            <Table head={["Time", "Side", "Symbol", "Qty", "Status"]}>
              {data.recent_orders.map((o: Order) => <tr key={o.id}><td>{new Date(o.created_at).toLocaleTimeString()}</td><td>{o.side}</td><td>{o.symbol}</td><td>{o.qty}</td><td title={o.message}>{o.status}{o.mode === "live" && " (LIVE)"}</td></tr>)}
            </Table>
          )}
        </Card>
      </div>
    </div>
  );
}

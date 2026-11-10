"use client";
import { useEffect, useState } from "react";
import { wsBase } from "./env";
import { useApi } from "./api";

export type Tick = { ltp: number; prev?: number; ts: number; hist: number[]; src?: string; bid?: number | null; ask?: number | null };
export type LiveEvent = { type: string; [k: string]: any };

/** Live ticks for `symbols` plus your order/signal events, over the API WebSocket. Reconnects automatically.
 *  Open mode connects without a token; login mode sends the session token. */
export function useStream(symbols: string[]) {
  const { ready, token, open } = useApi();
  const [ticks, setTicks] = useState<Record<string, Tick>>({});
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [status, setStatus] = useState<"connecting" | "live" | "reconnecting">("connecting");
  const key = symbols.join(",");

  useEffect(() => {
    if (!ready) return;
    let ws: WebSocket | undefined; let stop = false; let retry: ReturnType<typeof setTimeout>;
    const base = wsBase();
    const q = `${!open && token ? `token=${encodeURIComponent(token)}&` : ""}symbols=${encodeURIComponent(key)}`;
    const connect = () => {
      ws = new WebSocket(`${base}/ws/stream?${q}`);
      ws.onopen = () => setStatus("live");
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.type === "tick") setTicks((t) => ({ ...t, [m.symbol]: { ltp: m.ltp, prev: t[m.symbol]?.ltp, ts: m.ts, src: m.src, bid: m.bid ?? t[m.symbol]?.bid, ask: m.ask ?? t[m.symbol]?.ask, hist: [...(t[m.symbol]?.hist ?? []).slice(-59), m.ltp] } }));
        else setEvents((ev) => [m, ...ev].slice(0, 20));
      };
      ws.onclose = () => { setStatus("reconnecting"); if (!stop) retry = setTimeout(connect, 3000); };
    };
    connect();
    return () => { stop = true; clearTimeout(retry); ws?.close(); };
  }, [ready, open, token, key]);

  return { ticks, events, status };
}

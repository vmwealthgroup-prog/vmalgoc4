"use client";

import { useEffect, useState } from "react";

type ApiCall = <T = any>(path: string, init?: RequestInit) => Promise<T>;

type Props = {
  activeId: number | null;
  connected: boolean;
  exchangeSegment: string;
  instrumentToken: string;
  call: ApiCall;
};

export default function KotakNeoQuoteMonitor({
  activeId,
  connected,
  exchangeSegment,
  instrumentToken,
  call,
}: Props) {
  const [quote, setQuote] = useState<unknown>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = instrumentToken.trim();
    if (!activeId || !connected || !/^\\d+$/.test(token)) {
      setQuote(null);
      setUpdatedAt(null);
      setError("");
      return;
    }

    let stopped = false;
    let inFlight = false;

    const refresh = async () => {
      if (inFlight || stopped) return;
      inFlight = true;
      try {
        const result = await call<unknown>(
          `/api/brokers/accounts/${activeId}/kotak-neo/quotes`,
          {
            method: "POST",
            body: JSON.stringify({
              instruments: [{ instrument_token: token, exchange_segment: exchangeSegment }],
              quote_type: "ltp",
            }),
          },
        );
        if (!stopped) {
          setQuote(result);
          setUpdatedAt(new Date().toLocaleTimeString());
          setError("");
        }
      } catch (e) {
        if (!stopped) setError((e as Error).message || "Quote refresh failed.");
      } finally {
        inFlight = false;
      }
    };

    void refresh();
    const timer = window.setInterval(refresh, 10_000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [activeId, connected, exchangeSegment, instrumentToken, call]);

  if (!activeId) return null;

  return (
    <Card title="Kotak Neo auto-refresh monitor">
      {!connected ? (
        <p className="text-sm text-ink2">Complete today's TOTP and MPIN authentication to enable quote refresh.</p>
      ) : !/^\\d+$/.test(instrumentToken.trim()) ? (
        <p className="text-sm text-ink2">Enter a verified numeric instrument token above to start monitoring.</p>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-ink2">Read-only LTP polling every 10 seconds. This is REST polling, not a broker WebSocket stream.</p>
            <span className="rounded-full border border-line px-2 py-1 text-xs text-ink2">10s refresh</span>
          </div>
          {updatedAt && <p className="mb-2 text-xs text-ink2">Last successful update: {updatedAt}</p>}
          {error && <p className="mb-2 text-sm text-loss">{error}</p>}
          {quote !== null && (
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg border border-line p-3 text-xs text-ink2">
              {JSON.stringify(quote, null, 2)}
            </pre>
          )}
        </>
      )}
    </Card>
  );
}

import { Card } from "@/components/ui";

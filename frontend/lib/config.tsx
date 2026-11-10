"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { API } from "./env";

export type AppConfig = {
  mode: "open" | "login"; auth_required: boolean; env: string; allow_registration: boolean;
  brokers_available: boolean; live_available: boolean; live_trading_enabled_on_server: boolean;
};
type Ctx = { config: AppConfig | null; error: string | null; reload: () => Promise<void> };
const C = createContext<Ctx>({ config: null, error: null, reload: async () => {} });

/** Reads the public /api/app/config once: it tells the app whether login is on (login mode) or off (open mode). */
export function ConfigProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/app/config`, { cache: "no-store" });
      if (!r.ok) throw new Error(r.status === 404 ? "the API was not found" : `the API answered ${r.status}`);
      setConfig(await r.json()); setError(null);
    } catch (e) { setError((e as Error).message === "Failed to fetch" ? "the API is not running" : (e as Error).message || "cannot reach the API"); }
  }, []);
  useEffect(() => { reload(); }, [reload]);
  return <C.Provider value={{ config, error, reload }}>{children}</C.Provider>;
}
export const useConfig = () => useContext(C);

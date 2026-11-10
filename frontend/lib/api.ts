"use client";
import { signOut, useSession } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";
import { API } from "./env";
import { useConfig } from "./config";

export { API };

export async function api<T = any>(token: string | undefined, path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers || {}) },
  });
  if (res.status === 401) { signOut({ callbackUrl: "/login" }); throw new Error("Session expired, please sign in again"); }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data));
  return data as T;
}

/** call(path, init). Open mode: no token is needed. Login mode: the session token is attached.
 *  `ready` is false until the access mode is known (and, in login mode, until the session has loaded). */
export function useApi() {
  const { data, status } = useSession();
  const { config } = useConfig();
  const open = config?.mode === "open";
  const token = open ? undefined : data?.accessToken;
  const ready = !!config && (open || (status !== "loading" && !!data?.accessToken));
  const call = useCallback(<T = any>(path: string, init?: RequestInit) => api<T>(token, path, init), [token]);
  return { token, call, ready, open, config, role: data?.role, user: data?.user };
}

/** GET on mount (and whenever the path changes), with optional polling. */
export function useLoad<T = any>(path: string | null, pollMs = 0) {
  const { ready, call } = useApi();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(() => {
    if (!ready || !path) return Promise.resolve();
    return call<T>(path).then((d) => { setData(d); setError(null); }).catch((e) => setError(e.message));
  }, [ready, path, call]);
  useEffect(() => { reload(); if (!pollMs) return; const id = setInterval(reload, pollMs); return () => clearInterval(id); }, [reload, pollMs]);
  return { data, error, reload, ready };
}

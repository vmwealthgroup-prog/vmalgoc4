// API base URL for the browser. Empty (the default) = same origin: Next forwards /api/* to the API (see next.config.js), or Caddy does in Docker.
export const API = process.env.NEXT_PUBLIC_API_URL ?? "";

/** WebSocket base URL. Next cannot proxy WebSockets, so in development the socket connects straight to the API on port 8000 of the same host.
 *  In production the reverse proxy serves /ws on the same origin. Override with NEXT_PUBLIC_WS_URL. */
export function wsBase(): string {
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
  if (API) return API.replace(/^http/, "ws");
  if (typeof window === "undefined") return "";
  if (process.env.NODE_ENV !== "production") return `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8000`;
  return window.location.origin.replace(/^http/, "ws");
}

// API base URL for the browser.
// Empty means use same-origin Next.js rewrites or the hosting reverse proxy.
export const API = process.env.NEXT_PUBLIC_API_URL ?? "";

/** WebSocket base URL. */
export function wsBase(): string {
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
  if (API) return API.replace(/^http/, "ws");
  if (typeof window === "undefined") return "";
  if (process.env.NODE_ENV !== "production") {
    return `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8000`;
  }
  return window.location.origin.replace(/^http/, "ws");
}

export type Operand = { ind?: string; period?: number; value?: number };
export type Condition = { left: Operand; op: string; right: Operand };
export type Group = { all?: Condition[]; any?: Condition[] };
export type Spec = {
  symbol: string; exchange: string; interval: string; side?: "long" | "short"; entry: Group; exit?: Group;
  risk?: { qty?: number; stop_pct?: number; take_pct?: number; risk_pct?: number; equity?: number; max_qty?: number; stop_atr?: number; square_off?: string; capital?: number; breaker_trades?: number; breaker_loss_pct?: number };
};
export type Strategy = { id: number; name: string; spec: Spec; mode: "off" | "paper" | "live"; account_id: number | null; last_target: number; last_run: string | null };
export type Account = { id: number; kind: "paper" | "openalgo" | "kite" | "ccxt"; label: string; broker_name: string; host: string; live_enabled: boolean; has_key: boolean; token_ok?: boolean | null; crypto?: { trade: boolean; sandbox: boolean } | null };
export type Order = { id: number; symbol: string; exchange: string; side: string; qty: number; price: number; status: string; mode: string; message: string; created_at: string };
export type Position = { symbol: string; exchange: string; qty: number; avg_price: number; ltp: number; pnl: number };
export const fmt = (n: number | undefined | null, d = 2) => (n == null || Number.isNaN(n) ? "-" : Number(n).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));

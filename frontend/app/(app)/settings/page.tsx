"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { signOut } from "next-auth/react";
import { useApi, useLoad } from "@/lib/api";
import { useConfig } from "@/lib/config";
import Notifications from "@/components/Notifications";
import Webhooks from "@/components/Webhooks";
import { Button, Card, Field, Input, Notice, Table } from "@/components/ui";

type Limits = { max_qty: number; max_order_value: number; max_position_value: number; max_orders_per_day: number; max_daily_loss: number; window_start: string; window_end: string; allow_short: boolean; blocked: string[]; kill_switch: boolean };

function AccessCard({ role }: { role?: string }) {
  const { call, config, open } = useApi(); const { reload } = useConfig(); const router = useRouter();
  const [f, setF] = useState({ email: "", password: "", confirm: "" }); const [off, setOff] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  if (!config) return null;

  async function turnOn(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    if (f.password !== f.confirm) return setErr("The two passwords do not match");
    setBusy(true);
    try { await call("/api/app/auth", { method: "PUT", body: JSON.stringify({ required: true, email: f.email, password: f.password }) }); await reload(); router.push("/login"); }
    catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  }
  async function turnOff(e: React.FormEvent) {
    e.preventDefault(); setErr(""); setBusy(true);
    try { await call("/api/app/auth", { method: "PUT", body: JSON.stringify({ required: false, password: off }) }); await signOut({ redirect: false }); await reload(); router.push("/dashboard"); }
    catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  }

  return (
    <div id="access" className="scroll-mt-6">
      <Card title="Access: login" right={<span className={`rounded-full px-3 py-1 text-xs font-semibold ${open ? "bg-gold/20" : "bg-gain/10 text-gain"}`}>{open ? "Login OFF (open mode)" : "Login ON"}</span>}>
        {open ? (
          <form onSubmit={turnOn} className="grid gap-4">
            <p className="text-sm text-ink2">Right now anyone who can reach this server has full access. Turn login on to protect it. It is <b>required</b> for real-money trading{config.env === "production" ? " and for connecting brokers on this hosted server" : ""}. Your existing strategies and backtests stay with your account.</p>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Your email"><Input type="email" required autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
              <Field label="New password (8+ characters)"><Input type="password" required minLength={8} autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
              <Field label="Repeat password"><Input type="password" required minLength={8} autoComplete="new-password" value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} /></Field>
            </div>
            {err && <Notice kind="error">{err}</Notice>}
            <div><Button disabled={busy}>{busy ? "Turning on…" : "Turn on login"}</Button></div>
          </form>
        ) : role === "admin" ? (
          <form onSubmit={turnOff} className="grid gap-4">
            <Notice kind="warn">Turning login off lets anyone who can reach this server use it, and disables real-money trading{config.env === "production" ? " and broker connections" : ""}. Strategies running in live mode will be blocked.</Notice>
            <Field label="Confirm with your password"><Input type="password" required autoComplete="current-password" value={off} onChange={(e) => setOff(e.target.value)} className="max-w-xs" /></Field>
            {err && <Notice kind="error">{err}</Notice>}
            <div><Button variant="ghost" disabled={busy}>{busy ? "Turning off…" : "Turn off login (open mode)"}</Button></div>
          </form>
        ) : <p className="text-sm text-ink2">Only an admin can change this.</p>}
      </Card>
    </div>
  );
}

export default function Settings() {
  const { call, open } = useApi();
  const me = useLoad<{ id: number; email: string; name: string; role: string }>("/api/me");
  const lim = useLoad<Limits>("/api/risk-limits"); const [l, setL] = useState<Limits | null>(null); const [blocked, setBlocked] = useState("");
  const [msg, setMsg] = useState<{ k: "ok" | "error"; t: string } | null>(null); const [pw, setPw] = useState({ current: "", new: "" }); const [name, setName] = useState("");
  const isAdmin = me.data?.role === "admin"; const users = useLoad<any[]>(isAdmin ? "/api/admin/users" : null);
  useEffect(() => { if (lim.data) { setL(lim.data); setBlocked(lim.data.blocked.join(", ")); } }, [lim.data]);
  useEffect(() => { setName(me.data?.name ?? ""); }, [me.data?.name]);
  const say = (k: "ok" | "error", t: string) => setMsg({ k, t });
  async function saveLimits() { try { await call("/api/risk-limits", { method: "PUT", body: JSON.stringify({ ...l, blocked: blocked.split(/[,\s]+/).filter(Boolean) }) }); say("ok", "Risk limits saved"); } catch (e) { say("error", (e as Error).message); } }
  async function changePw(e: React.FormEvent) { e.preventDefault(); try { await call("/api/me/password", { method: "POST", body: JSON.stringify(pw) }); setPw({ current: "", new: "" }); say("ok", "Password changed"); } catch (x) { say("error", (x as Error).message); } }
  async function saveName() { try { await call("/api/me", { method: "PATCH", body: JSON.stringify({ name }) }); say("ok", "Profile saved"); } catch (x) { say("error", (x as Error).message); } }
  async function patchUser(id: number, body: object) { try { await call(`/api/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }); users.reload(); } catch (x) { say("error", (x as Error).message); } }
  const n = (k: keyof Limits) => ({ type: "number", value: l ? (l[k] as number) : "", onChange: (e: React.ChangeEvent<HTMLInputElement>) => l && setL({ ...l, [k]: Number(e.target.value) }) });
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-bold">Settings</h1>
      {msg && <Notice kind={msg.k}>{msg.t}</Notice>}
      <AccessCard role={me.data?.role} />
      <Notifications isAdmin={isAdmin} />
      <Webhooks />
      {l && (
        <Card title="Risk limits (checked before EVERY order)">
          <div className="mb-4 flex items-center justify-between rounded-lg border border-loss/40 bg-loss/5 p-3">
            <div><div className="font-semibold text-loss">Kill switch</div><div className="text-xs text-ink2">When ON, nothing can open or increase a position. Closing orders always go through, so you can still get out.</div></div>
            <Button variant={l.kill_switch ? "ghost" : "danger"} onClick={() => setL({ ...l, kill_switch: !l.kill_switch })}>{l.kill_switch ? "ON: click to turn off" : "OFF: click to turn on"}</Button>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Max quantity per order"><Input min={1} {...n("max_qty")} /></Field><Field label="Max order value"><Input min={0} {...n("max_order_value")} /></Field>
            <Field label="Max position value"><Input min={0} {...n("max_position_value")} /></Field><Field label="Max orders per day"><Input min={1} {...n("max_orders_per_day")} /></Field>
            <Field label="Max daily loss (stops trading)"><Input min={0} {...n("max_daily_loss")} /></Field>
            <Field label="Trading window (IST)"><div className="flex gap-2"><Input value={l.window_start} onChange={(e) => setL({ ...l, window_start: e.target.value })} aria-label="Window start" /><Input value={l.window_end} onChange={(e) => setL({ ...l, window_end: e.target.value })} aria-label="Window end" /></div></Field>
            <Field label="Blocked symbols"><Input value={blocked} onChange={(e) => setBlocked(e.target.value)} placeholder="e.g. YESBANK, SUZLON" /></Field>
            <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={l.allow_short} onChange={(e) => setL({ ...l, allow_short: e.target.checked })} /> Allow short positions</label>
          </div>
          <div className="mt-4"><Button onClick={saveLimits}>Save limits</Button></div>
        </Card>
      )}
      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Profile"><div className="grid gap-3"><Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field><div><Button variant="ghost" onClick={saveName}>Save</Button></div>{!open && <p className="text-xs text-ink2">{me.data?.email}</p>}</div></Card>
        {!open && (
          <Card title="Change password"><form onSubmit={changePw} className="grid gap-3">
            <Field label="Current password"><Input type="password" required autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></Field>
            <Field label="New password"><Input type="password" required minLength={8} autoComplete="new-password" value={pw.new} onChange={(e) => setPw({ ...pw, new: e.target.value })} /></Field><div><Button>Change</Button></div></form></Card>
        )}
      </div>
      {isAdmin && !open && (
        <Card title="Users (admin)">
          {!users.data ? <p className="text-ink2">Loading…</p> : (
            <Table head={["Email", "Name", "Role", "Status", ""]}>
              {users.data.map((u) => <tr key={u.id}><td>{u.email}</td><td>{u.name}</td><td>{u.role}</td><td>{u.is_active ? "active" : "disabled"}</td>
                <td className="flex justify-end gap-2"><Button variant="ghost" onClick={() => patchUser(u.id, { is_active: !u.is_active })}>{u.is_active ? "Disable" : "Enable"}</Button>
                  <Button variant="ghost" onClick={() => patchUser(u.id, { role: u.role === "admin" ? "user" : "admin" })}>{u.role === "admin" ? "Make user" : "Make admin"}</Button></td></tr>)}
            </Table>
          )}
        </Card>
      )}
    </div>
  );
}

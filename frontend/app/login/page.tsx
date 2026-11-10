"use client";
import Link from "next/link";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useConfig } from "@/lib/config";
import { Button, Card, Field, Input, Notice } from "@/components/ui";

export default function Login() {
  const router = useRouter(); const { config } = useConfig();
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setErr("");
    const f = new FormData(e.currentTarget);
    const r = await signIn("credentials", { email: f.get("email"), password: f.get("password"), redirect: false });
    setBusy(false);
    if (r?.error) setErr("Invalid email or password"); else router.push("/dashboard");
  }
  if (config?.mode === "open") return (
    <main className="mx-auto grid min-h-screen max-w-sm content-center gap-4 px-6">
      <h1 className="text-2xl font-bold">Login is off</h1>
      <Notice>This server is in open mode, so there is nothing to sign in to. You can turn login on inside the app under Settings, Access.</Notice>
      <Link className="font-semibold underline" href="/dashboard">Go to the dashboard</Link>
    </main>
  );
  return (
    <main className="mx-auto grid min-h-screen max-w-sm content-center gap-4 px-6">
      <h1 className="text-2xl font-bold">Sign in</h1>
      <Card><form onSubmit={submit} className="grid gap-4">
        <Field label="Email"><Input name="email" type="email" required autoComplete="email" /></Field>
        <Field label="Password"><Input name="password" type="password" required autoComplete="current-password" /></Field>
        {err && <Notice kind="error">{err}</Notice>}
        <Button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
      </form></Card>
      <p className="text-sm text-ink2">No account? <Link className="underline" href="/register">Create one</Link></p>
    </main>
  );
}

"use client";
import Link from "next/link";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useConfig } from "@/lib/config";
import { Button, Card, Field, Input, Notice } from "@/components/ui";

export default function Register() {
  const router = useRouter(); const { config } = useConfig();
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setErr("");
    const f = new FormData(e.currentTarget); const email = String(f.get("email")); const password = String(f.get("password"));
    try {
      await api(undefined, "/api/accounts/register", { method: "POST", body: JSON.stringify({ email, password, name: f.get("name") }) });
      const r = await signIn("credentials", { email, password, redirect: false });
      if (r?.error) throw new Error("Account created, but sign-in failed. Try signing in."); router.push("/dashboard");
    } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
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
      <h1 className="text-2xl font-bold">Create account</h1>
      <Card><form onSubmit={submit} className="grid gap-4">
        <Field label="Name"><Input name="name" autoComplete="name" /></Field>
        <Field label="Email"><Input name="email" type="email" required autoComplete="email" /></Field>
        <Field label="Password (8+ characters)"><Input name="password" type="password" minLength={8} required autoComplete="new-password" /></Field>
        {err && <Notice kind="error">{err}</Notice>}
        <Button disabled={busy}>{busy ? "Creating…" : "Create account"}</Button>
      </form></Card>
      <p className="text-sm text-ink2">Already registered? <Link className="underline" href="/login">Sign in</Link></p>
    </main>
  );
}

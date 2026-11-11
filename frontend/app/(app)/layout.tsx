"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { signOut, useSession } from "next-auth/react";
import { useConfig } from "@/lib/config";
import { Button, Notice } from "@/components/ui";

const NAV = [["/dashboard", "Dashboard"], ["/strategies", "Strategies"], ["/backtests", "Backtests"], ["/scanner", "Scanner"], ["/ai", "AI Analyst"], ["/portfolio", "Portfolio"], ["/brokers", "Brokers"], ["/brokers/kotak-neo", "Kotak Neo API"], ["/settings", "Settings"]];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname(); const router = useRouter();
  const { config, error, reload } = useConfig(); const { data: session, status } = useSession();
  const open = config?.mode === "open";
  useEffect(() => { if (config?.mode === "login" && status === "unauthenticated") router.replace("/login"); }, [config, status, router]);

  if (error) return <main className="mx-auto max-w-md p-8"><Notice kind="error">Cannot reach the API: {error}. Start it with <code>cd backend &amp;&amp; uvicorn app.main:app --port 8000</code>, then retry.</Notice><div className="mt-3"><Button onClick={reload}>Retry</Button></div></main>;
  if (!config || (!open && status !== "authenticated")) return <main className="p-8 text-ink2" role="status">Loading…</main>;

  return (
    <div className="min-h-screen md:grid md:grid-cols-[220px_1fr]">
      <aside className="border-b border-line bg-white p-4 md:border-b-0 md:border-r">
        <div className="mb-4 text-xl font-extrabold">VM<span className="text-gold">Algo</span></div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto md:grid">
          {NAV.map(([href, label]) => (
            <Link key={href} href={href} aria-current={path.startsWith(href) ? "page" : undefined}
              className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium ${path.startsWith(href) ? "bg-ink text-white" : "text-ink hover:bg-paper"}`}>{label}</Link>
          ))}
        </nav>
        <div className="mt-6 hidden text-xs text-ink2 md:block">
          {open ? <>Open mode: no login<br /><Link className="underline" href="/settings#access">Turn on login</Link></>
            : <><div className="truncate">{session?.user?.email}</div><button className="mt-1 underline" onClick={() => signOut({ callbackUrl: "/login" })}>Sign out</button></>}
        </div>
      </aside>
      <main className="mx-auto w-full max-w-6xl p-4 md:p-8">
        {open && (
          <div className="mb-6"><Notice kind="warn">
            <b>Open mode: no login.</b> Anyone who can reach this server can use it. Paper trading only: real-money trading{config.env === "production" ? " and broker connections are" : " is"} disabled until you{" "}
            <Link className="font-semibold underline" href="/settings#access">turn on login</Link>.
          </Notice></div>
        )}
        {children}
      </main>
    </div>
  );
}

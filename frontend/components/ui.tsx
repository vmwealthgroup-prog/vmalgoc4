import React from "react";

export const Card = ({ title, right, children, className = "" }: { title?: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) => (
  <section className={`rounded-xl border border-line bg-white p-5 ${className}`}>
    {(title || right) && <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold text-ink">{title}</h2>{right}</div>}
    {children}
  </section>
);

export const Stat = ({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "gain" | "loss" }) => (
  <div className="rounded-lg border border-line bg-white p-4">
    <div className="text-xs uppercase tracking-wide text-ink2">{label}</div>
    <div className={`mt-1 text-2xl font-semibold ${tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "text-ink"}`}>{value}</div>
  </div>
);

export const Button = ({ variant = "primary", className = "", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) => (
  <button {...p} className={`rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50 ${variant === "primary" ? "bg-gold text-ink hover:brightness-95" : variant === "danger" ? "bg-loss text-white hover:brightness-95" : "border border-ink/30 text-ink hover:bg-paper"} ${className}`} />
);

export const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="grid gap-1 text-sm font-medium text-ink">{label}{children}</label>
);

export const inputCls = "rounded-lg border border-line bg-white px-3 py-2 text-sm font-normal text-ink focus:outline-none focus:ring-2 focus:ring-gold";
export const Input = (p: React.InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={`${inputCls} ${p.className ?? ""}`} />;
export const Select = (p: React.SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={`${inputCls} ${p.className ?? ""}`} />;

export const Notice = ({ kind = "info", children }: { kind?: "info" | "error" | "ok" | "warn"; children: React.ReactNode }) => (
  <div role={kind === "error" ? "alert" : "status"} className={`rounded-lg border px-3 py-2 text-sm ${kind === "error" ? "border-loss/40 bg-loss/5 text-loss" : kind === "ok" ? "border-gain/40 bg-gain/5 text-gain" : kind === "warn" ? "border-gold bg-gold/10 text-ink" : "border-line bg-paper text-ink2"}`}>{children}</div>
);

export const Table = ({ head, children }: { head: string[]; children: React.ReactNode }) => (
  <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b border-line text-xs uppercase text-ink2">{head.map((h) => <th key={h} className="px-2 py-2 font-medium">{h}</th>)}</tr></thead><tbody className="[&_td]:px-2 [&_td]:py-2 [&_tr]:border-b [&_tr]:border-line/60">{children}</tbody></table></div>
);

export const Pnl = ({ v }: { v: number }) => <span className={v > 0 ? "text-gain" : v < 0 ? "text-loss" : ""}>{v > 0 ? "+" : ""}{v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span>;

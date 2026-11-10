"use client";
import { Button, Field, Input, Select } from "./ui";
import type { Condition, Group, Operand } from "@/lib/types";

const INDS = ["close", "open", "high", "low", "volume", "ema", "sma", "rsi", "atr", "hh", "ll"];
const NEEDS_PERIOD = new Set(["ema", "sma", "rsi", "atr", "hh", "ll"]);
const OPS: [string, string][] = [[">", "is above"], ["<", "is below"], [">=", ">="], ["<=", "<="], ["crosses_above", "crosses above"], ["crosses_below", "crosses below"]];

function OperandEditor({ o, onChange, label }: { o: Operand; onChange: (o: Operand) => void; label: string }) {
  const isValue = o.value !== undefined;
  return (
    <div className="flex flex-wrap items-center gap-1" role="group" aria-label={label}>
      <Select aria-label={`${label} type`} value={isValue ? "value" : o.ind} onChange={(e) => onChange(e.target.value === "value" ? { value: 0 } : { ind: e.target.value, period: 14 })}>
        {INDS.map((i) => <option key={i} value={i}>{i}</option>)}<option value="value">number</option>
      </Select>
      {isValue && <Input aria-label={`${label} value`} type="number" step="any" className="w-24" value={o.value} onChange={(e) => onChange({ value: Number(e.target.value) })} />}
      {!isValue && o.ind && NEEDS_PERIOD.has(o.ind) && <Input aria-label={`${label} period`} type="number" min={1} max={1000} className="w-20" value={o.period ?? 14} onChange={(e) => onChange({ ...o, period: Number(e.target.value) })} />}
    </div>
  );
}

export default function ConditionEditor({ title, group, onChange }: { title: string; group: Group; onChange: (g: Group) => void }) {
  const key: "all" | "any" = group.any ? "any" : "all";
  const rows: Condition[] = group[key] ?? [];
  const set = (r: Condition[], k = key) => onChange({ [k]: r } as Group);
  return (
    <fieldset className="grid gap-2 rounded-lg border border-line p-3">
      <legend className="px-1 text-sm font-semibold">{title}</legend>
      <div className="flex items-center gap-2 text-sm">Trigger when
        <Select aria-label={`${title} match mode`} value={key} onChange={(e) => set(rows, e.target.value as "all" | "any")}><option value="all">ALL conditions</option><option value="any">ANY condition</option></Select>
      </div>
      {rows.map((c, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2">
          <OperandEditor label={`${title} ${i + 1} left`} o={c.left} onChange={(left) => set(rows.map((x, j) => (j === i ? { ...x, left } : x)))} />
          <Select aria-label={`${title} ${i + 1} operator`} value={c.op} onChange={(e) => set(rows.map((x, j) => (j === i ? { ...x, op: e.target.value } : x)))}>{OPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>
          <OperandEditor label={`${title} ${i + 1} right`} o={c.right} onChange={(right) => set(rows.map((x, j) => (j === i ? { ...x, right } : x)))} />
          <Button type="button" variant="ghost" aria-label={`Remove ${title} condition ${i + 1}`} onClick={() => set(rows.filter((_, j) => j !== i))}>Remove</Button>
        </div>
      ))}
      <div><Button type="button" variant="ghost" onClick={() => set([...rows, { left: { ind: "close" }, op: ">", right: { ind: "ema", period: 20 } }])}>+ Add condition</Button></div>
    </fieldset>
  );
}

export const FieldRow = ({ label, children }: { label: string; children: React.ReactNode }) => <Field label={label}>{children}</Field>;

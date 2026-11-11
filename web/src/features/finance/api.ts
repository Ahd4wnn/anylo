import { api } from "@/api/client";

export interface Metrics {
  gross_sales: string; returns: string; net_sales: string; output_tax: string; net_revenue: string; cogs: string;
  gross_profit: string; gross_margin_pct: string; expenses: string; labour: string; net_profit: string; collections: string;
  invoices_count: number; avg_bill_value: string; new_customers: number;
}
export interface Goal {
  id: string; metric: string; metric_label: string; title: string; period_start: string; period_end: string; target: string;
  user_id: string | null; user_name: string | null; actual: string; percent: string; elapsed_percent: string;
  expected_by_now: string; run_rate_needed: string | null; projection: string; days_left: number;
  status: "achieved" | "on_track" | "at_risk" | "behind" | "missed";
}
export interface Dashboard {
  from: string; to: string; grain: "day" | "week"; current: Metrics; previous: Metrics;
  receivables: string; payables: string; stock_value: string; cash_in_hand: string;
  trend: { date: string; sales: string; profit: string }[];
  payment_mix: { method: string; amount: string }[];
  top_by_revenue: { name: string; qty: string; revenue: string; profit: string }[];
  top_by_profit: { name: string; qty: string; revenue: string; profit: string }[];
  staff: { name: string; bills: number; sales: string; avg_bill: string }[];
  alerts: { kind: string; text: string; link: string }[];
  goals: Goal[];
}

const iso = (d: Date) => d.toLocaleDateString("en-CA");
/** Range presets from the spec: today, yesterday, this week, this month, last month, this financial year. */
export function presetRange(p: string): [string, string] {
  const t = new Date();
  const d = (y: number, m: number, day: number) => new Date(y, m, day);
  switch (p) {
    case "yesterday": { const y = d(t.getFullYear(), t.getMonth(), t.getDate() - 1); return [iso(y), iso(y)]; }
    case "week": { const s = d(t.getFullYear(), t.getMonth(), t.getDate() - ((t.getDay() + 6) % 7)); return [iso(s), iso(t)]; }
    case "month": return [iso(d(t.getFullYear(), t.getMonth(), 1)), iso(t)];
    case "last_month": return [iso(d(t.getFullYear(), t.getMonth() - 1, 1)), iso(d(t.getFullYear(), t.getMonth(), 0))];
    case "fy": { const y = t.getMonth() >= 3 ? t.getFullYear() : t.getFullYear() - 1; return [iso(d(y, 3, 1)), iso(t)]; }
    default: return [iso(t), iso(t)];
  }
}
export const PRESETS = [["today", "Today"], ["yesterday", "Yesterday"], ["week", "This week"], ["month", "This month"], ["last_month", "Last month"], ["fy", "This FY"]] as const;

/** Download a server-built file (Excel) through the authenticated client. */
export async function download(path: string, fallbackName: string) {
  const blob = await api<Blob>(path, { blob: true });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = fallbackName;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}

export const GOAL_STATUS: Record<Goal["status"], { label: string; tone: "success" | "brand" | "warning" | "neutral" }> = {
  achieved: { label: "Achieved", tone: "success" }, on_track: { label: "On track", tone: "brand" },
  at_risk: { label: "At risk", tone: "warning" }, behind: { label: "Behind", tone: "warning" }, missed: { label: "Missed", tone: "neutral" },
};

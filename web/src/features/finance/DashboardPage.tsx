import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowDown, ArrowUp, Download } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Badge, PageHeader, useToast } from "@/ui/primitives";
import { download, GOAL_STATUS, presetRange, PRESETS, type Dashboard, type Goal, type Metrics } from "./api";

const rupees = (v: string | number) => formatINR(String(v), { always: true });
const cell = "h-10 rounded-lg border border-border-strong bg-surface px-3";

export function RangePicker({ from, to, onChange }: { from: string; to: string; onChange: (f: string, t: string) => void }) {
  const active = PRESETS.find(([p]) => { const [a, b] = presetRange(p); return a === from && b === to; })?.[0];
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Period">
        {PRESETS.map(([p, label]) => (
          <button key={p} role="radio" aria-checked={active === p} onClick={() => onChange(...presetRange(p))}
            className={`h-10 rounded-lg px-3 text-sm font-medium ${active === p ? "bg-primary text-on-primary" : "bg-surface text-text-2 hover:bg-surface-2"}`}>{label}</button>
        ))}
      </div>
      <input type="date" value={from} max={to} onChange={(e) => onChange(e.target.value, to)} aria-label="From" className={cell} />
      <input type="date" value={to} min={from} onChange={(e) => onChange(from, e.target.value)} aria-label="To" className={cell} />
    </div>
  );
}

function Delta({ now, before, money = true }: { now: number; before: number; money?: boolean }) {
  if (!before) return <span className="text-xs text-text-3">no earlier data</span>;
  const pct = ((now - before) / Math.abs(before)) * 100;
  const up = pct >= 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-semibold ${up ? "text-success" : "text-danger"}`}>
      {up ? <ArrowUp className="h-3 w-3" aria-hidden /> : <ArrowDown className="h-3 w-3" aria-hidden />}
      {Math.abs(pct).toFixed(0)}%<span className="font-normal text-text-3"> vs {money ? rupees(before) : before}</span>
    </span>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="text-sm text-text-2">{label}</p>
      <p className="tnum mt-1 text-2xl font-bold">{value}</p>
      {sub && <div className="mt-1">{sub}</div>}
    </div>
  );
}

/** Single-series bar chart; hover (or focus) a bar to read its day. */
function TrendChart({ data, grain }: { data: Dashboard["trend"]; grain: Dashboard["grain"] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (!data.length) return <p className="py-10 text-center text-text-2">No sales in this period.</p>;
  const max = Math.max(...data.map((d) => Number(d.sales)), 1);
  const W = 100 / data.length;
  const label = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  const shown = data[hover ?? data.length - 1];
  return (
    <div>
      <p className="tnum mb-2 text-sm text-text-2" aria-live="polite">
        {grain === "week" ? "Week of " : ""}{label(shown.date)} · <span className="font-semibold text-text">{rupees(shown.sales)}</span> sales · {rupees(shown.profit)} gross profit
      </p>
      <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="h-40 w-full" role="img" aria-label="Sales by day">
        <line x1="0" y1="40" x2="100" y2="40" stroke="rgb(var(--border))" strokeWidth="0.3" vectorEffect="non-scaling-stroke" />
        {data.map((d, i) => {
          const h = (Number(d.sales) / max) * 38;
          return (
            <g key={d.date} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={i * W} y="0" width={W} height="40" fill="transparent" />
              <rect x={i * W + W * 0.15} y={40 - Math.max(h, 0.4)} width={W * 0.7} height={Math.max(h, 0.4)} rx="0.6"
                fill={hover === i ? "rgb(var(--primary-hover))" : "rgb(var(--primary))"} />
            </g>
          );
        })}
      </svg>
      <div className="mt-1 flex justify-between text-xs text-text-3"><span>{label(data[0].date)}</span><span>{label(data[data.length - 1].date)}</span></div>
    </div>
  );
}

/** Ranked rows with direct labels: the bar shows share, the text carries the value. */
function Bars({ rows, value }: { rows: { label: string; v: number; note?: string }[]; value: (n: number) => string }) {
  const max = Math.max(...rows.map((r) => r.v), 1);
  return (
    <ul className="space-y-2.5">
      {rows.map((r) => (
        <li key={r.label}>
          <div className="flex justify-between gap-3 text-sm"><span className="truncate">{r.label}</span><span className="tnum font-semibold">{value(r.v)}{r.note && <span className="font-normal text-text-2"> · {r.note}</span>}</span></div>
          <div className="mt-1 h-2 rounded-full bg-surface-2"><div className="h-2 rounded-full bg-primary" style={{ width: `${Math.max((r.v / max) * 100, 1)}%` }} /></div>
        </li>
      ))}
    </ul>
  );
}

export function GoalCard({ g }: { g: Goal }) {
  const money = !["invoices_count", "new_customers"].includes(g.metric);
  const fmt = (v: string) => (money ? rupees(v) : String(Number(v)));
  const s = GOAL_STATUS[g.status];
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <div><p className="font-semibold">{g.title}</p><p className="text-xs text-text-2">{g.user_name ?? "Whole shop"} · {g.days_left} day{g.days_left === 1 ? "" : "s"} left</p></div>
        <Badge tone={s.tone}>{s.label}</Badge>
      </div>
      <p className="tnum mt-3 text-sm"><span className="text-lg font-bold">{fmt(g.actual)}</span> <span className="text-text-2">of {fmt(g.target)}</span></p>
      <div className="relative mt-2 h-2.5 rounded-full bg-surface-2" role="progressbar" aria-valuenow={Number(g.percent)} aria-valuemin={0} aria-valuemax={100} aria-label={g.title}>
        <div className="h-2.5 rounded-full bg-primary" style={{ width: `${Math.min(Number(g.percent), 100)}%` }} />
        <div className="absolute top-[-3px] h-4 w-0.5 bg-text-2" style={{ left: `${Math.min(Number(g.elapsed_percent), 100)}%` }} title="Where you should be by now" />
      </div>
      <p className="mt-2 text-xs text-text-2">{g.percent}% done · {g.elapsed_percent}% of time gone{g.run_rate_needed && ` · need ${fmt(g.run_rate_needed)}/day`}</p>
    </div>
  );
}

export function DashboardPage() {
  const toast = useToast((s) => s.show);
  const [[from, to], setRange] = useState(presetRange("today"));
  const { data: d } = useQuery({ queryKey: ["dashboard", from, to], queryFn: () => api<Dashboard>(`/dashboard?from=${from}&to=${to}`), placeholderData: keepPreviousData });
  const n = (m: Metrics, k: keyof Metrics) => Number(m[k]);
  return (
    <>
      <PageHeader title="Dashboard" description="How the shop is doing. Every number is compared with the same length of time just before."
        action={<Button size="md" variant="secondary" onClick={() => download(`/reports/export?from=${from}&to=${to}`, `anylo-business-${from}-to-${to}.xlsx`).catch(() => toast("Couldn't download."))}>
          <Download className="h-4 w-4" aria-hidden />Excel</Button>} />
      <div className="mb-5"><RangePicker from={from} to={to} onChange={(a, b) => setRange([a, b])} /></div>
      {!d ? <p className="text-text-2">Loading…</p> : (
        <div className="space-y-6">
          {d.alerts.length > 0 && (
            <ul className="space-y-2">
              {d.alerts.map((a) => (
                <li key={a.kind}><Link to={a.link} className="flex items-center gap-3 rounded-lg bg-warning-soft px-4 py-2.5 text-sm text-warning hover:underline">
                  <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />{a.text}</Link></li>
              ))}
            </ul>
          )}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Tile label="Net sales" value={rupees(d.current.net_sales)} sub={<Delta now={n(d.current, "net_sales")} before={n(d.previous, "net_sales")} />} />
            <Tile label={`Gross profit · ${d.current.gross_margin_pct}%`} value={rupees(d.current.gross_profit)} sub={<Delta now={n(d.current, "gross_profit")} before={n(d.previous, "gross_profit")} />} />
            <Tile label="Net profit" value={rupees(d.current.net_profit)} sub={<Delta now={n(d.current, "net_profit")} before={n(d.previous, "net_profit")} />} />
            <Tile label="Bills" value={String(d.current.invoices_count)} sub={<Delta now={d.current.invoices_count} before={d.previous.invoices_count} money={false} />} />
            <Tile label="Average bill" value={rupees(d.current.avg_bill_value)} sub={<Delta now={n(d.current, "avg_bill_value")} before={n(d.previous, "avg_bill_value")} />} />
            <Tile label="Collections" value={rupees(d.current.collections)} sub={<Delta now={n(d.current, "collections")} before={n(d.previous, "collections")} />} />
            <Tile label="Customers owe you" value={rupees(d.receivables)} sub={<Link to="/app/reports/receivables" className="text-xs font-semibold text-primary hover:underline">See who</Link>} />
            <Tile label="Cash in drawer" value={rupees(d.cash_in_hand)} sub={<span className="text-xs text-text-2">Stock worth {rupees(d.stock_value)}</span>} />
          </div>
          <section className="rounded-xl border border-border bg-surface p-5" aria-label="Sales trend">
            <h2 className="mb-3 font-semibold">Sales {d.grain === "week" ? "by week" : "by day"}</h2>
            <TrendChart data={d.trend} grain={d.grain} />
          </section>
          {d.goals.length > 0 && (
            <section aria-label="Goals">
              <div className="mb-2 flex items-center justify-between"><h2 className="font-semibold">Goals</h2><Link to="/app/reports/goals" className="text-sm font-semibold text-primary hover:underline">All goals</Link></div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{d.goals.slice(0, 6).map((g) => <GoalCard key={g.id} g={g} />)}</div>
            </section>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-xl border border-border bg-surface p-5" aria-label="How customers paid">
              <h2 className="mb-3 font-semibold">How customers paid</h2>
              {d.payment_mix.length ? <Bars rows={d.payment_mix.map((m) => ({ label: m.method === "due" ? "Kept as due" : m.method.toUpperCase(), v: Number(m.amount) }))} value={(v) => rupees(v.toFixed(2))} />
                : <p className="text-text-2">No bills yet.</p>}
            </section>
            <section className="rounded-xl border border-border bg-surface p-5" aria-label="Top items">
              <h2 className="mb-3 font-semibold">Top items by sales</h2>
              {d.top_by_revenue.length ? <Bars rows={d.top_by_revenue.map((p) => ({ label: p.name, v: Number(p.revenue), note: `profit ${rupees(p.profit)}` }))} value={(v) => rupees(v.toFixed(2))} />
                : <p className="text-text-2">No bills yet.</p>}
            </section>
            <section className="rounded-xl border border-border bg-surface p-5" aria-label="Most profitable items">
              <h2 className="mb-3 font-semibold">Most profitable items</h2>
              {d.top_by_profit.length ? <Bars rows={d.top_by_profit.map((p) => ({ label: p.name, v: Number(p.profit), note: `${Number(p.qty)} sold` }))} value={(v) => rupees(v.toFixed(2))} />
                : <p className="text-text-2">No bills yet.</p>}
            </section>
            <section className="rounded-xl border border-border bg-surface p-5" aria-label="Staff">
              <h2 className="mb-3 font-semibold">Staff</h2>
              {d.staff.length ? (
                <table className="tnum w-full text-sm">
                  <thead className="text-left text-text-2"><tr><th className="pb-2 font-medium">Name</th><th className="pb-2 text-right font-medium">Bills</th><th className="pb-2 text-right font-medium">Sales</th><th className="pb-2 text-right font-medium">Avg bill</th></tr></thead>
                  <tbody className="divide-y divide-border">{d.staff.map((s) => <tr key={s.name}><td className="py-2">{s.name}</td><td className="py-2 text-right">{s.bills}</td><td className="py-2 text-right">{rupees(s.sales)}</td><td className="py-2 text-right">{rupees(s.avg_bill)}</td></tr>)}</tbody>
                </table>
              ) : <p className="text-text-2">No bills yet.</p>}
            </section>
          </div>
        </div>
      )}
    </>
  );
}

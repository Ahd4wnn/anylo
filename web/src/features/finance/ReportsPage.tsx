import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Trash2 } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { useShop } from "@/features/shop/api";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Dialog, PageHeader, useToast } from "@/ui/primitives";
import { download, presetRange, type Goal, type Metrics } from "./api";
import { GoalCard, RangePicker } from "./DashboardPage";

const rupees = (v: string | number | null | undefined) => (v === null || v === undefined ? "" : formatINR(String(v), { always: true }));
const cell = "h-10 rounded-lg border border-border-strong bg-surface px-3";
const err = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);

export function ReportsPage() {
  const can = useAuth((s) => s.can);
  const tabs = [
    ...(can("report.view") ? [["pnl", "Profit & loss"], ["cash-flow", "Cash flow"], ["receivables", "Who owes you"], ["payables", "What you owe"]] : []),
    ...(can("report.gst") ? [["gst", "GST returns"]] : []),
    ["goals", "Goals"],
  ];
  return (
    <>
      <PageHeader title="Reports" description="Your books in plain words, GST returns ready for filing, and goals." />
      <nav className="mb-6 flex gap-1 overflow-x-auto shadow-[inset_0_-1px_0_rgb(var(--border))] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" aria-label="Report sections">
        {tabs.map(([to, label]) => (
          <NavLink key={to} to={to} className={({ isActive }) => `whitespace-nowrap border-b-2 px-4 py-2.5 font-medium ${isActive ? "border-primary text-primary" : "border-transparent text-text-2 hover:text-text"}`}>{label}</NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Navigate to={tabs[0][0]} replace />} />
        <Route path="pnl" element={<Pnl />} />
        <Route path="cash-flow" element={<CashFlow />} />
        <Route path="receivables" element={<Ageing kind="receivables" />} />
        <Route path="payables" element={<Ageing kind="payables" />} />
        <Route path="gst" element={<Gst />} />
        <Route path="goals" element={<Goals />} />
      </Routes>
    </>
  );
}

function useRange(preset = "month") {
  const [[from, to], set] = useState(presetRange(preset));
  return { from, to, picker: <RangePicker from={from} to={to} onChange={(a, b) => set([a, b])} /> };
}

function Table({ head, children, foot }: { head: ReactNode; children: ReactNode; foot?: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-surface">
      <table className="tnum w-full text-sm">
        <thead className="text-left text-text-2"><tr className="border-b border-border">{head}</tr></thead>
        <tbody className="divide-y divide-border">{children}</tbody>
        {foot && <tfoot className="border-t-2 border-border font-semibold">{foot}</tfoot>}
      </table>
    </div>
  );
}
const th = "px-4 py-2.5 font-medium";
const td = "px-4 py-2.5";

const PL_LINES: [string, keyof Metrics, boolean?][] = [
  ["Sales (incl. GST)", "gross_sales"], ["Returns", "returns"], ["Net sales", "net_sales", true], ["GST collected", "output_tax"],
  ["Revenue without GST", "net_revenue", true], ["Cost of goods sold", "cogs"], ["Gross profit", "gross_profit", true],
  ["Expenses", "expenses"], ["Wages", "labour"], ["Net profit", "net_profit", true],
];

function Pnl() {
  const r = useRange();
  const { data } = useQuery({ queryKey: ["pnl", r.from, r.to], queryFn: () => api<{ months: (Metrics & { from: string })[]; total: Metrics; expenses_by_category: { name: string; amount: string }[] }>(`/reports/pnl?from=${r.from}&to=${r.to}`) });
  const toast = useToast((s) => s.show);
  const multi = (data?.months.length ?? 0) > 1;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">{r.picker}
        <Button size="md" variant="secondary" onClick={() => download(`/reports/export?from=${r.from}&to=${r.to}`, `anylo-business-${r.from}-to-${r.to}.xlsx`).catch(() => toast("Couldn't download."))}><Download className="h-4 w-4" aria-hidden />Excel</Button>
      </div>
      {data && (
        <>
          <Table head={<><th className={th}>Line</th>{multi && data.months.map((m) => <th key={m.from} className={`${th} text-right`}>{new Date(m.from).toLocaleDateString("en-IN", { month: "short", year: "2-digit" })}</th>)}<th className={`${th} text-right`}>Total</th></>}>
            {PL_LINES.map(([label, k, bold]) => (
              <tr key={k} className={bold ? "font-semibold" : ""}>
                <td className={td}>{label}</td>
                {multi && data.months.map((m) => <td key={m.from} className={`${td} text-right`}>{rupees(m[k])}</td>)}
                <td className={`${td} text-right ${k === "net_profit" && Number(data.total[k]) < 0 ? "text-danger" : ""}`}>{rupees(data.total[k])}</td>
              </tr>
            ))}
          </Table>
          <p className="text-sm text-text-2">Gross margin {data.total.gross_margin_pct}% · {data.total.invoices_count} bills · cost uses each item's average purchase cost. Wages are counted when paid.</p>
          {data.expenses_by_category.length > 0 && (
            <Table head={<><th className={th}>Expense</th><th className={`${th} text-right`}>Amount</th></>}>
              {data.expenses_by_category.map((e) => <tr key={e.name}><td className={td}>{e.name}</td><td className={`${td} text-right`}>{rupees(e.amount)}</td></tr>)}
            </Table>
          )}
        </>
      )}
    </div>
  );
}

function CashFlow() {
  const r = useRange();
  const { data } = useQuery({ queryKey: ["cash-flow", r.from, r.to], queryFn: () => api<{ lines: { direction: string; label: string; cash: string; bank: string }[]; net_cash: string; net_bank: string; opening_cash: string; closing_cash: string }>(`/reports/cash-flow?from=${r.from}&to=${r.to}`) });
  const signed = (x: { direction: string }, v: string) => (x.direction === "in" ? rupees(v) : rupees(-Number(v)));
  return (
    <div className="space-y-4">
      {r.picker}
      {data && (
        <Table head={<><th className={th}></th><th className={`${th} text-right`}>Cash</th><th className={`${th} text-right`}>Bank / UPI / card</th></>}
          foot={<><tr><td className={td}>Net movement</td><td className={`${td} text-right`}>{rupees(data.net_cash)}</td><td className={`${td} text-right`}>{rupees(data.net_bank)}</td></tr>
            <tr><td className={td}>Cash at the end</td><td className={`${td} text-right`}>{rupees(data.closing_cash)}</td><td /></tr></>}>
          <tr><td className={td}>Cash at the start</td><td className={`${td} text-right`}>{rupees(data.opening_cash)}</td><td /></tr>
          {data.lines.map((x) => (
            <tr key={x.direction + x.label}><td className={td}>{x.label}</td>
              <td className={`${td} text-right ${x.direction === "out" ? "text-danger" : ""}`}>{signed(x, x.cash)}</td>
              <td className={`${td} text-right ${x.direction === "out" ? "text-danger" : ""}`}>{signed(x, x.bank)}</td></tr>
          ))}
        </Table>
      )}
    </div>
  );
}

const BUCKETS = [["0_30", "0–30 days"], ["31_60", "31–60"], ["61_90", "61–90"], ["over_90", "Over 90"]] as const;
type AgeRow = Record<(typeof BUCKETS)[number][0] | "balance", string> & { name: string; phone?: string | null };

function Ageing({ kind }: { kind: "receivables" | "payables" }) {
  const { data } = useQuery({ queryKey: [kind], queryFn: () => api<{ items: AgeRow[]; totals: Record<string, string> }>(`/reports/${kind}`) });
  if (!data) return <p className="text-text-2">Loading…</p>;
  if (!data.items.length) return <p className="rounded-xl border border-dashed border-border-strong bg-surface p-8 text-center text-text-2">{kind === "receivables" ? "No one owes you anything right now." : "You don't owe any supplier right now."}</p>;
  return (
    <Table head={<><th className={th}>{kind === "receivables" ? "Customer" : "Supplier"}</th>{BUCKETS.map(([k, l]) => <th key={k} className={`${th} text-right`}>{l}</th>)}<th className={`${th} text-right`}>Total</th></>}
      foot={<tr><td className={td}>Total</td>{BUCKETS.map(([k]) => <td key={k} className={`${td} text-right`}>{rupees(data.totals[k])}</td>)}<td className={`${td} text-right`}>{rupees(data.totals.balance)}</td></tr>}>
      {data.items.map((r) => (
        <tr key={r.name + (r.phone ?? "")}>
          <td className={td}>{r.name}{r.phone && <span className="text-text-2"> · {r.phone}</span>}</td>
          {BUCKETS.map(([k]) => <td key={k} className={`${td} text-right ${k === "over_90" && Number(r[k]) > 0 ? "text-danger" : ""}`}>{Number(r[k]) ? rupees(r[k]) : "—"}</td>)}
          <td className={`${td} text-right font-semibold`}>{rupees(r.balance)}</td>
        </tr>
      ))}
    </Table>
  );
}

type Tax = { taxable: string; igst: string; cgst: string; sgst: string; cess: string };
interface G1 { b2b: unknown[]; b2cl: unknown[]; b2cs: unknown[]; cdnr: unknown[]; cdnur: unknown[]; totals: Record<string, Tax>; docs: { nature: string; sr_from: string; sr_to: string; total: number; cancelled: number }[]; nil: Record<string, string>; disclaimer: string }
interface G3 { outward_taxable: Tax; nil_exempt: string; inter_state_unregistered: ({ pos: string } & Tax)[]; itc: Omit<Tax, "taxable">; payable: Omit<Tax, "taxable">; itc_note: string }

function Gst() {
  const { data: shop } = useShop();
  const toast = useToast((s) => s.show);
  const thisMonth = new Date().toLocaleDateString("en-CA").slice(0, 7);
  const [period, setPeriod] = useState(thisMonth);
  const regular = shop?.tax.gst_scheme === "regular";
  const g1 = useQuery({ queryKey: ["gstr1", period], queryFn: () => api<G1>(`/reports/gst/gstr1?period=${period}`), enabled: regular });
  const g3 = useQuery({ queryKey: ["gstr3b", period], queryFn: () => api<G3>(`/reports/gst/gstr3b?period=${period}`), enabled: regular });
  const q = new Date(`${period}-01`);
  const qStart = new Date(q.getFullYear(), Math.floor(q.getMonth() / 3) * 3, 1); // FY quarters (Apr–Jun…) are calendar quarters
  const qEnd = new Date(qStart.getFullYear(), qStart.getMonth() + 3, 0);
  const iso = (d: Date) => d.toLocaleDateString("en-CA");
  const cmp = useQuery({ queryKey: ["cmp08", period], queryFn: () => api<{ turnover: string; rate: string; cgst: string; sgst: string; total: string; from: string; to: string }>(`/reports/gst/cmp08?from=${iso(qStart)}&to=${iso(qEnd)}`), enabled: shop?.tax.gst_scheme === "composition" });
  if (!shop) return null;
  if (shop.tax.gst_scheme === "unregistered") return <p className="rounded-xl border border-dashed border-border-strong bg-surface p-8 text-center text-text-2">Your shop isn't GST registered, so there are no returns to file. Add your GSTIN in Settings → GST when you register.</p>;
  const taxRow = (label: string, t?: Partial<Tax>) => (
    <tr key={label}><td className={td}>{label}</td>{(["taxable", "igst", "cgst", "sgst", "cess"] as const).map((k) => <td key={k} className={`${td} text-right`}>{t?.[k] !== undefined ? rupees(t[k]) : ""}</td>)}</tr>
  );
  const taxHead = <><th className={th}></th><th className={`${th} text-right`}>Taxable</th><th className={`${th} text-right`}>IGST</th><th className={`${th} text-right`}>CGST</th><th className={`${th} text-right`}>SGST</th><th className={`${th} text-right`}>Cess</th></>;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm font-medium">Month <input type="month" value={period} max={thisMonth} onChange={(e) => setPeriod(e.target.value)} className={cell} /></label>
        {regular && <Button size="md" variant="secondary" onClick={() => download(`/reports/export?kind=gstr1&period=${period}`, `anylo-gstr1-${period}.xlsx`).catch(() => toast("Couldn't download."))}><Download className="h-4 w-4" aria-hidden />GSTR-1 + 3B Excel</Button>}
      </div>
      {regular && g1.data && g3.data && (
        <>
          <section className="space-y-2" aria-label="GSTR-1">
            <h2 className="font-semibold">GSTR-1 · sales you report</h2>
            <Table head={taxHead}>
              {taxRow(`B2B · ${g1.data.b2b.length} invoice lines to registered buyers`, g1.data.totals.b2b)}
              {taxRow(`B2C large · ${g1.data.b2cl.length} inter-state bills over ₹1 lakh`, g1.data.totals.b2cl)}
              {taxRow(`B2C small · ${g1.data.b2cs.length} rows by state and rate, returns netted`, g1.data.totals.b2cs)}
              {taxRow(`Credit notes, registered · ${g1.data.cdnr.length}`, g1.data.totals.cdnr)}
              {taxRow(`Credit notes, unregistered · ${g1.data.cdnur.length}`, g1.data.totals.cdnur)}
            </Table>
            {g1.data.docs.length > 0 && <p className="text-sm text-text-2">Documents: {g1.data.docs.map((d) => `${d.nature} ${d.sr_from} to ${d.sr_to} (${d.total}, ${d.cancelled} cancelled)`).join(" · ")}</p>}
          </section>
          <section className="space-y-2" aria-label="GSTR-3B">
            <h2 className="font-semibold">GSTR-3B · tax to pay</h2>
            <Table head={taxHead}>
              {taxRow("3.1(a) Outward taxable supplies", g3.data.outward_taxable)}
              {taxRow("3.1(c) Nil rated / exempt", { taxable: g3.data.nil_exempt })}
              {g3.data.inter_state_unregistered.map((r) => taxRow(`3.2 Unregistered buyers in ${r.pos}`, { taxable: r.taxable, igst: r.igst }))}
              {taxRow("4(A)(5) Input tax credit (estimate)", g3.data.itc)}
              {taxRow("Payable before set-off", g3.data.payable)}
            </Table>
            <p className="text-sm text-text-2">{g3.data.itc_note} {g1.data.disclaimer}</p>
          </section>
        </>
      )}
      {cmp.data && (
        <section className="rounded-xl border border-border bg-surface p-5" aria-label="CMP-08">
          <h2 className="font-semibold">CMP-08 · quarter {cmp.data.from} to {cmp.data.to}</h2>
          <p className="tnum mt-2">Turnover {rupees(cmp.data.turnover)} × {Number(cmp.data.rate)}% = <span className="font-bold">{rupees(cmp.data.total)}</span> (CGST {rupees(cmp.data.cgst)} + SGST {rupees(cmp.data.sgst)})</p>
          <p className="mt-1 text-sm text-text-2">Prepared by Anylo for filing assistance. Verify before filing.</p>
        </section>
      )}
      {(g1.error || g3.error) && <p className="text-danger">{err(g1.error ?? g3.error, "Couldn't load the return.")}</p>}
    </div>
  );
}

const METRICS = [["sales", "Sales"], ["gross_profit", "Gross profit"], ["net_profit", "Net profit"], ["invoices_count", "Number of bills"], ["avg_bill_value", "Average bill"], ["new_customers", "New customers"], ["collections", "Collections"]];

function Goals() {
  const can = useAuth((s) => s.can);
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["goals"], queryFn: () => api<Goal[]>("/goals") });
  const [adding, setAdding] = useState(false);
  async function remove(id: string) { await api(`/goals/${id}`, { method: "DELETE" }); void qc.invalidateQueries({ queryKey: ["goals"] }); void qc.invalidateQueries({ queryKey: ["dashboard"] }); }
  return (
    <div className="space-y-4">
      {can("goal.manage") && <div className="flex justify-end"><Button size="md" onClick={() => setAdding(true)}>New goal</Button></div>}
      {data && (data.length ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((g) => (
            <div key={g.id} className="relative">
              <GoalCard g={g} />
              {can("goal.manage") && <button onClick={() => void remove(g.id)} className="absolute bottom-3 right-3 text-text-3 hover:text-danger" aria-label={`Delete goal ${g.title}`}><Trash2 className="h-4 w-4" /></button>}
            </div>
          ))}
        </div>
      ) : <p className="rounded-xl border border-dashed border-border-strong bg-surface p-8 text-center text-text-2">Set a target, like this month's sales, and watch it every day.</p>)}
      {adding && <GoalDialog onClose={() => setAdding(false)} />}
    </div>
  );
}

function GoalDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [s0] = presetRange("month");
  const end0 = (() => { const d = new Date(s0); return new Date(d.getFullYear(), d.getMonth() + 1, 0).toLocaleDateString("en-CA"); })();
  const [metric, setMetric] = useState("sales");
  const [start, setStart] = useState(s0);
  const [end, setEnd] = useState(end0);
  const [target, setTarget] = useState("");
  const [userId, setUserId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => api<{ id: string; full_name: string; is_active: boolean }[]>("/shop/staff") });
  const hint = useQuery({ queryKey: ["goal-suggest", metric, start, end], queryFn: () => api<{ previous: string; suggested: string | null }>(`/goals/suggest?metric=${metric}&start=${start}&end=${end}`), enabled: !!start && !!end && end >= start });
  async function submit(e: FormEvent) {
    e.preventDefault(); setError(null);
    try {
      await api("/goals", { method: "POST", json: { metric, period_start: start, period_end: end, target, user_id: userId || null } });
      void qc.invalidateQueries({ queryKey: ["goals"] }); void qc.invalidateQueries({ queryKey: ["dashboard"] }); onClose();
    } catch (e2) { setError(err(e2, "Couldn't save.")); }
  }
  return (
    <Dialog open onClose={onClose} title="New goal">
      <form onSubmit={submit} className="space-y-4">
        <FormError message={error} />
        <select value={metric} onChange={(e) => setMetric(e.target.value)} aria-label="What to measure" className={`${cell} h-12 w-full`}>
          {METRICS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm font-semibold">From<input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={`${cell} mt-1 h-12 w-full font-normal`} /></label>
          <label className="text-sm font-semibold">To<input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} className={`${cell} mt-1 h-12 w-full font-normal`} /></label>
        </div>
        <input value={target} onChange={(e) => setTarget(e.target.value.replace(/[^\d.]/g, ""))} required inputMode="decimal" placeholder="Target" aria-label="Target" className={`${cell} h-12 w-full`} />
        {hint.data && Number(hint.data.previous) > 0 && (
          <button type="button" onClick={() => setTarget(String(hint.data!.suggested))} className="text-sm font-semibold text-primary hover:underline">
            Last time: {Number(hint.data.previous).toLocaleString("en-IN")}. Use 10% more ({Number(hint.data.suggested).toLocaleString("en-IN")})
          </button>
        )}
        <select value={userId} onChange={(e) => setUserId(e.target.value)} aria-label="For" className={`${cell} h-12 w-full`}>
          <option value="">Whole shop</option>
          {staff.data?.filter((s) => s.is_active).map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
        </select>
        <Button type="submit" className="w-full" disabled={!target}>Save goal</Button>
      </form>
    </Dialog>
  );
}

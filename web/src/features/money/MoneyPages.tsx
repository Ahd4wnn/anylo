import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Trash2, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { Badge, Dialog, PageHeader, Section, useToast } from "@/ui/primitives";
import { cell, day, dayTime, todayIso, useApprovals, type Borrowing, type CashDay, type DayBook, type ExpensePage } from "./api";
import { LabourPanel } from "./LabourPanel";

const rupees = (v: string | number) => formatINR(String(v), { always: true });
const err = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export function MoneyPage() {
  const can = useAuth((s) => s.can);
  const approvals = useApprovals(can("approval.decide"));
  const pending = approvals.data?.length ?? 0;
  const tabs = [
    ...(can("cash.view_today") ? [{ to: "cash", label: "Cash" }] : []),
    ...(can("expense.create") ? [{ to: "expenses", label: "Expenses" }] : []),
    ...(can("labour.attendance") ? [{ to: "labour", label: "Labour" }] : []),
    ...(can("borrowing.manage") ? [{ to: "loans", label: "Loans" }] : []),
    ...(can("approval.decide") ? [{ to: "approvals", label: pending ? `Approvals (${pending})` : "Approvals" }] : []),
  ];
  return (
    <>
      <PageHeader title="Money" description="Cash in hand, what went out, wages and approvals." />
      <nav className="mb-6 flex gap-1 overflow-x-auto shadow-[inset_0_-1px_0_rgb(var(--border))] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" aria-label="Money sections">
        {tabs.map((t) => (
          <NavLink key={t.to} to={t.to}
            className={({ isActive }) => `whitespace-nowrap border-b-2 px-4 py-2.5 font-medium ${isActive ? "border-primary text-primary" : "border-transparent text-text-2 hover:text-text"}`}>
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Navigate to={tabs[0]?.to ?? "cash"} replace />} />
        <Route path="cash" element={<CashPanel />} />
        <Route path="expenses" element={<ExpensesPanel />} />
        <Route path="labour" element={<LabourPanel />} />
        <Route path="loans" element={<LoansPanel />} />
        <Route path="approvals" element={<ApprovalsPanel />} />
      </Routes>
    </>
  );
}

// --- cash ---

function Tile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="text-sm text-text-2">{label}</p>
      <p className={`tnum mt-1 text-xl font-bold ${tone ?? ""}`}>{value}</p>
    </div>
  );
}

function CashPanel() {
  const can = useAuth((s) => s.can);
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const { data: t } = useQuery({ queryKey: ["cash", "today"], queryFn: () => api<CashDay>("/cash/today") });
  const [bookDay, setBookDay] = useState(todayIso());
  const book = useQuery({ queryKey: ["cash", "book", bookDay], queryFn: () => api<DayBook>(`/cash/book?from=${bookDay}&to=${bookDay}`), enabled: can("cash.book") });
  const [counted, setCounted] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (!t) return <p className="text-text-2">Loading…</p>;
  const diff = counted === "" ? null : Number(counted) - Number(t.expected_cash);
  async function close(e: FormEvent) {
    e.preventDefault(); setError(null);
    try {
      await api("/cash/close", { method: "POST", json: { counted_cash: counted, note: note || null } });
      void qc.invalidateQueries({ queryKey: ["cash"] }); void qc.invalidateQueries({ queryKey: ["approvals"] });
      toast("Day closed");
    } catch (e2) { setError(err(e2, "Couldn't close the day.")); }
  }
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile label="Opening cash" value={rupees(t.opening_cash)} />
        <Tile label="Cash in today" value={rupees(t.cash_in)} tone="text-success" />
        <Tile label="Cash out today" value={rupees(t.cash_out)} tone="text-danger" />
        <Tile label="Should be in the drawer" value={rupees(t.expected_cash)} />
      </div>
      {t.breakdown.length > 0 && (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface text-sm">
          {t.breakdown.map((b) => (
            <li key={b.direction + b.label} className="flex justify-between px-4 py-2.5">
              <span>{b.label}</span><span className={`tnum font-medium ${b.direction === "in" ? "text-success" : "text-danger"}`}>{b.direction === "in" ? "+" : "−"}{rupees(b.amount)}</span>
            </li>
          ))}
        </ul>
      )}
      {Number(t.pending_cash) > 0 && <p className="rounded-lg bg-warning-soft px-4 py-3 text-sm text-warning">{rupees(t.pending_cash)} collected by staff is waiting for approval and isn't counted yet.</p>}
      {t.close ? (
        <Section title="Today is closed">
          <p>Counted {rupees(t.close.counted_cash)} · {Number(t.close.difference) === 0 ? "matches" : Number(t.close.difference) < 0 ? `short by ${rupees(-Number(t.close.difference))}` : `over by ${rupees(t.close.difference)}`}</p>
          <p className="text-sm text-text-2">{t.close.status === "pending" ? "Waiting for the owner or manager to confirm." : `Closed by ${t.close.closed_by_name ?? "staff"}`}{t.close.note ? ` · ${t.close.note}` : ""}</p>
        </Section>
      ) : can("cash.close") && (
        <Section title="Close the day" description="Count the cash in the drawer. Tomorrow starts from this amount.">
          <form onSubmit={close} className="space-y-4">
            <FormError message={error} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Cash counted ₹" value={counted} onChange={(e) => setCounted(e.target.value.replace(/[^\d.]/g, ""))} inputMode="decimal" required
                hint={diff === null ? undefined : diff === 0 ? "Matches exactly." : diff < 0 ? `Short by ${rupees(-diff)}` : `Over by ${rupees(diff)}`} />
              <Field label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
            <Button type="submit" size="md">Close day</Button>
          </form>
        </Section>
      )}
      {book.data && (
        <section aria-label="Day book" className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-semibold">Day book</h2>
            <input type="date" value={bookDay} max={todayIso()} onChange={(e) => setBookDay(e.target.value)} aria-label="Day" className={cell} />
          </div>
          <div className="overflow-x-auto rounded-xl border border-border bg-surface">
            <table className="w-full text-sm">
              <thead className="text-left text-text-2"><tr className="border-b border-border">
                <th className="px-4 py-2.5 font-medium">Time</th><th className="px-4 py-2.5 font-medium">Entry</th><th className="px-4 py-2.5 font-medium">Mode</th>
                <th className="px-4 py-2.5 text-right font-medium">Amount</th><th className="px-4 py-2.5 text-right font-medium">Cash</th>
              </tr></thead>
              <tbody className="tnum divide-y divide-border">
                <tr><td className="px-4 py-2.5 text-text-2" colSpan={4}>Opening cash</td><td className="px-4 py-2.5 text-right">{rupees(book.data.opening_cash)}</td></tr>
                {book.data.entries.map((e) => (
                  <tr key={e.id}>
                    <td className="whitespace-nowrap px-4 py-2.5 text-text-2">{new Date(e.at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</td>
                    <td className="px-4 py-2.5">{e.label}</td>
                    <td className="px-4 py-2.5 uppercase text-text-2">{e.method}</td>
                    <td className={`px-4 py-2.5 text-right ${e.direction === "in" ? "text-success" : "text-danger"}`}>{e.direction === "in" ? "+" : "−"}{rupees(e.amount)}</td>
                    <td className="px-4 py-2.5 text-right">{e.method === "cash" ? rupees(e.cash_balance) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

// --- expenses ---

function ExpensesPanel() {
  const can = useAuth((s) => s.can);
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const start = todayIso().slice(0, 8) + "01";
  const [from, setFrom] = useState(start);
  const [to, setTo] = useState(todayIso());
  const { data } = useQuery({ queryKey: ["expenses", from, to], queryFn: () => api<ExpensePage>(`/expenses?from=${from}&to=${to}`) });
  const cats = useQuery({ queryKey: ["expense-categories"], queryFn: () => api<{ id: string; name: string }[]>("/expenses/categories"), staleTime: 600_000 });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const cat = String(f.get("category"));
    setBusy(true); setError(null);
    try {
      await api("/expenses", { method: "POST", json: {
        ...(cat === "__new" ? { category_name: String(f.get("new_category") || "Misc") } : { category_id: cat }),
        amount: f.get("amount"), method: f.get("method"), note: String(f.get("note") || "") || null, occurred_on: f.get("date") || null,
      } });
      form.reset(); void qc.invalidateQueries({ queryKey: ["expenses"] }); void qc.invalidateQueries({ queryKey: ["cash"] }); void qc.invalidateQueries({ queryKey: ["expense-categories"] });
      toast("Expense added");
    } catch (e2) { setError(err(e2, "Couldn't add the expense.")); } finally { setBusy(false); }
  }
  async function remove(id: string) {
    try { await api(`/expenses/${id}`, { method: "DELETE" }); void qc.invalidateQueries({ queryKey: ["expenses"] }); void qc.invalidateQueries({ queryKey: ["cash"] }); toast("Expense removed"); }
    catch (e2) { toast(err(e2, "Couldn't remove.")); }
  }
  const [newCat, setNewCat] = useState(false);
  return (
    <div className="space-y-6">
      <Section title="Add an expense">
        <form onSubmit={add} className="space-y-3">
          <FormError message={error} />
          <div className="grid gap-3 sm:grid-cols-4">
            <select name="category" required defaultValue="" onChange={(e) => setNewCat(e.target.value === "__new")} aria-label="Category" className={cell}>
              <option value="" disabled>Category</option>
              {cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              <option value="__new">+ New category</option>
            </select>
            {newCat && <input name="new_category" required placeholder="Category name" aria-label="New category" className={cell} />}
            <input name="amount" required inputMode="decimal" placeholder="Amount ₹" aria-label="Amount" className={cell} />
            <select name="method" defaultValue="cash" aria-label="Paid by" className={cell}>
              {["cash", "upi", "card", "bank", "cheque"].map((m) => <option key={m} value={m}>{m.toUpperCase()}</option>)}
            </select>
            <input name="date" type="date" defaultValue={todayIso()} max={todayIso()} aria-label="Date" className={cell} />
          </div>
          <div className="flex gap-3">
            <input name="note" placeholder="Note (optional)" aria-label="Note" className={`${cell} flex-1`} />
            <Button type="submit" size="md" loading={busy}>Add</Button>
          </div>
        </form>
      </Section>
      <div className="flex flex-wrap items-center gap-3">
        <input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} aria-label="From" className={cell} />
        <input type="date" value={to} min={from} max={todayIso()} onChange={(e) => setTo(e.target.value)} aria-label="To" className={cell} />
        {data && <p className="ml-auto font-semibold">Total {rupees(data.total)}</p>}
      </div>
      {data && data.by_category.length > 1 && (
        <div className="flex flex-wrap gap-2">{data.by_category.map((c) => <Badge key={c.name}>{c.name} {rupees(c.amount)}</Badge>)}</div>
      )}
      {data && (data.items.length ? (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
          {data.items.map((x) => (
            <li key={x.id} className="flex items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{x.category_name}</p>
                <p className="truncate text-sm text-text-2">{[day(x.occurred_on), x.method.toUpperCase(), x.note, x.created_by_name].filter(Boolean).join(" · ")}</p>
              </div>
              <p className="tnum font-semibold">{rupees(x.amount)}</p>
              {can("expense.manage") && <button onClick={() => void remove(x.id)} className="grid h-9 w-9 place-items-center rounded-md text-text-3 hover:bg-surface-2 hover:text-danger" aria-label={`Remove ${x.category_name} expense`}><Trash2 className="h-4 w-4" /></button>}
            </li>
          ))}
        </ul>
      ) : <p className="rounded-xl border border-dashed border-border-strong bg-surface p-8 text-center text-text-2">No expenses for these dates.</p>)}
    </div>
  );
}

// --- loans ---

function LoansPanel() {
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const { data } = useQuery({ queryKey: ["borrowings"], queryFn: () => api<{ items: Borrowing[]; outstanding: string }>("/borrowings") });
  const [adding, setAdding] = useState(false);
  const [repaying, setRepaying] = useState<Borrowing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["borrowings"] }); void qc.invalidateQueries({ queryKey: ["cash"] }); };
  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(null);
    const f = new FormData(e.currentTarget);
    try {
      await api("/borrowings", { method: "POST", json: { lender_name: f.get("name"), lender_phone: String(f.get("phone") || "") || null, principal: f.get("amount"), received_method: f.get("method"), interest_note: String(f.get("interest") || "") || null } });
      refresh(); setAdding(false); toast("Loan added");
    } catch (e2) { setError(err(e2, "Couldn't save.")); }
  }
  async function repay(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(null);
    const f = new FormData(e.currentTarget);
    try {
      await api(`/borrowings/${repaying!.id}/repay`, { method: "POST", json: { amount: f.get("amount"), method: f.get("method") } });
      refresh(); setRepaying(null); toast("Repayment saved");
    } catch (e2) { setError(err(e2, "Couldn't save.")); }
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        {data && <p className="font-semibold">To repay: {rupees(data.outstanding)}</p>}
        <Button size="md" onClick={() => { setError(null); setAdding(true); }}>Add loan</Button>
      </div>
      {data && (data.items.length ? (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
          {data.items.map((b) => (
            <li key={b.id} className="flex items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{b.lender_name} {b.status === "closed" && <Badge tone="success">Repaid</Badge>}</p>
                <p className="truncate text-sm text-text-2">{[day(b.borrowed_on), `${rupees(b.principal)} taken`, Number(b.repaid) ? `${rupees(b.repaid)} repaid` : null, b.interest_note].filter(Boolean).join(" · ")}</p>
              </div>
              {b.status === "open" && <><p className="tnum font-semibold">{rupees(b.outstanding)}</p><Button size="md" variant="secondary" onClick={() => { setError(null); setRepaying(b); }}>Repay</Button></>}
            </li>
          ))}
        </ul>
      ) : <p className="rounded-xl border border-dashed border-border-strong bg-surface p-8 text-center text-text-2">Money borrowed for the shop shows here, so cash in hand stays right.</p>)}
      <Dialog open={adding} onClose={() => setAdding(false)} title="Money borrowed">
        <form onSubmit={add} className="space-y-4">
          <FormError message={error} />
          <Field label="From (lender)" name="name" required />
          <Field label="Lender mobile (optional)" name="phone" inputMode="numeric" maxLength={10} />
          <Field label="Amount ₹" name="amount" required inputMode="decimal" />
          <select name="method" defaultValue="cash" aria-label="Received as" className={`${cell} h-12 w-full`}>
            {["cash", "upi", "bank", "cheque"].map((m) => <option key={m} value={m}>Received as {m.toUpperCase()}</option>)}
          </select>
          <Field label="Interest / terms (optional)" name="interest" />
          <Button type="submit" className="w-full">Save</Button>
        </form>
      </Dialog>
      <Dialog open={!!repaying} onClose={() => setRepaying(null)} title={`Repay ${repaying?.lender_name ?? ""}`}>
        <form onSubmit={repay} className="space-y-4">
          <FormError message={error} />
          <Field label="Amount ₹" name="amount" required inputMode="decimal" defaultValue={repaying?.outstanding} hint={repaying ? `${rupees(repaying.outstanding)} left` : undefined} />
          <select name="method" defaultValue="cash" aria-label="Paid by" className={`${cell} h-12 w-full`}>
            {["cash", "upi", "bank", "cheque"].map((m) => <option key={m} value={m}>Paid by {m.toUpperCase()}</option>)}
          </select>
          <Button type="submit" className="w-full">Save repayment</Button>
        </form>
      </Dialog>
    </div>
  );
}

// --- approvals ---

function ApprovalsPanel() {
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const { data } = useApprovals();
  const [busy, setBusy] = useState<string | null>(null);
  async function decide(id: string, approve: boolean) {
    setBusy(id);
    try {
      await api(`/approvals/${id}/${approve ? "approve" : "reject"}`, { method: "POST", json: {} });
      for (const k of ["approvals", "cash", "customers", "customer", "invoices", "credit-notes"]) void qc.invalidateQueries({ queryKey: [k] });
      toast(approve ? "Approved" : "Rejected");
    } catch (e2) { toast(err(e2, "Couldn't save.")); } finally { setBusy(null); }
  }
  if (!data) return <p className="text-text-2">Loading…</p>;
  if (!data.length) return <p className="rounded-xl border border-dashed border-border-strong bg-surface p-8 text-center text-text-2">Nothing waiting. Collections, returns and day closes by salespeople show up here.</p>;
  const KIND = { collection: "Collection", return: "Return", cash_close: "Day close" } as const;
  return (
    <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
      {data.map((a) => (
        <li key={a.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="font-medium"><Badge tone="brand">{KIND[a.kind]}</Badge> {a.summary}</p>
            <p className="text-sm text-text-2">{[a.requested_by_name, dayTime(a.created_at)].filter(Boolean).join(" · ")}</p>
          </div>
          <Button size="md" variant="ghost" disabled={busy === a.id} onClick={() => void decide(a.id, false)}><X className="h-4 w-4" aria-hidden />Reject</Button>
          <Button size="md" loading={busy === a.id} onClick={() => void decide(a.id, true)}><Check className="h-4 w-4" aria-hidden />Approve</Button>
        </li>
      ))}
    </ul>
  );
}

import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, MessageCircle, Plus, Search, Users } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { Badge, Dialog, PageHeader, useToast } from "@/ui/primitives";
import { cell, day, dayTime, newKey, useCustomer, type CollectionReceipt, type Customer, type CustomerPage, type Ledger } from "./api";

const rupees = (v: string) => formatINR(v, { always: true });

function BalanceBadge({ balance }: { balance: string }) {
  const b = Number(balance);
  if (b > 0) return <Badge tone="warning">Due {rupees(balance)}</Badge>;
  if (b < 0) return <Badge tone="success">Credit {rupees(String(-b))}</Badge>;
  return null;
}

export function CustomersPage() {
  const [q, setQ] = useState("");
  const [due, setDue] = useState(false);
  const [adding, setAdding] = useState(false);
  const params = new URLSearchParams({ ...(q.trim() ? { q: q.trim() } : {}), ...(due ? { has_due: "true" } : {}), limit: "100" });
  const { data, isLoading } = useQuery({ queryKey: ["customers", params.toString()], queryFn: () => api<CustomerPage>(`/customers?${params}`), placeholderData: keepPreviousData });
  return (
    <>
      <PageHeader title="Customers" description={data ? `${data.total} customers · ${rupees(data.due_total)} to collect` : undefined}
        action={<Button size="md" onClick={() => setAdding(true)}><Plus className="h-4 w-4" aria-hidden />Add customer</Button>} />
      <div className="mb-4 flex flex-wrap gap-3">
        <label className="relative min-w-[200px] flex-1">
          <span className="sr-only">Search customers</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-text-3" aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, mobile or GSTIN" className={`${cell} w-full pl-10`} />
        </label>
        <button onClick={() => setDue(!due)} aria-pressed={due} className={`h-11 rounded-lg border px-4 font-medium ${due ? "border-warning-fill bg-warning-soft text-warning" : "border-border-strong bg-surface"}`}>Has due</button>
      </div>
      {isLoading ? <p className="text-text-2">Loading…</p> : !data?.items.length ? (
        <div className="rounded-xl border border-dashed border-border-strong bg-surface p-10 text-center text-text-2">
          <Users className="mx-auto h-8 w-8 text-text-3" aria-hidden />
          <p className="mt-3">{q || due ? "No customers match." : "Customers are added when you save a bill with their mobile number."}</p>
        </div>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
          {data.items.map((c) => (
            <li key={c.id}>
              <Link to={`/app/customers/${c.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-surface-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{c.name || c.phone}</p>
                  <p className="truncate text-sm text-text-2">{[c.name ? c.phone : null, c.bills ? `${c.bills} bill${c.bills === 1 ? "" : "s"}` : null, c.last_visit ? `last ${day(c.last_visit)}` : null].filter(Boolean).join(" · ")}</p>
                </div>
                <BalanceBadge balance={c.balance} />
              </Link>
            </li>
          ))}
        </ul>
      )}
      <Dialog open={adding} onClose={() => setAdding(false)} title="Add customer"><CustomerForm onDone={() => setAdding(false)} /></Dialog>
    </>
  );
}

function CustomerForm({ customer, onDone }: { customer?: Customer; onDone: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast((s) => s.show);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const v = (k: string) => String(f.get(k) ?? "").trim() || null;
    const body = {
      name: v("name"), phone: v("phone"), gstin: v("gstin"), billing_address: v("address"), email: v("email"),
      credit_limit: v("credit_limit"), opening_balance: v("opening_balance") ?? "0", notes: v("notes"), tags: customer?.tags ?? [],
    };
    setBusy(true); setError(null);
    try {
      const saved = await api<Customer>(customer ? `/customers/${customer.id}` : "/customers", { method: customer ? "PUT" : "POST", json: body });
      await qc.invalidateQueries({ queryKey: ["customers"] }); await qc.invalidateQueries({ queryKey: ["customer", saved.id] });
      toast(customer ? "Customer updated" : "Customer added"); onDone();
      if (!customer) navigate(`/app/customers/${saved.id}`);
    } catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't save."); } finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <FormError message={error} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" name="name" defaultValue={customer?.name ?? ""} />
        <Field label="Mobile" name="phone" inputMode="numeric" maxLength={10} defaultValue={customer?.phone ?? ""} />
        <Field label="GSTIN (business customers)" name="gstin" defaultValue={customer?.gstin ?? ""} className="uppercase" />
        <Field label="Email" name="email" type="email" defaultValue={customer?.email ?? ""} />
      </div>
      <Field label="Billing address" name="address" defaultValue={customer?.billing_address ?? ""} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Credit limit ₹" name="credit_limit" inputMode="decimal" defaultValue={customer?.credit_limit ?? ""} hint="Leave empty for no limit. Salespeople can't go past it." />
        <Field label="Old dues ₹ (opening balance)" name="opening_balance" inputMode="decimal" defaultValue={customer?.opening_balance ?? ""} hint="Money they owed before Anylo." />
      </div>
      <Field label="Notes" name="notes" defaultValue={customer?.notes ?? ""} />
      <Button type="submit" className="w-full" loading={busy}>Save</Button>
    </form>
  );
}

const KIND: Record<string, string> = { bill: "Bill", paid_at_bill: "Paid at bill", payment: "Payment", return: "Return", refund: "Refund" };

export function CustomerDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const can = useAuth((s) => s.can);
  const shopName = useAuth((s) => s.me?.shops.find((x) => x.id === s.me?.active_shop_id)?.name ?? "");
  const { data: c, isLoading } = useCustomer(id);
  const ledger = useQuery({ queryKey: ["ledger", id], queryFn: () => api<Ledger>(`/customers/${id}/ledger`), enabled: !!id && can("customer.manage") });
  const [collecting, setCollecting] = useState(false);
  const [editing, setEditing] = useState(false);
  if (isLoading || !c) return <p className="text-text-2">Loading…</p>;
  const balance = Number(c.balance);
  const remind = `https://wa.me/91${c.phone}?text=${encodeURIComponent(`Hello ${c.name ?? ""}, a gentle reminder from ${shopName}: ${rupees(c.balance)} is pending. Thank you!`)}`;
  async function remove() {
    try { await api(`/customers/${id}`, { method: "DELETE" }); await qc.invalidateQueries({ queryKey: ["customers"] }); toast("Customer removed"); navigate("/app/customers"); }
    catch (err) { toast(err instanceof ApiError ? err.message : "Couldn't remove."); }
  }
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <button onClick={() => navigate(-1)} className="inline-flex items-center gap-2 text-sm font-semibold text-text-2 hover:text-text"><ArrowLeft className="h-4 w-4" aria-hidden />Back</button>
      <div className="rounded-xl border border-border bg-surface p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">{c.name || c.phone}</h1>
            <p className="tnum text-text-2">{[c.name ? c.phone : null, c.gstin].filter(Boolean).join(" · ")}</p>
          </div>
          <div className="text-right">
            <p className="text-sm text-text-2">{balance < 0 ? "Store credit" : "Balance due"}</p>
            <p className={`tnum text-3xl font-bold ${balance > 0 ? "text-warning" : balance < 0 ? "text-success" : ""}`}>{rupees(String(Math.abs(balance)))}</p>
            {c.credit_limit && <p className="text-xs text-text-2">Limit {rupees(c.credit_limit)}</p>}
          </div>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
          <div><p className="text-text-2">Bills</p><p className="tnum font-semibold">{c.bills ?? 0}</p></div>
          <div><p className="text-text-2">Total bought</p><p className="tnum font-semibold">{rupees(c.spent ?? "0")}</p></div>
          <div><p className="text-text-2">Last visit</p><p className="font-semibold">{c.last_visit ? day(c.last_visit) : "—"}</p></div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          {balance > 0 && can("payment.collect") && <Button size="md" onClick={() => setCollecting(true)}>Collect payment</Button>}
          {balance > 0 && c.phone && <a href={remind} target="_blank" rel="noopener" className="inline-flex h-10 items-center gap-2 rounded-lg border border-border-strong px-4 text-sm font-semibold hover:bg-surface-2"><MessageCircle className="h-4 w-4" aria-hidden />Remind on WhatsApp</a>}
          {can("customer.manage") && <Button size="md" variant="secondary" onClick={() => setEditing(true)}>Edit</Button>}
          {can("customer.manage") && balance === 0 && <Button size="md" variant="ghost" onClick={() => void remove()}>Remove</Button>}
        </div>
      </div>
      {ledger.data && (
        <section aria-label="Statement">
          <h2 className="mb-2 font-semibold">Statement</h2>
          <div className="overflow-x-auto rounded-xl border border-border bg-surface">
            <table className="w-full text-sm">
              <thead className="text-left text-text-2"><tr className="border-b border-border">
                <th className="px-4 py-2.5 font-medium">Date</th><th className="px-4 py-2.5 font-medium">Entry</th>
                <th className="px-4 py-2.5 text-right font-medium">Bought</th><th className="px-4 py-2.5 text-right font-medium">Paid / returned</th><th className="px-4 py-2.5 text-right font-medium">Balance</th>
              </tr></thead>
              <tbody className="tnum divide-y divide-border">
                {Number(ledger.data.opening_balance) !== 0 && (
                  <tr><td className="px-4 py-2.5 text-text-2">—</td><td className="px-4 py-2.5">Old dues</td><td /><td /><td className="px-4 py-2.5 text-right">{rupees(ledger.data.opening_balance)}</td></tr>
                )}
                {ledger.data.entries.map((e, i) => (
                  <tr key={i}>
                    <td className="whitespace-nowrap px-4 py-2.5 text-text-2">{dayTime(e.at)}</td>
                    <td className="px-4 py-2.5">{e.kind === "bill" && e.ref_id ? <Link to={`/app/sales/${e.ref_id}`} className="font-medium text-primary hover:underline">{e.ref}</Link> : <>{KIND[e.kind]}{e.ref && <span className="text-text-2"> · {e.ref}</span>}</>}</td>
                    <td className="px-4 py-2.5 text-right">{Number(e.debit) ? rupees(e.debit) : ""}</td>
                    <td className="px-4 py-2.5 text-right text-success">{Number(e.credit) ? rupees(e.credit) : ""}</td>
                    <td className="px-4 py-2.5 text-right font-medium">{rupees(e.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <Dialog open={collecting} onClose={() => setCollecting(false)} title="Collect payment"><CollectForm customer={c} onDone={() => setCollecting(false)} /></Dialog>
      <Dialog open={editing} onClose={() => setEditing(false)} title="Edit customer"><CustomerForm customer={c} onDone={() => setEditing(false)} /></Dialog>
    </div>
  );
}

function CollectForm({ customer, onDone }: { customer: Customer; onDone: () => void }) {
  const qc = useQueryClient();
  const [key] = useState(newKey); // one key per form: a double tap or retry can't record the payment twice
  const [amount, setAmount] = useState(customer.balance);
  const [method, setMethod] = useState("cash");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<CollectionReceipt | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      const r = await api<CollectionReceipt>(`/customers/${customer.id}/payments`, { method: "POST", json: { amount, method, reference: reference || null, idempotency_key: key } });
      setDone(r);
      for (const k of ["customer", "customers", "ledger", "invoices", "cash"]) void qc.invalidateQueries({ queryKey: [k] });
    } catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't save. Try again; it won't be recorded twice."); } finally { setBusy(false); }
  }
  if (done) return (
    <div className="space-y-4 text-center">
      <p className="tnum text-3xl font-bold">{rupees(done.amount)}</p>
      <p className="text-text-2">{done.receipt_no} · {done.method.toUpperCase()}</p>
      {done.status === "pending_approval"
        ? <p className="rounded-lg bg-warning-soft px-4 py-3 text-sm text-warning">Sent to the owner or manager to approve. It counts once they approve.</p>
        : <p className="text-sm text-text-2">Balance now {rupees(done.balance_after)}</p>}
      <Button className="w-full" onClick={onDone}>Done</Button>
    </div>
  );
  return (
    <form onSubmit={submit} className="space-y-4">
      <FormError message={error} />
      <Field label="Amount ₹" value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" required hint={`Due: ${rupees(customer.balance)}. Settles the oldest bills first.`} />
      <div className="grid grid-cols-5 gap-1.5" role="radiogroup" aria-label="Payment method">
        {["cash", "upi", "card", "bank", "cheque"].map((m) => (
          <button type="button" key={m} role="radio" aria-checked={method === m} onClick={() => setMethod(m)}
            className={`h-11 rounded-lg border text-sm font-semibold uppercase ${method === m ? "border-primary bg-primary-soft text-on-primary-soft" : "border-border hover:bg-surface-2"}`}>{m}</button>
        ))}
      </div>
      {method !== "cash" && <Field label="Reference (optional)" value={reference} onChange={(e) => setReference(e.target.value)} />}
      <Button type="submit" className="w-full" loading={busy}>Save payment</Button>
    </form>
  );
}

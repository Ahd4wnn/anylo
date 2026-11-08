import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Truck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, NavLink, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { cell, day, dayTime } from "@/features/money/api";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { Badge, Dialog, PageHeader, useToast } from "@/ui/primitives";
import { StockCountPanel } from "./StockCount";

const rupees = (v: string | number) => formatINR(String(v), { always: true });
const qtyFmt = (v: string) => Number(v).toLocaleString("en-IN", { maximumFractionDigits: 3 });

export interface Supplier { id: string; name: string; gstin: string | null; phone: string | null; state_code: string | null; opening_balance: string; balance: string; last_purchase?: string | null }
export interface PurchaseRow { id: string; supplier_invoice_no: string | null; supplier_invoice_date: string | null; grand_total: string; status: "draft" | "posted" | "cancelled"; created_at: string; supplier_name: string; items: number }
export interface Purchase {
  id: string; supplier_id: string; supplier_name: string; supplier_gstin: string | null; supplier_invoice_no: string | null; supplier_invoice_date: string | null;
  supply_type: string; taxable_total: string; cgst_total: string; sgst_total: string; igst_total: string; grand_total: string; paid: string;
  itc_eligible: boolean; status: PurchaseRow["status"]; notes: string | null; created_at: string; posted_at: string | null;
  lines: { variant_id: string; description: string; hsn_code: string | null; qty: string; unit_cost: string; discount: string; taxable: string; tax_rate: string; line_total: string }[];
}

export const useSuppliers = () => useQuery({ queryKey: ["suppliers"], queryFn: () => api<{ items: Supplier[]; payable: string }>("/suppliers") });

const STATUS = { draft: <Badge>Draft</Badge>, posted: <Badge tone="success">Posted</Badge>, cancelled: <Badge>Cancelled</Badge> };

export function PurchasingPage() {
  const can = useAuth((s) => s.can);
  const tabs = [
    ...(can("purchase.manage") ? [{ to: "list", label: "Purchases" }, { to: "suppliers", label: "Suppliers" }, { to: "restock", label: "Restock" }] : []),
    ...(can("stock.manage") ? [{ to: "count", label: "Stock count" }] : []),
  ];
  return (
    <>
      <PageHeader title="Purchases" description="Stock coming in, what you owe suppliers, and counting what's on the shelf." />
      <nav className="mb-6 flex gap-1 overflow-x-auto shadow-[inset_0_-1px_0_rgb(var(--border))] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" aria-label="Purchase sections">
        {tabs.map((t) => (
          <NavLink key={t.to} to={t.to} className={({ isActive }) => `whitespace-nowrap border-b-2 px-4 py-2.5 font-medium ${isActive ? "border-primary text-primary" : "border-transparent text-text-2 hover:text-text"}`}>{t.label}</NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Navigate to={tabs[0]?.to ?? "list"} replace />} />
        <Route path="list" element={<PurchaseList />} />
        <Route path="suppliers" element={<SupplierList />} />
        <Route path="restock" element={<Restock />} />
        <Route path="count/*" element={<StockCountPanel />} />
      </Routes>
    </>
  );
}

function PurchaseList() {
  const navigate = useNavigate();
  const { data } = useQuery({ queryKey: ["purchases"], queryFn: () => api<{ items: PurchaseRow[] }>("/purchases?limit=100") });
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button size="md" onClick={() => navigate("/app/purchases/new")}><Plus className="h-4 w-4" aria-hidden />New purchase</Button></div>
      {data && (data.items.length ? (
        <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
          {data.items.map((p) => (
            <li key={p.id}>
              <Link to={`/app/purchases/${p.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-surface-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{p.supplier_name}{p.supplier_invoice_no && <span className="text-text-2"> · {p.supplier_invoice_no}</span>}</p>
                  <p className="text-sm text-text-2">{dayTime(p.created_at)} · {p.items} item{p.items === 1 ? "" : "s"}</p>
                </div>
                {STATUS[p.status]}
                <p className="tnum w-28 text-right font-semibold">{rupees(p.grand_total)}</p>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <div className="rounded-xl border border-dashed border-border-strong bg-surface p-10 text-center text-text-2">
          <Truck className="mx-auto h-8 w-8 text-text-3" aria-hidden /><p className="mt-3">Enter the bills from your suppliers here. Stock goes up and your item costs stay right.</p>
        </div>
      ))}
    </div>
  );
}

export function PurchaseDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const { data: p } = useQuery({ queryKey: ["purchase", id], queryFn: () => api<Purchase>(`/purchases/${id}`) });
  const [paying, setPaying] = useState(false);
  if (!p) return <p className="text-text-2">Loading…</p>;
  async function act(path: string, json?: unknown) {
    try {
      await api(`/purchases/${id}/${path}`, { method: "POST", json });
      for (const k of ["purchase", "purchases", "suppliers", "products", "cash"]) void qc.invalidateQueries({ queryKey: [k] });
      toast(path === "post" ? "Posted. Stock is in." : "Purchase cancelled");
    } catch (e) { toast(e instanceof ApiError ? e.message : "Couldn't save."); }
  }
  const due = Number(p.grand_total) - Number(p.paid);
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between gap-3">
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-2 text-sm font-semibold text-text-2 hover:text-text"><ArrowLeft className="h-4 w-4" aria-hidden />Back</button>
        <div className="flex gap-2">
          {p.status === "draft" && <Button size="md" variant="secondary" onClick={() => navigate(`/app/purchases/new?edit=${p.id}`)}>Edit</Button>}
          {p.status === "draft" && <Button size="md" onClick={() => void act("post", [])}>Post</Button>}
          {p.status === "posted" && due > 0 && <Button size="md" onClick={() => setPaying(true)}>Pay supplier</Button>}
          {p.status !== "cancelled" && <Button size="md" variant="ghost" onClick={() => void act("cancel")}>Cancel</Button>}
        </div>
      </div>
      <article className="rounded-xl border border-border bg-surface p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-lg font-bold">{p.supplier_name}</p>
            <p className="text-sm text-text-2">{[p.supplier_gstin, p.supplier_invoice_no && `Bill ${p.supplier_invoice_no}`, p.supplier_invoice_date && day(p.supplier_invoice_date)].filter(Boolean).join(" · ")}</p>
          </div>
          <div className="text-right">{STATUS[p.status]}<p className="mt-1 text-sm text-text-2">{p.itc_eligible ? "GST claimable (ITC)" : "No ITC"}</p></div>
        </div>
        <table className="mt-4 w-full text-sm">
          <thead className="text-left text-text-2"><tr className="border-b border-border"><th className="py-2 font-medium">Item</th><th className="py-2 text-right font-medium">Qty</th><th className="py-2 text-right font-medium">Rate</th><th className="py-2 text-right font-medium">GST</th><th className="py-2 text-right font-medium">Amount</th></tr></thead>
          <tbody className="tnum divide-y divide-border">
            {p.lines.map((l, i) => (
              <tr key={i}><td className="py-2">{l.description}</td><td className="py-2 text-right">{qtyFmt(l.qty)}</td><td className="py-2 text-right">{rupees(l.unit_cost)}</td><td className="py-2 text-right">{Number(l.tax_rate)}%</td><td className="py-2 text-right">{rupees(l.line_total)}</td></tr>
            ))}
          </tbody>
        </table>
        <dl className="tnum ml-auto mt-4 max-w-xs space-y-1 text-sm">
          <div className="flex justify-between text-text-2"><dt>Taxable</dt><dd>{rupees(p.taxable_total)}</dd></div>
          {p.supply_type === "inter" ? <div className="flex justify-between text-text-2"><dt>IGST</dt><dd>{rupees(p.igst_total)}</dd></div>
            : <><div className="flex justify-between text-text-2"><dt>CGST</dt><dd>{rupees(p.cgst_total)}</dd></div><div className="flex justify-between text-text-2"><dt>SGST</dt><dd>{rupees(p.sgst_total)}</dd></div></>}
          <div className="flex justify-between border-t border-border pt-1 text-base font-bold"><dt>Total</dt><dd>{rupees(p.grand_total)}</dd></div>
          {p.status === "posted" && <div className="flex justify-between text-text-2"><dt>Paid</dt><dd>{rupees(p.paid)}</dd></div>}
        </dl>
      </article>
      {paying && <PaySupplierDialog supplierId={p.supplier_id} name={p.supplier_name} owed={String(due)} onClose={() => setPaying(false)} />}
    </div>
  );
}

function PaySupplierDialog({ supplierId, name, owed, onClose }: { supplierId: string; name: string; owed: string; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await api(`/suppliers/${supplierId}/payments`, { method: "POST", json: { amount: f.get("amount"), method: f.get("method"), reference: String(f.get("ref") || "") || null } });
      for (const k of ["suppliers", "supplier-ledger", "purchase", "cash"]) void qc.invalidateQueries({ queryKey: [k] });
      toast(`Paid ${name}`); onClose();
    } catch (e2) { setError(e2 instanceof ApiError ? e2.message : "Couldn't save."); }
  }
  return (
    <Dialog open onClose={onClose} title={`Pay ${name}`}>
      <form onSubmit={submit} className="space-y-4">
        <FormError message={error} />
        <Field label="Amount ₹" name="amount" required inputMode="decimal" defaultValue={Number(owed).toFixed(2)} hint={`You owe ${rupees(owed)}`} />
        <select name="method" defaultValue="cash" aria-label="Paid by" className={`${cell} h-12 w-full`}>
          {["cash", "upi", "bank", "cheque"].map((m) => <option key={m} value={m}>Paid by {m.toUpperCase()}</option>)}
        </select>
        <Field label="Reference (optional)" name="ref" />
        <Button type="submit" className="w-full">Save payment</Button>
      </form>
    </Dialog>
  );
}

export function SupplierForm({ supplier, onDone }: { supplier?: Supplier; onDone: (s: Supplier) => void }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); e.stopPropagation();
    const f = new FormData(e.currentTarget);
    const v = (k: string) => String(f.get(k) ?? "").trim() || null;
    try {
      const s = await api<Supplier>(supplier ? `/suppliers/${supplier.id}` : "/suppliers", { method: supplier ? "PUT" : "POST", json: {
        name: v("name"), gstin: v("gstin"), phone: v("phone"), address: v("address"), opening_balance: v("opening") ?? "0",
      } });
      void qc.invalidateQueries({ queryKey: ["suppliers"] }); onDone(s);
    } catch (e2) { setError(e2 instanceof ApiError ? e2.message : "Couldn't save."); }
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <FormError message={error} />
      <Field label="Supplier name" name="name" required defaultValue={supplier?.name} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="GSTIN (optional)" name="gstin" defaultValue={supplier?.gstin ?? ""} className="uppercase" hint="Their state comes from the GSTIN." />
        <Field label="Mobile (optional)" name="phone" defaultValue={supplier?.phone ?? ""} />
      </div>
      <Field label="Address (optional)" name="address" />
      <Field label="You already owe them ₹ (optional)" name="opening" inputMode="decimal" defaultValue={supplier?.opening_balance ?? ""} />
      <Button type="submit" className="w-full">Save supplier</Button>
    </form>
  );
}

interface SupplierLedger { entries: { at: string; kind: string; ref: string; added: string; paid: string; balance: string }[]; balance: string; opening_balance: string }

function SupplierList() {
  const { data } = useSuppliers();
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<Supplier | null>(null);
  const [paying, setPaying] = useState<Supplier | null>(null);
  const ledger = useQuery({ queryKey: ["supplier-ledger", open?.id], queryFn: () => api<SupplierLedger>(`/suppliers/${open!.id}/ledger`), enabled: !!open });
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        {data && <p className="font-semibold">You owe suppliers {rupees(data.payable)}</p>}
        <Button size="md" onClick={() => setAdding(true)}><Plus className="h-4 w-4" aria-hidden />Add supplier</Button>
      </div>
      {data && (data.items.length ? (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
          {data.items.map((s) => (
            <li key={s.id} className="flex items-center gap-3 px-4 py-3">
              <button onClick={() => setOpen(s)} className="min-w-0 flex-1 text-left">
                <p className="font-medium">{s.name}</p>
                <p className="truncate text-sm text-text-2">{[s.gstin, s.phone, s.last_purchase && `last bill ${day(s.last_purchase)}`].filter(Boolean).join(" · ")}</p>
              </button>
              {Number(s.balance) > 0 && <><Badge tone="warning">Owe {rupees(s.balance)}</Badge><Button size="md" variant="secondary" onClick={() => setPaying(s)}>Pay</Button></>}
            </li>
          ))}
        </ul>
      ) : <p className="rounded-xl border border-dashed border-border-strong bg-surface p-8 text-center text-text-2">Add the wholesalers and distributors you buy from.</p>)}
      <Dialog open={adding} onClose={() => setAdding(false)} title="Add supplier"><SupplierForm onDone={() => setAdding(false)} /></Dialog>
      {paying && <PaySupplierDialog supplierId={paying.id} name={paying.name} owed={paying.balance} onClose={() => setPaying(null)} />}
      <Dialog open={!!open} onClose={() => setOpen(null)} title={open?.name ?? ""}>
        {ledger.data && (
          <ul className="tnum divide-y divide-border text-sm">
            {Number(ledger.data.opening_balance) !== 0 && <li className="flex justify-between py-2"><span>Old balance</span><span>{rupees(ledger.data.opening_balance)}</span></li>}
            {ledger.data.entries.map((e, i) => (
              <li key={i} className="flex justify-between gap-3 py-2">
                <span>{day(e.at)} · {e.kind === "purchase" ? `Bill ${e.ref}` : `Paid ${e.ref}`}</span>
                <span className={e.kind === "payment" ? "text-success" : ""}>{e.kind === "payment" ? `−${rupees(e.paid)}` : rupees(e.added)}</span>
              </li>
            ))}
            <li className="flex justify-between py-2 font-semibold"><span>You owe now</span><span>{rupees(ledger.data.balance)}</span></li>
          </ul>
        )}
      </Dialog>
    </div>
  );
}

interface Suggestion { variant_id: string; name: string; variant_name: string | null; stock_qty: string; reorder_level: string; cost_price: string; suggested_qty: string }

function Restock() {
  const navigate = useNavigate();
  const { data } = useQuery({ queryKey: ["restock"], queryFn: () => api<Suggestion[]>("/purchases/restock") });
  if (!data) return <p className="text-text-2">Loading…</p>;
  if (!data.length) return <p className="rounded-xl border border-dashed border-border-strong bg-surface p-8 text-center text-text-2">Nothing is below its reorder level. Set reorder levels on items to get suggestions here.</p>;
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button size="md" onClick={() => navigate("/app/purchases/new?restock=1")}>Create purchase from these</Button></div>
      <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
        {data.map((s) => (
          <li key={s.variant_id} className="flex items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1"><p className="font-medium">{s.name}{s.variant_name && ` · ${s.variant_name}`}</p><p className="text-sm text-text-2">{qtyFmt(s.stock_qty)} left · reorder at {qtyFmt(s.reorder_level)}</p></div>
            <p className="tnum font-semibold">Order {qtyFmt(s.suggested_qty)}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

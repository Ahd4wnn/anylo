import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, Receipt as ReceiptIcon, Search, ShoppingCart } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Logo } from "@/ui/Logo";
import { Badge, Dialog, PageHeader, useToast } from "@/ui/primitives";
import { useInvoice, type InvoicePage, type Receipt } from "./api";
import { ReceiptActions, UpiQr } from "./PaymentSheet";

const today = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD in local time
const when = (iso: string) => new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

export function SalesPage() {
  const navigate = useNavigate();
  const [from, setFrom] = useState(today());
  const [to, setTo] = useState(today());
  const [q, setQ] = useState("");
  const [due, setDue] = useState(false);
  const params = new URLSearchParams({ from, to, ...(q.trim() ? { q: q.trim() } : {}), ...(due ? { has_due: "true" } : {}), limit: "100" });
  const { data, isLoading } = useQuery({ queryKey: ["invoices", params.toString()], queryFn: () => api<InvoicePage>(`/invoices?${params}`), placeholderData: keepPreviousData });

  return (
    <>
      <PageHeader title="Sales" description={data ? `${data.total} bills · ${formatINR(data.sales_total, { always: true })}` : undefined}
        action={<Button size="md" onClick={() => navigate("/pos")}><ShoppingCart className="h-4 w-4" aria-hidden />New bill</Button>} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="relative min-w-[200px] flex-1">
          <span className="sr-only">Search bills</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-text-3" aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Bill number, customer name or mobile"
            className="h-11 w-full rounded-lg border border-border-strong bg-surface pl-10 pr-3" />
        </label>
        <input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} aria-label="From date" className="h-11 rounded-lg border border-border-strong bg-surface px-3" />
        <input type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} aria-label="To date" className="h-11 rounded-lg border border-border-strong bg-surface px-3" />
        <button onClick={() => setDue(!due)} aria-pressed={due} className={`h-11 rounded-lg border px-4 font-medium ${due ? "border-warning-fill bg-warning-soft text-warning" : "border-border-strong bg-surface"}`}>Has due</button>
      </div>
      {isLoading ? <p className="text-text-2">Loading…</p> : !data?.items.length ? (
        <div className="rounded-xl border border-dashed border-border-strong bg-surface p-10 text-center text-text-2">
          <ReceiptIcon className="mx-auto h-8 w-8 text-text-3" aria-hidden /><p className="mt-3">No bills for these dates.</p>
        </div>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
          {data.items.map((i) => (
            <li key={i.id}>
              <Link to={`/app/sales/${i.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-surface-2">
                <div className="min-w-0 flex-1">
                  <p className={`font-medium ${i.status === "cancelled" ? "text-text-3 line-through" : ""}`}>{i.number}</p>
                  <p className="truncate text-sm text-text-2">{[when(i.issued_at), i.buyer_name || i.buyer_phone, i.created_by_name].filter(Boolean).join(" · ")}</p>
                </div>
                <div className="hidden gap-1.5 sm:flex">
                  {i.status === "cancelled" && <Badge>Cancelled</Badge>}
                  {Number(i.due_total) > 0 && i.status === "issued" && <Badge tone="warning">Due {formatINR(i.due_total)}</Badge>}
                  {i.methods.map((m) => <Badge key={m} tone="brand">{m.toUpperCase()}</Badge>)}
                </div>
                <p className="tnum w-28 text-right font-semibold">{formatINR(i.grand_total, { always: true })}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** On-screen copy of the receipt; also used for the public link. */
export function ReceiptView({ r }: { r: Receipt }) {
  const t = r.totals;
  const reg = r.tax_summary.length > 0;
  return (
    <article className="rounded-xl border border-border bg-surface p-5 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex gap-3">
          {r.shop.logo_url && <img src={r.shop.logo_url} alt="" className="h-14 w-14 rounded-lg object-contain" />}
          <div>
            <p className="text-lg font-bold">{r.shop.name}</p>
            <p className="text-sm text-text-2">{r.shop.address}</p>
            {r.shop.gstin && <p className="text-sm text-text-2">GSTIN {r.shop.gstin}</p>}
          </div>
        </div>
        <div className="text-right">
          <p className="font-bold tracking-wide">{r.title}</p>
          <p className="tnum">{r.number}</p>
          <p className="text-sm text-text-2">{new Date(r.issued_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</p>
          {r.status === "cancelled" && <Badge>Cancelled</Badge>}
        </div>
      </div>
      {r.composition_note && <p className="mt-3 text-sm text-text-2">{r.composition_note}</p>}
      <div className="mt-4 grid gap-3 rounded-lg bg-surface-2 p-4 text-sm sm:grid-cols-2">
        <div><p className="text-text-2">Bill to</p><p className="font-medium">{r.buyer?.name || r.buyer?.phone || "Walk-in customer"}</p>
          {r.buyer?.gstin && <p className="text-text-2">GSTIN {r.buyer.gstin}</p>}</div>
        <div><p className="text-text-2">Place of supply</p><p className="font-medium">{r.place_of_supply}</p></div>
      </div>
      <table className="mt-4 w-full text-sm">
        <thead><tr className="border-b border-border text-left text-text-2"><th className="py-2 font-medium">Item</th><th className="text-right font-medium">Qty</th><th className="text-right font-medium">Rate</th>{reg && <th className="text-right font-medium">GST</th>}<th className="text-right font-medium">Amount</th></tr></thead>
        <tbody className="divide-y divide-border">
          {r.lines.map((l, i) => (
            <tr key={i}><td className="py-2.5">{l.name}{l.variant_name && <span className="text-text-2"> · {l.variant_name}</span>}{l.hsn && <span className="block text-xs text-text-3">HSN {l.hsn}</span>}</td>
              <td className="tnum text-right">{Number(l.qty).toLocaleString("en-IN")} {l.unit.toLowerCase()}</td>
              <td className="tnum text-right">{formatINR(l.unit_price, { always: true })}</td>
              {reg && <td className="tnum text-right">{Number(l.tax_rate)}%</td>}
              <td className="tnum text-right font-medium">{formatINR(l.line_total, { always: true })}</td></tr>
          ))}
        </tbody>
      </table>
      <dl className="tnum ml-auto mt-4 max-w-xs space-y-1 text-sm">
        {Number(t.discount_total) > 0 && <div className="flex justify-between"><dt className="text-text-2">Discount</dt><dd>−{formatINR(t.discount_total, { always: true })}</dd></div>}
        {reg && <div className="flex justify-between"><dt className="text-text-2">Taxable</dt><dd>{formatINR(t.taxable_total, { always: true })}</dd></div>}
        {reg && (r.supply_type === "inter"
          ? <div className="flex justify-between"><dt className="text-text-2">IGST</dt><dd>{formatINR(t.igst_total, { always: true })}</dd></div>
          : <><div className="flex justify-between"><dt className="text-text-2">CGST</dt><dd>{formatINR(t.cgst_total, { always: true })}</dd></div>
            <div className="flex justify-between"><dt className="text-text-2">{r.state_tax_label}</dt><dd>{formatINR(t.sgst_total, { always: true })}</dd></div></>)}
        {Number(t.round_off) !== 0 && <div className="flex justify-between"><dt className="text-text-2">Round off</dt><dd>{t.round_off}</dd></div>}
        <div className="flex justify-between border-t border-border pt-2 text-lg font-bold"><dt>Total</dt><dd>{formatINR(t.grand_total, { always: true })}</dd></div>
        {r.payments.map((p, i) => <div key={i} className="flex justify-between text-text-2"><dt>Paid · {p.method.toUpperCase()}</dt><dd>{formatINR(p.amount, { always: true })}</dd></div>)}
        {Number(t.due_total) > 0 && <div className="flex justify-between font-semibold text-warning"><dt>Balance due</dt><dd>{formatINR(t.due_total, { always: true })}</dd></div>}
      </dl>
      <p className="mt-3 text-sm text-text-2">{r.amount_in_words}</p>
      {r.upi_due_uri && <div className="mt-4 flex items-center gap-4 rounded-lg bg-tint p-4"><UpiQr uri={r.upi_due_uri} size={120} /><p className="text-sm">Scan with any UPI app to pay the balance of <span className="tnum font-semibold">{formatINR(t.due_total, { always: true })}</span>.</p></div>}
      {r.remarks && <p className="mt-3 text-sm">Note: {r.remarks}</p>}
    </article>
  );
}

export function InvoiceDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast((s) => s.show);
  const qc = useQueryClient();
  const canCancel = useAuth((s) => s.can("invoice.cancel"));
  const { data: r, isLoading } = useInvoice(id);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function cancel(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    try {
      await api(`/invoices/${id}/cancel`, { method: "POST", json: { reason: new FormData(e.currentTarget).get("reason") } });
      await qc.invalidateQueries({ queryKey: ["invoice", id] }); await qc.invalidateQueries({ queryKey: ["invoices"] });
      setCancelling(false); toast("Bill cancelled. Stock was put back.");
    } catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't cancel."); }
  }
  if (isLoading || !r) return <p className="text-text-2">Loading…</p>;
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between gap-3">
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-2 text-sm font-semibold text-text-2 hover:text-text"><ArrowLeft className="h-4 w-4" aria-hidden />Back</button>
        {canCancel && r.status === "issued" && <Button variant="ghost" size="md" onClick={() => setCancelling(true)}>Cancel bill</Button>}
      </div>
      {r.status === "issued" && <ReceiptActions r={r} />}
      {r.cancel_reason && <p className="rounded-lg bg-surface-2 px-4 py-3 text-sm text-text-2">Cancelled: {r.cancel_reason}</p>}
      <ReceiptView r={r} />
      <Dialog open={cancelling} onClose={() => setCancelling(false)} title={`Cancel ${r.number}?`}>
        <form onSubmit={cancel} className="space-y-4">
          <p className="text-text-2">The number stays in your records as cancelled and the stock goes back. Bills can only be cancelled on the day they were made; after that use a return.</p>
          <FormError message={error} />
          <input name="reason" required minLength={3} placeholder="Reason" aria-label="Reason" className="h-12 w-full rounded-lg border border-border-strong bg-surface px-3" />
          <Button type="submit" variant="danger" className="w-full">Cancel bill</Button>
        </form>
      </Dialog>
    </div>
  );
}

/** Customer-facing bill at /i/:token. No login. */
export function PublicInvoicePage() {
  const { token } = useParams();
  const { data: r, isError } = useQuery({ queryKey: ["public", token], queryFn: () => api<Receipt>(`/public/invoices/${token}`) });
  return (
    <div className="min-h-dvh bg-bg px-4 py-6">
      <div className="mx-auto max-w-3xl space-y-4">
        <div className="flex items-center justify-between"><Logo size={28} />
          {r && <a href={`${import.meta.env.VITE_API_BASE_URL ?? "/v1"}/public/invoices/${token}/pdf`} className="inline-flex h-10 items-center gap-2 rounded-lg border border-border-strong bg-surface px-4 text-sm font-semibold"><Download className="h-4 w-4" aria-hidden />Download PDF</a>}
        </div>
        {isError ? <p className="rounded-xl bg-surface p-8 text-center text-text-2">This bill link isn't valid.</p> : r ? <ReceiptView r={r} /> : <p className="text-text-2">Loading…</p>}
        <p className="text-center text-sm text-text-3">Made with Anylo · Bill anything. Sell anything. Run everything.</p>
      </div>
    </div>
  );
}

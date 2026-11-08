import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useProducts, type Product } from "@/features/items/api";
import { cell, newKey, todayIso } from "@/features/money/api";
import { useHidScanner } from "@/features/pos/inputs";
import { useShop } from "@/features/shop/api";
import { computeInvoice } from "@/lib/gst";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Dialog, Toggle, useToast } from "@/ui/primitives";
import { SupplierForm, useSuppliers, type Purchase } from "./PurchasingPages";

interface Line { variantId: string; name: string; qty: string; cost: string; discount: string; rate: string }
const rupees = (v: string | number) => formatINR(String(v), { always: true });

export function PurchaseEditor() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const [params] = useSearchParams();
  const editId = params.get("edit");
  const { data: shop } = useShop();
  const suppliers = useSuppliers();
  const [key] = useState(newKey);
  const [supplierId, setSupplierId] = useState("");
  const [billNo, setBillNo] = useState("");
  const [billDate, setBillDate] = useState(todayIso());
  const [itc, setItc] = useState(true);
  const [lines, setLines] = useState<Line[]>([]);
  const [paidNow, setPaidNow] = useState("");
  const [method, setMethod] = useState("cash");
  const [q, setQ] = useState("");
  const [addingSupplier, setAddingSupplier] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const found = useProducts({ q: q.trim() || undefined });

  const fromProduct = (p: Product, v = p.variants[0]): Line => ({
    variantId: v.id, name: p.name + (v.name ? ` · ${v.name}` : ""), qty: "1", cost: Number(v.cost_price) ? v.cost_price : "", discount: "", rate: p.tax_rate ?? "0",
  });
  const add = (l: Line) => setLines((ls) => ls.some((x) => x.variantId === l.variantId)
    ? ls.map((x) => (x.variantId === l.variantId ? { ...x, qty: String(Number(x.qty) + 1) } : x)) : [...ls, l]);

  // Prefill: editing a draft, or ordering everything below its reorder level.
  const draft = useQuery({ queryKey: ["purchase", editId], queryFn: () => api<Purchase>(`/purchases/${editId}`), enabled: !!editId });
  const restock = useQuery({ queryKey: ["restock"], queryFn: () => api<{ variant_id: string; name: string; variant_name: string | null; cost_price: string; tax_rate: string; suggested_qty: string }[]>("/purchases/restock"), enabled: params.get("restock") === "1" });
  useEffect(() => {
    const d = draft.data;
    if (!d) return;
    setSupplierId(d.supplier_id); setBillNo(d.supplier_invoice_no ?? ""); setBillDate(d.supplier_invoice_date ?? todayIso()); setItc(d.itc_eligible);
    setLines(d.lines.map((l) => ({ variantId: l.variant_id, name: l.description, qty: String(Number(l.qty)), cost: l.unit_cost, discount: Number(l.discount) ? l.discount : "", rate: l.tax_rate })));
  }, [draft.data]);
  useEffect(() => {
    if (restock.data) setLines(restock.data.map((s) => ({ variantId: s.variant_id, name: s.name + (s.variant_name ? ` · ${s.variant_name}` : ""), qty: String(Number(s.suggested_qty)), cost: Number(s.cost_price) ? s.cost_price : "", discount: "", rate: s.tax_rate })));
  }, [restock.data]);

  async function addCode(code: string) {
    try { const r = await api<{ product: Product; variant: Product["variants"][number] }>(`/products/lookup?code=${encodeURIComponent(code)}`); add(fromProduct(r.product, r.variant)); }
    catch { toast(`No item has barcode ${code}`); }
  }
  useHidScanner((code) => void addCode(code));

  const supplier = suppliers.data?.items.find((s) => s.id === supplierId);
  const inter = !!supplier?.state_code && !!shop && supplier.state_code !== shop.state_code;
  const ready = lines.length > 0 && lines.every((l) => Number(l.qty) > 0 && l.cost !== "" && Number(l.cost) >= 0);
  // Display only: the server prices the bill with the GST engine.
  const totals = useMemo(() => {
    if (!ready) return null;
    try {
      return computeInvoice({ lines: lines.map((l) => ({ qty: l.qty, unitPrice: l.cost, rate: l.rate, priceIncludesTax: false, lineDiscount: l.discount || "0" })), supplyType: inter ? "inter" : "intra", roundOff: false });
    } catch { return null; }
  }, [lines, inter, ready]);

  async function save(post: boolean) {
    setBusy(true); setError(null);
    const body = {
      supplier_id: supplierId, supplier_invoice_no: billNo.trim() || null, supplier_invoice_date: billDate || null, itc_eligible: itc, post,
      lines: lines.map((l) => ({ variant_id: l.variantId, qty: l.qty, unit_cost: l.cost, discount: l.discount || "0" })),
      paid: post && Number(paidNow) > 0 ? [{ method, amount: paidNow }] : [], idempotency_key: key,
    };
    try {
      const p = await api<Purchase>(editId ? `/purchases/${editId}` : "/purchases", { method: editId ? "PUT" : "POST", json: body });
      for (const k of ["purchases", "purchase", "suppliers", "products", "restock", "cash"]) void qc.invalidateQueries({ queryKey: [k] });
      toast(post ? "Posted. Stock is in and costs are updated." : "Saved as draft");
      navigate(`/app/purchases/${p.id}`, { replace: true });
    } catch (e) { setError(e instanceof ApiError ? e.message : "Couldn't save the purchase."); } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <button onClick={() => navigate(-1)} className="inline-flex items-center gap-2 text-sm font-semibold text-text-2 hover:text-text"><ArrowLeft className="h-4 w-4" aria-hidden />Back</button>
      <h1 className="text-2xl font-bold">{editId ? "Edit purchase" : "New purchase"}</h1>
      <FormError message={error} />
      <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
        <div className="flex gap-2">
          <select value={supplierId} onChange={(e) => setSupplierId(e.target.value)} aria-label="Supplier" className={`${cell} h-12 flex-1`}>
            <option value="" disabled>Choose supplier</option>
            {suppliers.data?.items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <Button variant="secondary" size="md" className="h-12" onClick={() => setAddingSupplier(true)}>New</Button>
        </div>
        <input value={billNo} onChange={(e) => setBillNo(e.target.value)} placeholder="Their bill no." aria-label="Supplier bill number" className={`${cell} h-12`} />
        <input type="date" value={billDate} max={todayIso()} onChange={(e) => setBillDate(e.target.value)} aria-label="Bill date" className={`${cell} h-12`} />
      </div>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-text-3" aria-hidden />
        <input value={q} onChange={(e) => setQ(e.target.value)} data-scan-target="1" placeholder="Search or scan items to add" aria-label="Search items" className={`${cell} h-12 w-full pl-10`} />
        {q.trim() && found.data && (
          <ul className="absolute z-10 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-border bg-surface shadow-e2">
            {found.data.items.flatMap((p) => p.variants.map((v) => (
              <li key={v.id}><button onClick={() => { add(fromProduct(p, v)); setQ(""); }} className="flex w-full justify-between px-3 py-2.5 text-left hover:bg-surface-2">
                <span>{p.name}{v.name ? ` · ${v.name}` : ""}</span><span className="tnum text-sm text-text-2">cost {rupees(v.cost_price)}</span>
              </button></li>
            )))}
            {!found.data.items.length && <li className="px-3 py-2.5 text-text-2">No items. Add it in Items first.</li>}
          </ul>
        )}
      </div>
      {lines.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface">
          <table className="w-full text-sm">
            <thead className="text-left text-text-2"><tr className="border-b border-border">
              <th className="px-3 py-2 font-medium">Item</th><th className="px-3 py-2 font-medium">Qty</th><th className="px-3 py-2 font-medium">Rate before GST ₹</th>
              <th className="px-3 py-2 font-medium">Discount ₹</th><th className="px-3 py-2 text-right font-medium">GST</th><th />
            </tr></thead>
            <tbody className="divide-y divide-border">
              {lines.map((l, i) => {
                const set = (patch: Partial<Line>) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, ...patch } : x)));
                const num = (v: string) => v.replace(/[^\d.]/g, "");
                return (
                  <tr key={l.variantId}>
                    <td className="px-3 py-2 font-medium">{l.name}</td>
                    <td className="px-3 py-2"><input value={l.qty} onChange={(e) => set({ qty: num(e.target.value) })} inputMode="decimal" aria-label={`Quantity of ${l.name}`} className={`${cell} tnum w-20`} /></td>
                    <td className="px-3 py-2"><input value={l.cost} onChange={(e) => set({ cost: num(e.target.value) })} inputMode="decimal" aria-label={`Rate of ${l.name}`} className={`${cell} tnum w-28`} /></td>
                    <td className="px-3 py-2"><input value={l.discount} onChange={(e) => set({ discount: num(e.target.value) })} inputMode="decimal" aria-label={`Discount on ${l.name}`} className={`${cell} tnum w-24`} /></td>
                    <td className="tnum px-3 py-2 text-right text-text-2">{Number(l.rate)}%</td>
                    <td className="px-2"><button onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))} className="grid h-9 w-9 place-items-center rounded-md text-text-3 hover:text-danger" aria-label={`Remove ${l.name}`}><Trash2 className="h-4 w-4" /></button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {shop?.tax.gst_scheme === "regular" && <Toggle checked={itc} onChange={setItc} label="I can claim this GST back (ITC)" hint="Turn off for bills without your GSTIN or for items you can't claim. Then the GST becomes part of the item's cost." />}
      <div className="flex flex-wrap items-end justify-between gap-4 rounded-xl border border-border bg-surface p-4">
        <dl className="tnum space-y-1 text-sm">
          {totals ? <>
            <div className="flex gap-6 text-text-2"><dt>Taxable</dt><dd>{rupees(totals.taxableTotal.toFixed(2))}</dd></div>
            <div className="flex gap-6 text-text-2"><dt>{inter ? "IGST" : "CGST + SGST"}</dt><dd>{rupees(totals.cgstTotal.plus(totals.sgstTotal).plus(totals.igstTotal).toFixed(2))}</dd></div>
            <div className="flex gap-6 text-lg font-bold"><dt>Total</dt><dd>{rupees(totals.grandTotal.toFixed(2))}</dd></div>
          </> : <p className="text-text-2">{lines.length ? "Enter the rate for every item." : "Add items from the supplier's bill."}</p>}
        </dl>
        <div className="flex flex-wrap items-center gap-2">
          <input value={paidNow} onChange={(e) => setPaidNow(e.target.value.replace(/[^\d.]/g, ""))} inputMode="decimal" placeholder="Paid now ₹ (optional)" aria-label="Paid now" className={`${cell} w-44`} />
          <select value={method} onChange={(e) => setMethod(e.target.value)} aria-label="Paid by" className={cell}>
            {["cash", "upi", "bank", "cheque"].map((m) => <option key={m} value={m}>{m.toUpperCase()}</option>)}
          </select>
          <Button variant="secondary" size="md" disabled={!supplierId || !ready} loading={busy} onClick={() => void save(false)}>Save draft</Button>
          <Button size="md" disabled={!supplierId || !ready} loading={busy} onClick={() => void save(true)}>Post · stock in</Button>
        </div>
      </div>
      <Dialog open={addingSupplier} onClose={() => setAddingSupplier(false)} title="Add supplier">
        <SupplierForm onDone={(s) => { setSupplierId(s.id); setAddingSupplier(false); }} />
      </Dialog>
    </div>
  );
}

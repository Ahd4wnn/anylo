import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import type { Receipt } from "@/features/pos/api";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Dialog, Toggle, useToast } from "@/ui/primitives";
import { cell, day, newKey, type CreditNoteRow } from "./api";

const qtyFmt = (v: string | number) => Number(v).toLocaleString("en-IN", { maximumFractionDigits: 3 });

/** Returns already made against a bill, shown under it. */
export function CreditNotesFor({ invoiceId }: { invoiceId: string }) {
  const { data } = useQuery({ queryKey: ["credit-notes", invoiceId], queryFn: () => api<{ items: CreditNoteRow[] }>(`/credit-notes?invoice_id=${invoiceId}`) });
  if (!data?.items.length) return null;
  return (
    <ul className="divide-y divide-border rounded-xl border border-border bg-surface text-sm" aria-label="Returns on this bill">
      {data.items.map((n) => (
        <li key={n.id} className="flex items-center justify-between gap-3 px-4 py-3">
          <span><span className="font-medium">{n.number}</span> <span className="text-text-2">· {day(n.issued_at)} · {n.refund_method === "store_credit" ? "store credit" : `refund ${n.refund_method.toUpperCase()}`}</span></span>
          <span className="tnum font-semibold">−{formatINR(n.grand_total, { always: true })}</span>
        </li>
      ))}
    </ul>
  );
}

export function ReturnDialog({ r, open, onClose }: { r: Receipt; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const [key] = useState(newKey);
  const [qty, setQty] = useState<Record<string, string>>({});
  const [refund, setRefund] = useState<"cash" | "upi" | "store_credit">("cash");
  const [restock, setRestock] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const left = (l: Receipt["lines"][number]) => Number(l.qty) - Number(l.returned_qty);
  const lines = r.lines.filter((l) => Number(qty[l.id] || 0) > 0).map((l) => ({ invoice_line_id: l.id, qty: qty[l.id] }));
  // Shown only as a guide: the server prices the credit note from the original bill's lines.
  const estimate = r.lines.reduce((s, l) => s + (Number(l.line_total) / Number(l.qty)) * Number(qty[l.id] || 0), 0);

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      const res = await api<{ number?: string; approval_required?: boolean; grand_total?: string }>("/credit-notes", {
        method: "POST", json: { invoice_id: r.id, lines, refund_method: refund, restock, idempotency_key: key },
      });
      for (const k of ["invoice", "invoices", "credit-notes", "customer", "products", "cash"]) void qc.invalidateQueries({ queryKey: [k] });
      toast(res.approval_required ? "Return sent to the owner or manager to approve" : `Return saved as ${res.number}`);
      onClose();
    } catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't save the return."); } finally { setBusy(false); }
  }

  return (
    <Dialog open={open} onClose={onClose} title={`Return items · ${r.number}`}>
      <form onSubmit={submit} className="space-y-4">
        <FormError message={error} />
        <ul className="space-y-2">
          {r.lines.map((l) => (
            <li key={l.id} className="flex items-center gap-3">
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{l.name}{l.variant_name ? ` (${l.variant_name})` : ""}</span>
                <span className="text-sm text-text-2">{qtyFmt(left(l))} of {qtyFmt(l.qty)} {l.unit.toLowerCase()} can be returned</span>
              </span>
              <input value={qty[l.id] ?? ""} onChange={(e) => setQty({ ...qty, [l.id]: e.target.value.replace(/[^\d.]/g, "") })} disabled={left(l) <= 0}
                inputMode="decimal" placeholder="0" aria-label={`Quantity of ${l.name} to return`} className={`${cell} tnum w-24 text-right`} />
            </li>
          ))}
        </ul>
        <div className="grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Refund">
          {([["cash", "Cash"], ["upi", "UPI"], ["store_credit", "Store credit"]] as const).map(([m, label]) => (
            <button type="button" key={m} role="radio" aria-checked={refund === m} onClick={() => setRefund(m)} disabled={m === "store_credit" && !r.customer_id}
              className={`h-11 rounded-lg border text-sm font-semibold disabled:opacity-40 ${refund === m ? "border-primary bg-primary-soft text-on-primary-soft" : "border-border hover:bg-surface-2"}`}>{label}</button>
          ))}
        </div>
        {Number(r.totals.due_total) > 0 && <p className="text-sm text-text-2">This bill has {formatINR(r.totals.due_total, { always: true })} unpaid. The return clears that first; only the rest is refunded.</p>}
        <Toggle checked={restock} onChange={setRestock} label="Put items back in stock" hint="Turn off for damaged or expired items." />
        <Button type="submit" className="w-full" loading={busy} disabled={!lines.length}>
          {lines.length ? `Save return · about ${formatINR(estimate.toFixed(2), { always: true })}` : "Choose items to return"}
        </Button>
      </form>
    </Dialog>
  );
}

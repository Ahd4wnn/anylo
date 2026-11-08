import { CheckCircle2, FileText, Printer, Share2 } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { usePrinter } from "@/features/printer/store";
import { useShop } from "@/features/shop/api";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Dialog, useToast } from "@/ui/primitives";
import { upiUri, type Receipt } from "./api";
import { useCart } from "./cart";
import { receiptRaster } from "./receipt";

type Mode = "cash" | "upi" | "card" | "split" | "due";
const MODES: { m: Mode; label: string }[] = [
  { m: "cash", label: "Cash" }, { m: "upi", label: "UPI" }, { m: "card", label: "Card" }, { m: "split", label: "Split" }, { m: "due", label: "Due" },
];
const n = (s: string) => (Number.isFinite(Number(s)) ? Number(s) : 0);
const r2 = (x: number) => (Math.round(x * 100) / 100).toFixed(2);

export function UpiQr({ uri, size = 200 }: { uri: string; size?: number }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => { void QRCode.toDataURL(uri, { margin: 1, width: size }).then(setSrc); }, [uri, size]);
  return src ? <img src={src} width={size} height={size} alt="UPI payment QR code" className="rounded-lg bg-white p-1" /> : <div style={{ width: size, height: size }} />;
}

/** Print through the connected thermal printer; marks the bill as handed over (it can't be edited afterwards). */
export async function printReceipt(r: Receipt) {
  const printer = usePrinter.getState();
  if (printer.status !== "connected") throw new Error("No printer connected. Connect one in Settings → Printing.");
  await printer.print(await receiptRaster(r, printer.paperDots));
  await api(`/invoices/${r.id}/handover`, { method: "POST" });
}

export async function openPdf(r: Receipt) {
  const blob = await api<Blob>(`/invoices/${r.id}/pdf`, { blob: true });
  window.open(URL.createObjectURL(blob), "_blank", "noopener");
}

export async function shareBill(r: Receipt) {
  await api(`/invoices/${r.id}/handover`, { method: "POST" });
  const text = `${r.shop.name}: ${r.title.toLowerCase()} ${r.number} for ${formatINR(r.totals.grand_total, { always: true })}. View: ${r.public_url}`;
  if (navigator.share) { await navigator.share({ title: r.number, text }).catch(() => undefined); return; }
  const phone = r.buyer?.phone ? `91${r.buyer.phone}` : "";
  window.open(`https://wa.me/${phone}?text=${encodeURIComponent(text)}`, "_blank", "noopener");
}

export function ReceiptActions({ r }: { r: Receipt }) {
  const toast = useToast((s) => s.show);
  const connected = usePrinter((s) => s.status === "connected");
  const printing = usePrinter((s) => s.printing);
  const run = (fn: () => Promise<void>, ok?: string) => async () => {
    try { await fn(); if (ok) toast(ok); } catch (e) { toast(e instanceof Error ? e.message : "Something went wrong."); }
  };
  return (
    <div className="grid grid-cols-3 gap-2">
      <Button variant="secondary" size="md" loading={printing} disabled={!connected} title={connected ? "" : "Connect a printer in Settings"} onClick={run(() => printReceipt(r), "Printed")}>
        <Printer className="h-4 w-4" aria-hidden />Print
      </Button>
      <Button variant="secondary" size="md" onClick={run(() => openPdf(r))}><FileText className="h-4 w-4" aria-hidden />PDF</Button>
      <Button variant="secondary" size="md" onClick={run(() => shareBill(r))}><Share2 className="h-4 w-4" aria-hidden />Share</Button>
    </div>
  );
}

export function PaymentSheet({ open, total, onClose, buildBody }: {
  open: boolean; total: number; onClose: () => void; buildBody: () => Record<string, unknown>;
}) {
  const cart = useCart();
  const { data: shop } = useShop();
  const printer = usePrinter();
  const [mode, setMode] = useState<Mode>("cash");
  const [received, setReceived] = useState("");
  const [split, setSplit] = useState({ cash: "", upi: "", card: "" });
  const [ref, setRef] = useState("");
  const [pin, setPin] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Receipt | null>(null);

  useEffect(() => { if (open) { setMode("cash"); setReceived(""); setSplit({ cash: "", upi: "", card: "" }); setRef(""); setError(null); setDone(null); setPin(null); } }, [open]);
  useEffect(() => { if (open && !cart.idempotencyKey) cart.set({ idempotencyKey: crypto.randomUUID() }); }, [open, cart]);

  const payments = useMemo(() => {
    if (mode === "due") return [];
    if (mode === "split") return (["cash", "upi", "card"] as const).filter((k) => n(split[k]) > 0).map((k) => ({ method: k, amount: r2(n(split[k])) }));
    return [{ method: mode, amount: r2(total), ...(ref && mode !== "cash" ? { reference: ref } : {}) }];
  }, [mode, split, total, ref]);
  const paid = payments.reduce((s, p) => s + n(p.amount), 0);
  const due = Math.max(0, Math.round((total - paid) * 100) / 100);
  const hasPhone = /^[6-9]\d{9}$/.test(cart.customer.phone);
  const over = paid - total > 0.004;
  const upiAmount = mode === "upi" ? total : mode === "split" ? n(split.upi) : 0;

  async function submit(approvalPin?: string) {
    setBusy(true); setError(null);
    try {
      const r = await api<Receipt>("/invoices", { method: "POST", json: { ...buildBody(), payments, idempotency_key: cart.idempotencyKey, ...(approvalPin ? { approval_pin: approvalPin } : {}) } });
      setDone(r);
      cart.clear();
      if (printer.autoPrint && printer.status === "connected") void printReceipt(r).catch(() => undefined);
    } catch (e) {
      if (e instanceof ApiError && e.code === "invoice.approval_required") { setPin(""); }
      else setError(e instanceof ApiError ? e.message : "Couldn't save the bill. Check your connection and try again; it won't be saved twice.");
    } finally { setBusy(false); }
  }

  return (
    <Dialog open={open} onClose={onClose} title={done ? "Bill saved" : `Pay ${formatINR(r2(total), { always: true })}`}>
      {done ? (
        <div className="space-y-5 text-center">
          <CheckCircle2 className="mx-auto h-14 w-14 text-success" aria-hidden />
          <div>
            <p className="tnum text-3xl font-bold">{formatINR(done.totals.grand_total, { always: true })}</p>
            <p className="text-text-2">{done.title} · {done.number}</p>
            {Number(done.totals.due_total) > 0 && <p className="mt-1 font-semibold text-warning">Due: {formatINR(done.totals.due_total, { always: true })}</p>}
          </div>
          <ReceiptActions r={done} />
          <Button className="w-full" size="xl" onClick={onClose} autoFocus>New bill</Button>
        </div>
      ) : pin !== null ? (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); void submit(pin); }}>
          <p className="text-text-2">This discount is above your limit. Ask the owner or manager to enter their PIN.</p>
          <FormError message={error} />
          <input value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" type="password" autoFocus
            aria-label="Manager PIN" className="tnum h-14 w-full rounded-lg border border-border-strong bg-surface text-center text-2xl tracking-[0.5em]" />
          <Button type="submit" className="w-full" size="xl" loading={busy} disabled={pin.length < 4}>Approve and save</Button>
        </form>
      ) : (
        <div className="space-y-5">
          <div className="grid grid-cols-5 gap-1.5" role="radiogroup" aria-label="Payment method">
            {MODES.map(({ m, label }) => (
              <button key={m} role="radio" aria-checked={mode === m} onClick={() => setMode(m)}
                className={`h-11 rounded-lg border text-sm font-semibold ${mode === m ? "border-primary bg-primary-soft text-on-primary-soft" : "border-border hover:bg-surface-2"}`}>{label}</button>
            ))}
          </div>
          <FormError message={error} />
          {mode === "cash" && (
            <label className="block">
              <span className="mb-1.5 block text-sm font-semibold">Cash received (optional)</span>
              <input value={received} onChange={(e) => setReceived(e.target.value)} inputMode="decimal" autoFocus placeholder={r2(total)}
                className="tnum h-12 w-full rounded-lg border border-border-strong bg-surface px-3 text-lg" />
              {n(received) > total && <p className="mt-2 text-lg">Give back <span className="tnum font-bold text-success">{formatINR(r2(n(received) - total), { always: true })}</span></p>}
            </label>
          )}
          {mode === "split" && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {(["cash", "upi", "card"] as const).map((k) => (
                <label key={k}><span className="mb-1 block text-xs font-semibold uppercase text-text-2">{k}</span>
                  <input value={split[k]} onChange={(e) => setSplit((s) => ({ ...s, [k]: e.target.value }))} inputMode="decimal"
                    className="tnum h-11 w-full rounded-lg border border-border-strong bg-surface px-2" /></label>
              ))}
              {/* Whatever isn't paid now is the due; filled in, never typed, so the parts always add up to the bill. */}
              <div><span className="mb-1 block text-xs font-semibold uppercase text-text-2">Due</span>
                <output aria-live="polite" className={`tnum flex h-11 items-center rounded-lg border px-2 ${due > 0 ? "border-warning bg-warning-soft font-semibold text-warning" : "border-border bg-surface-2 text-text-3"}`}>
                  {r2(due)}
                </output></div>
            </div>
          )}
          {due > 0 && (mode === "due" || mode === "split") && (
            <label className="block">
              <span className="mb-1.5 block text-sm font-semibold">Customer mobile (needed for due)</span>
              <input value={cart.customer.phone} inputMode="numeric" autoComplete="tel" placeholder="98xxxxxxxx"
                onChange={(e) => cart.set({ customer: { ...cart.customer, phone: e.target.value.replace(/\D/g, "").slice(0, 10) } })}
                className="tnum h-11 w-full rounded-lg border border-border-strong bg-surface px-3" />
            </label>
          )}
          {(mode === "upi" || mode === "card") && (
            <label className="block">
              <span className="mb-1.5 block text-sm font-semibold">{mode === "upi" ? "UPI reference (optional)" : "Card last 4 / approval code (optional)"}</span>
              <input value={ref} onChange={(e) => setRef(e.target.value)} className="h-11 w-full rounded-lg border border-border-strong bg-surface px-3" />
            </label>
          )}
          {upiAmount > 0 && (shop?.upi_vpa ? (
            <div className="flex flex-col items-center gap-2 rounded-xl bg-tint p-4">
              <UpiQr uri={upiUri(shop.upi_vpa, shop.upi_payee_name || shop.name, r2(upiAmount), "Anylo bill")} />
              <p className="text-sm text-text-2">Customer scans with any UPI app · <span className="tnum font-semibold text-text">{formatINR(r2(upiAmount), { always: true })}</span> to {shop.upi_vpa}</p>
            </div>
          ) : <p className="rounded-lg bg-warning-soft px-4 py-3 text-sm text-warning">Add your UPI ID in Settings → Business to show a payment QR here.</p>)}
          {(mode === "due" || mode === "split") && due > 0 && (
            <p className={`rounded-lg px-4 py-3 text-sm ${hasPhone ? "bg-warning-soft text-warning" : "bg-danger-soft text-danger"}`}>
              {formatINR(r2(due), { always: true })} will be kept as due{hasPhone ? ` on ${cart.customer.phone}` : ". Enter the customer's mobile number above."}
            </p>
          )}
          {over && <p className="text-sm text-danger">Payments are more than the bill. Enter the bill amount; change is shown separately.</p>}
          <Button className="w-full" size="xl" loading={busy} disabled={over || (due > 0 && !hasPhone)} onClick={() => void submit()}>
            {due > 0 && mode !== "cash" ? `Save with ${formatINR(r2(due), { always: true })} due` : "Save bill"}
          </Button>
        </div>
      )}
    </Dialog>
  );
}

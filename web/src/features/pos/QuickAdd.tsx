import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { useRates, useUnits, type Product, type Variant } from "@/features/items/api";
import { useShop } from "@/features/shop/api";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Dialog, Toggle } from "@/ui/primitives";
import { useCart } from "./cart";

const cell = "h-12 w-full rounded-lg border border-border-strong bg-surface px-3";
const LAST_RATE = "anylo.pos.lastRate";
const remembered = () => { try { return localStorage.getItem(LAST_RATE) ?? ""; } catch { return ""; } };

/** Short shop-counter names for GST unit codes (KGS → kg). */
export const unitLabel = (code: string) =>
  ({ KGS: "kg", GMS: "g", LTR: "L", MLT: "ml", MTR: "m", NOS: "pcs", PCS: "pcs" } as Record<string, string>)[code] ?? code.toLowerCase();

/** Weighed / measured units get the weighing pad instead of a plain "+1". */
export function useMeasured() {
  const { data: units = [] } = useUnits();
  return (code: string) => units.find((u) => u.code === code)?.allows_decimal ?? false;
}

const PRESETS: Record<string, [string, string][]> = {
  KGS: [["0.25", "250 g"], ["0.5", "500 g"], ["1", "1 kg"], ["2", "2 kg"]],
  GMS: [["100", "100 g"], ["250", "250 g"], ["500", "500 g"]],
  LTR: [["0.5", "500 ml"], ["1", "1 L"], ["2", "2 L"]],
  MLT: [["250", "250 ml"], ["500", "500 ml"]],
};

/** Sell by weight: type the weight, tap a common weight, or type the money ("₹50 of tomatoes") and get the weight. */
export function WeighDialog({ product, variant, onAdd, onClose }: { product: Product; variant: Variant; onAdd: (qty: string) => void; onClose: () => void }) {
  const [mode, setMode] = useState<"qty" | "amount">("qty");
  const [value, setValue] = useState("");
  const price = Number(variant.sale_price);
  const unit = unitLabel(product.unit_code);
  const qty = mode === "qty" ? Number(value) : price > 0 ? Number(value) / price : 0;
  const qtyStr = Number.isFinite(qty) && qty > 0 ? qty.toFixed(3) : "";
  const add = (q: string) => { if (Number(q) > 0) onAdd(String(Number(Number(q).toFixed(3)))); };
  return (
    <Dialog open onClose={onClose} title={`${product.name} · ${formatINR(variant.sale_price, { always: true })}/${unit}`}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); add(qtyStr); }}>
        <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Enter">
          {([["qty", `Weight (${unit})`], ["amount", "Amount ₹"]] as const).map(([m, label]) => (
            <button type="button" key={m} role="radio" aria-checked={mode === m} onClick={() => { setMode(m); setValue(""); }} disabled={m === "amount" && price <= 0}
              className={`h-11 rounded-lg border font-semibold disabled:opacity-40 ${mode === m ? "border-primary bg-primary-soft text-on-primary-soft" : "border-border hover:bg-surface-2"}`}>{label}</button>
          ))}
        </div>
        <input value={value} onChange={(e) => setValue(e.target.value.replace(/[^\d.]/g, ""))} inputMode="decimal" autoFocus
          aria-label={mode === "qty" ? `Weight in ${unit}` : "Amount in rupees"} placeholder={mode === "qty" ? `e.g. 1.250 ${unit}` : "e.g. 50"}
          className="tnum h-16 w-full rounded-lg border border-border-strong bg-surface px-4 text-center text-3xl font-bold" />
        {mode === "qty" && PRESETS[product.unit_code] && (
          <div className="grid grid-cols-4 gap-2">
            {PRESETS[product.unit_code].map(([q, label]) => (
              <button type="button" key={q} onClick={() => add(q)} className="h-12 rounded-lg border border-border font-semibold hover:border-primary">{label}</button>
            ))}
          </div>
        )}
        <p className="tnum text-center text-text-2">{qtyStr ? `${Number(qtyStr)} ${unit} · ${formatINR((Number(qtyStr) * price).toFixed(2), { always: true })}` : " "}</p>
        <Button type="submit" className="w-full" size="xl" disabled={!qtyStr}>Add to bill</Button>
      </form>
    </Dialog>
  );
}

/** For anything not in the item list yet (or a one-off). Owners and managers can save it as an item at the same time. */
export function QuickAddDialog({ name: initialName, onClose }: { name: string; onClose: () => void }) {
  const cart = useCart();
  const qc = useQueryClient();
  const canSave = useAuth((s) => s.can("product.manage"));
  const { data: shop } = useShop();
  const { data: rates = [] } = useRates();
  const { data: units = [] } = useUnits();
  const [save, setSave] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const regular = shop?.tax.gst_scheme === "regular";
  const inclusive = shop?.tax.prices_include_tax ?? true;

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const name = String(f.get("name")).trim();
    const price = String(f.get("price"));
    const unit = String(f.get("unit") || "NOS");
    const rateId = String(f.get("rate") || "");
    const qty = String(f.get("qty") || "1");
    try { localStorage.setItem(LAST_RATE, rateId); } catch { /* storage blocked */ }
    const rate = rates.find((r) => r.id === rateId)?.rate ?? "0";
    if (!save) {
      cart.add({ custom: { name, tax_rate_id: rateId || null, unit_code: unit }, name, unit, unitPrice: price, salePrice: price, rate, inclusive, qty });
      onClose();
      return;
    }
    setBusy(true); setError(null);
    try {
      const p = await api<Product>("/products", { method: "POST", json: {
        name, unit_code: unit, tax_rate_id: rateId || null, price_includes_tax: inclusive, track_stock: false,
        variants: [{ sale_price: price }],
      } });
      void qc.invalidateQueries({ queryKey: ["products"] });
      const v = p.variants[0];
      cart.add({ variantId: v.id, name: p.name, variantName: v.name, unit: p.unit_code, unitPrice: v.sale_price, salePrice: v.sale_price, mrp: v.mrp, rate: p.tax_rate ?? "0", inclusive: p.price_includes_tax, qty });
      onClose();
    } catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't save the item."); } finally { setBusy(false); }
  }

  return (
    <Dialog open onClose={onClose} title="Quick add">
      <form className="space-y-3" onSubmit={submit}>
        <FormError message={error} />
        <input name="name" required defaultValue={initialName} autoFocus={!initialName} placeholder="Item name" aria-label="Item name" className={cell} />
        <div className="grid grid-cols-3 gap-2">
          <input name="price" required inputMode="decimal" autoFocus={!!initialName} placeholder="Price ₹" aria-label="Price" className={`${cell} col-span-1`} />
          <input name="qty" inputMode="decimal" placeholder="Qty (1)" aria-label="Quantity" className={cell} />
          <select name="unit" defaultValue="NOS" aria-label="Sold in" className={cell}>
            {(units.length ? units : [{ code: "NOS", label: "Pieces" }]).map((u) => <option key={u.code} value={u.code}>{u.label}</option>)}
          </select>
        </div>
        {regular && (
          <select name="rate" required defaultValue={rates.some((r) => r.id === remembered()) ? remembered() : ""} aria-label="GST rate" className={cell}>
            <option value="" disabled>GST rate</option>
            {rates.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
        )}
        {canSave
          ? <Toggle checked={save} onChange={setSave} label="Also save to my items" hint="Next time it shows up in search. Stock isn't tracked until you turn it on in Items." />
          : <p className="text-sm text-text-2">Added to this bill only. The owner can add it to the item list later.</p>}
        <Button type="submit" className="w-full" loading={busy}>Add to bill</Button>
      </form>
    </Dialog>
  );
}

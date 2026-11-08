import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Camera as SnapIcon, Keyboard, Minus, Package, PauseCircle, Plus, Search, Trash2, UserRound, X } from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/features/auth/store";
import type { Page, Product, Variant } from "@/features/items/api";
import { useCategories, useRates } from "@/features/items/api";
import { useShop } from "@/features/shop/api";
import { computeInvoice } from "@/lib/gst";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Logo } from "@/ui/Logo";
import { Dialog, Toaster, Toggle, useToast } from "@/ui/primitives";
import { useHeld } from "./api";
import { useCart, type CartLine } from "./cart";
import { CameraButton, CameraScanner, cameraScanSupported, useHidScanner, voiceScore, VoiceButton } from "./inputs";
import { PaymentSheet } from "./PaymentSheet";

const fmtQty = (q: string) => Number(q).toLocaleString("en-IN", { maximumFractionDigits: 3 });
const cell = "h-10 rounded-md border border-border-strong bg-surface px-2 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";

function lineFrom(p: Product, v: Variant): Omit<CartLine, "key" | "qty"> {
  return { variantId: v.id, name: p.name, variantName: v.name, unit: p.unit_code, unitPrice: v.sale_price, salePrice: v.sale_price,
    mrp: v.mrp, rate: p.tax_rate ?? "0", inclusive: p.price_includes_tax };
}

export function PosPage() {
  const cart = useCart();
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const canEditPrice = useAuth((s) => s.me?.user.role !== "salesperson");
  const { data: shop } = useShop();
  const { data: cats = [] } = useCategories();
  const { data: rates = [] } = useRates();
  const { data: page } = useQuery({ queryKey: ["pos-products"], queryFn: () => api<Page>("/products?limit=200") });
  const { data: held = [] } = useHeld();
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [picking, setPicking] = useState<Product | null>(null);
  const [paying, setPaying] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [customerOpen, setCustomerOpen] = useState(false);
  const [custom, setCustom] = useState(false);
  const [showHeld, setShowHeld] = useState(false);
  const [help, setHelp] = useState(false);
  const search = useRef<HTMLInputElement>(null);
  const snapRef = useRef<HTMLInputElement>(null);
  const items = page?.items ?? [];

  const addProduct = useCallback((p: Product, v?: Variant) => {
    if (!v && p.variants.length > 1) return setPicking(p);
    const variant = v ?? p.variants[0];
    if (variant) cart.add(lineFrom(p, variant));
    setPicking(null);
  }, [cart]);

  const addByCode = useCallback(async (code: string) => {
    for (const p of items) {
      const v = p.variants.find((x) => x.barcode === code || x.sku.toLowerCase() === code.toLowerCase());
      if (v) return addProduct(p, v);
    }
    try {
      const r = await api<{ product: Product; variant: Variant }>(`/products/lookup?code=${encodeURIComponent(code)}`);
      addProduct(r.product, r.variant);
    } catch { toast(`No item has barcode ${code}`); }
  }, [items, addProduct, toast]);

  useHidScanner((code) => void addByCode(code), !paying);

  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return items.filter((p) => (!cat || p.category_id === cat) && (!s || p.name.toLowerCase().includes(s) || p.brand?.toLowerCase().includes(s)
      || p.variants.some((v) => v.sku.toLowerCase().includes(s) || v.barcode === q.trim())));
  }, [items, q, cat]);

  // Local preview with the same GST engine as the server (which recomputes and is authoritative).
  const shopState = shop?.state_code ?? "";
  const supply = cart.deliveryMode === "dispatched" && cart.deliveryState && cart.deliveryState !== shopState ? "inter" : "intra";
  const totals = useMemo(() => {
    if (!cart.lines.length || !shop) return null;
    try {
      return computeInvoice({
        lines: cart.lines.map((l) => ({ qty: l.qty || "0.001", unitPrice: l.unitPrice || "0", rate: l.rate, priceIncludesTax: l.inclusive })),
        supplyType: supply, scheme: shop.tax.gst_scheme, roundOff: shop.tax.invoice_round_off,
        discountType: Number(cart.discountValue) > 0 ? cart.discountType : null, discountValue: cart.discountValue || "0",
      });
    } catch { return null; }
  }, [cart.lines, cart.discountType, cart.discountValue, shop, supply]);
  const total = totals ? Number(totals.grandTotal) : 0;

  const buildBody = () => ({
    lines: cart.lines.map((l) => l.variantId
      ? { variant_id: l.variantId, qty: l.qty, unit_price: l.unitPrice }
      : { custom: l.custom, qty: l.qty, unit_price: l.unitPrice }),
    customer: cart.customer.phone || cart.customer.name || (cart.b2b && cart.customer.gstin)
      ? { name: cart.customer.name || null, phone: cart.customer.phone || null, gstin: cart.b2b ? cart.customer.gstin || null : null, address: cart.customer.address || null }
      : null,
    discount_type: Number(cart.discountValue) > 0 ? cart.discountType : null,
    discount_value: cart.discountValue || "0",
    delivery_mode: cart.deliveryMode,
    delivery_state_code: cart.deliveryMode === "dispatched" ? cart.deliveryState || null : null,
    remarks: cart.remarks || null,
  });

  async function hold() {
    if (!cart.lines.length) return;
    const label = cart.customer.name || cart.customer.phone || `Bill ${new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`;
    await api("/held-bills", { method: "POST", json: { label, payload: cart.snapshot() } });
    cart.clear(); void qc.invalidateQueries({ queryKey: ["held"] }); toast(`Held: ${label}`);
  }

  async function resume(id: string, payload: unknown) {
    if (cart.lines.length) await hold(); // never lose the bill on screen
    cart.load(payload);
    await api(`/held-bills/${id}`, { method: "DELETE" });
    void qc.invalidateQueries({ queryKey: ["held"] });
    setShowHeld(false);
  }

  async function snap(file: File) {
    try {
      const body = new FormData(); body.append("file", file);
      const r = await api<{ identified_name: string; matches: Product[] }>("/products/snap", { method: "POST", body });
      setQ(r.matches[0]?.name ?? r.identified_name);
      toast(r.matches.length ? `Looks like ${r.identified_name}` : `Looks like ${r.identified_name}. Not in your items yet.`);
    } catch (e) { toast(e instanceof ApiError ? e.message : "Snap & Find failed."); }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (paying) return;
      if (e.key === "F2" || (e.key === "/" && (e.target as HTMLElement).tagName !== "INPUT")) { e.preventDefault(); search.current?.focus(); }
      if (e.key === "F8") { e.preventDefault(); void hold(); }
      if (e.key === "F9") { e.preventDefault(); setShowHeld(true); }
      if (e.key === "F10" && cart.lines.length && total > 0) { e.preventDefault(); setPaying(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className="flex h-dvh flex-col bg-bg">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface px-3 sm:px-5">
        <Link to="/app" className="grid h-10 w-10 place-items-center rounded-lg hover:bg-surface-2" aria-label="Back to Anylo"><ArrowLeft className="h-5 w-5" /></Link>
        <Logo size={26} />
        <span className="hidden truncate text-sm text-text-2 sm:block">{shop?.name}</span>
        <div className="ml-auto flex gap-1.5">
          <Button variant="ghost" size="md" onClick={() => setShowHeld(true)}><PauseCircle className="h-4 w-4" aria-hidden />Held{held.length ? ` (${held.length})` : ""}</Button>
          <Button variant="ghost" size="md" onClick={() => setHelp(true)} aria-label="Keyboard shortcuts"><Keyboard className="h-4 w-4" /></Button>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[1fr_440px]">
        {/* Catalogue */}
        <section className="flex min-h-0 flex-col p-3 sm:p-5">
          <div className="flex items-center gap-1 rounded-xl border border-border-strong bg-surface pl-3 focus-within:border-primary focus-within:ring-4 focus-within:ring-primary/15">
            <Search className="h-5 w-5 shrink-0 text-text-3" aria-hidden />
            <input ref={search} value={q} onChange={(e) => setQ(e.target.value)} data-scan-target="1" autoFocus aria-label="Search items"
              placeholder="Search, scan a barcode or speak…" className="h-12 min-w-0 flex-1 bg-transparent px-2 text-base focus:outline-none"
              onKeyDown={(e) => { if (e.key === "Enter" && q.trim()) { e.preventDefault(); const p = shown[0]; if (p && !/^\d{6,}$/.test(q.trim())) addProduct(p); else void addByCode(q.trim()); setQ(""); } }} />
            {q && <button onClick={() => setQ("")} className="grid h-11 w-9 place-items-center text-text-3" aria-label="Clear search"><X className="h-4 w-4" /></button>}
            <VoiceButton onText={(t) => { const best = [...items].sort((a, b) => voiceScore(t, b.name) - voiceScore(t, a.name))[0]; if (best && voiceScore(t, best.name) >= 0.6) addProduct(best); else setQ(t); }} />
            {cameraScanSupported && <CameraButton onClick={() => setScanning(true)} />}
            <input ref={snapRef} type="file" accept="image/*" capture="environment" hidden onChange={(e) => e.target.files?.[0] && void snap(e.target.files[0])} />
            <button onClick={() => snapRef.current?.click()} className="mr-1 grid h-11 w-11 place-items-center rounded-lg text-text-2 hover:bg-surface-2" aria-label="Snap & Find: photo search" title="Snap & Find"><SnapIcon className="h-5 w-5" /></button>
          </div>
          <div className="mt-3 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none]">
            {[{ id: "", name: "All" }, ...cats].map((c) => (
              <button key={c.id} onClick={() => setCat(c.id)} className={`h-9 shrink-0 rounded-full px-4 text-sm font-medium ${cat === c.id ? "bg-primary text-on-primary" : "bg-surface text-text-2 hover:bg-surface-2"}`}>{c.name}</button>
            ))}
            <button onClick={() => setCustom(true)} className="h-9 shrink-0 rounded-full border border-dashed border-border-strong px-4 text-sm font-medium text-text-2 hover:bg-surface-2">+ Custom item</button>
          </div>
          <div className="mt-3 grid min-h-0 flex-1 auto-rows-min grid-cols-2 gap-2.5 overflow-y-auto pb-24 sm:grid-cols-3 xl:grid-cols-4 lg:pb-2">
            {shown.map((p) => {
              const v = p.variants[0];
              const out = p.track_stock && p.variants.every((x) => Number(x.stock_qty) <= 0);
              return (
                <button key={p.id} onClick={() => addProduct(p)} className="flex flex-col overflow-hidden rounded-xl border border-border bg-surface text-left transition-colors hover:border-primary active:scale-[.98]">
                  <div className="grid h-20 place-items-center bg-surface-2">
                    {p.thumb_url ? <img src={p.thumb_url} alt="" className="h-full w-full object-cover" loading="lazy" /> : <Package className="h-6 w-6 text-text-3" aria-hidden />}
                  </div>
                  <div className="p-2.5">
                    <p className="line-clamp-2 text-sm font-medium leading-snug">{p.name}</p>
                    <p className="tnum mt-1 text-sm font-semibold">{v ? formatINR(v.sale_price) : "—"}{p.variants.length > 1 && <span className="font-normal text-text-2"> · {p.variants.length} sizes</span>}</p>
                    {out && <p className="text-xs text-warning">Out of stock</p>}
                  </div>
                </button>
              );
            })}
            {!shown.length && <p className="col-span-full py-10 text-center text-text-2">{items.length ? "No items match. Press Enter to look up a barcode." : "Add items first in Items."}</p>}
          </div>
        </section>

        {/* Cart */}
        <aside className="flex min-h-0 flex-col border-t border-border bg-surface lg:border-l lg:border-t-0">
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {!cart.lines.length ? (
              <div className="grid h-full place-items-center py-10 text-center text-text-2"><p>Tap, scan or search items to start a bill.</p></div>
            ) : (
              <ul className="divide-y divide-border">
                {cart.lines.map((l) => (
                  <li key={l.key} className="py-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-medium leading-snug">{l.name}{l.variantName && <span className="text-text-2"> · {l.variantName}</span>}</p>
                      <button onClick={() => cart.remove(l.key)} className="text-text-3 hover:text-danger" aria-label={`Remove ${l.name}`}><Trash2 className="h-4 w-4" /></button>
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <button onClick={() => Number(l.qty) > 1 ? cart.setLine(l.key, { qty: String(Number(l.qty) - 1) }) : cart.remove(l.key)} className="grid h-9 w-9 place-items-center rounded-md border border-border" aria-label="Less"><Minus className="h-4 w-4" /></button>
                      <input value={l.qty} onChange={(e) => cart.setLine(l.key, { qty: e.target.value.replace(/[^\d.]/g, "") })} inputMode="decimal" aria-label="Quantity" className={`${cell} tnum w-16 text-center`} />
                      <button onClick={() => cart.setLine(l.key, { qty: String(Number(l.qty) + 1) })} className="grid h-9 w-9 place-items-center rounded-md border border-border" aria-label="More"><Plus className="h-4 w-4" /></button>
                      <span className="text-sm text-text-2">{l.unit.toLowerCase()} ×</span>
                      {canEditPrice || l.custom
                        ? <input value={l.unitPrice} onChange={(e) => cart.setLine(l.key, { unitPrice: e.target.value.replace(/[^\d.]/g, "") })} inputMode="decimal" aria-label="Price" className={`${cell} tnum w-24 text-right`} />
                        : <span className="tnum">{formatINR(l.unitPrice)}</span>}
                      <span className="tnum ml-auto font-semibold">{formatINR((Number(l.qty) * Number(l.unitPrice)).toFixed(2), { always: true })}</span>
                    </div>
                    {l.mrp && Number(l.unitPrice) > Number(l.mrp) && <p className="mt-1 text-xs text-danger">Above MRP ₹{l.mrp}</p>}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="space-y-3 border-t border-border p-4">
            <button onClick={() => setCustomerOpen(true)} className="flex w-full items-center gap-3 rounded-lg border border-border px-3 py-2.5 text-left hover:bg-surface-2">
              <UserRound className="h-5 w-5 text-text-2" aria-hidden />
              <span className="flex-1 truncate">{cart.customer.name || cart.customer.phone ? `${cart.customer.name} ${cart.customer.phone}`.trim() : <span className="text-text-2">Add customer (optional)</span>}</span>
              {cart.b2b && <span className="rounded bg-primary-soft px-2 py-0.5 text-xs font-semibold text-on-primary-soft">B2B</span>}
            </button>
            <div className="flex items-center gap-2">
              <span className="text-sm text-text-2">Discount</span>
              <div className="flex overflow-hidden rounded-md border border-border-strong">
                {(["flat", "percent"] as const).map((t) => (
                  <button key={t} onClick={() => cart.set({ discountType: t })} className={`h-10 w-10 text-sm font-semibold ${cart.discountType === t ? "bg-primary text-on-primary" : "bg-surface"}`}>{t === "flat" ? "₹" : "%"}</button>
                ))}
              </div>
              <input value={cart.discountValue} onChange={(e) => cart.set({ discountValue: e.target.value.replace(/[^\d.]/g, "") })} inputMode="decimal" placeholder="0" aria-label="Discount" className={`${cell} tnum w-24`} />
            </div>
            {totals && (
              <dl className="tnum space-y-1 text-sm">
                {Number(totals.discountTotal) > 0 && <div className="flex justify-between text-text-2"><dt>Discount</dt><dd>−{formatINR(totals.discountTotal.toFixed(2), { always: true })}</dd></div>}
                {shop?.tax.gst_scheme === "regular" && <div className="flex justify-between text-text-2"><dt>GST {supply === "inter" ? "(IGST)" : "(CGST + SGST)"}</dt><dd>{formatINR(totals.cgstTotal.plus(totals.sgstTotal).plus(totals.igstTotal).toFixed(2), { always: true })}</dd></div>}
                {!totals.roundOff.isZero() && <div className="flex justify-between text-text-2"><dt>Round off</dt><dd>{totals.roundOff.toFixed(2)}</dd></div>}
              </dl>
            )}
            <div className="grid grid-cols-[auto_1fr] gap-2">
              <Button variant="secondary" size="xl" onClick={() => void hold()} disabled={!cart.lines.length} aria-label="Hold bill" title="Hold (F8)"><PauseCircle className="h-5 w-5" /></Button>
              <Button size="xl" disabled={!cart.lines.length || total <= 0} onClick={() => setPaying(true)}>
                Pay {formatINR(total.toFixed(2), { always: true })}
              </Button>
            </div>
          </div>
        </aside>
      </div>

      <Dialog open={!!picking} onClose={() => setPicking(null)} title={picking?.name ?? ""}>
        <div className="grid grid-cols-2 gap-2">
          {picking?.variants.map((v) => (
            <button key={v.id} onClick={() => addProduct(picking, v)} className="rounded-lg border border-border p-3 text-left hover:border-primary">
              <span className="block font-medium">{v.name || "Standard"}</span>
              <span className="tnum text-sm text-text-2">{formatINR(v.sale_price)}{picking.track_stock && ` · ${fmtQty(v.stock_qty)} left`}</span>
            </button>
          ))}
        </div>
      </Dialog>

      <Dialog open={customerOpen} onClose={() => setCustomerOpen(false)} title="Customer">
        <CustomerForm onDone={() => setCustomerOpen(false)} shopState={shopState} />
      </Dialog>

      <Dialog open={custom} onClose={() => setCustom(false)} title="Custom item">
        <form className="space-y-3" onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const rateId = String(f.get("rate") || "");
          const rate = rates.find((r) => r.id === rateId)?.rate ?? "0";
          cart.add({ custom: { name: String(f.get("name")), tax_rate_id: rateId || null, unit_code: "NOS" }, name: String(f.get("name")), unit: "NOS",
            unitPrice: String(f.get("price")), salePrice: String(f.get("price")), rate, inclusive: shop?.tax.prices_include_tax ?? true, qty: String(f.get("qty") || "1") });
          setCustom(false);
        }}>
          <p className="text-sm text-text-2">For one-off items. It won't be added to your item list.</p>
          <input name="name" required placeholder="Item name" className={`${cell} h-12 w-full`} />
          <div className="grid grid-cols-2 gap-2">
            <input name="price" required inputMode="decimal" placeholder="Price ₹" className={`${cell} h-12 w-full`} />
            <input name="qty" inputMode="decimal" placeholder="Qty (1)" className={`${cell} h-12 w-full`} />
          </div>
          {shop?.tax.gst_scheme === "regular" && (
            <select name="rate" required className={`${cell} h-12 w-full`} defaultValue="">
              <option value="" disabled>GST rate</option>
              {rates.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          )}
          <Button type="submit" className="w-full">Add to bill</Button>
        </form>
      </Dialog>

      <Dialog open={showHeld} onClose={() => setShowHeld(false)} title="Held bills">
        {!held.length ? <p className="text-text-2">No held bills. Press Hold (F8) to park the bill on screen.</p> : (
          <ul className="divide-y divide-border">
            {held.map((h) => (
              <li key={h.id} className="flex items-center justify-between gap-3 py-3">
                <span><span className="font-medium">{h.label}</span><span className="block text-sm text-text-2">{new Date(h.created_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}{h.created_by_name ? ` · ${h.created_by_name}` : ""}</span></span>
                <Button size="md" variant="soft" onClick={() => void resume(h.id, h.payload)}>Resume</Button>
              </li>
            ))}
          </ul>
        )}
      </Dialog>

      <Dialog open={help} onClose={() => setHelp(false)} title="Keyboard shortcuts">
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2">
          {[["F2 or /", "Search"], ["Enter", "Add top result or look up barcode"], ["F8", "Hold bill"], ["F9", "Held bills"], ["F10", "Pay"], ["Esc", "Close"]].map(([k, v]) => (
            <Fragment key={k}><dt className="font-mono text-sm font-semibold">{k}</dt><dd className="text-text-2">{v}</dd></Fragment>
          ))}
        </dl>
        <p className="mt-4 text-sm text-text-2">USB barcode scanners work anywhere on this screen.</p>
      </Dialog>

      {scanning && <CameraScanner onCode={(c) => void addByCode(c)} onClose={() => setScanning(false)} />}
      <PaymentSheet open={paying} total={total} onClose={() => { setPaying(false); search.current?.focus(); void qc.invalidateQueries({ queryKey: ["pos-products"] }); }} buildBody={buildBody} />
      <Toaster />
    </div>
  );
}

function CustomerForm({ onDone, shopState }: { onDone: () => void; shopState: string }) {
  const cart = useCart();
  const c = cart.customer;
  const setC = (patch: Partial<typeof c>) => cart.set({ customer: { ...c, ...patch } });
  const ref = useQuery({ queryKey: ["reference"], queryFn: () => api<{ states: { value: string; label: string }[] }>("/meta/reference"), staleTime: Infinity });
  return (
    <div className="space-y-3">
      <input value={c.phone} onChange={(e) => { const phone = e.target.value.replace(/\D/g, "").slice(0, 10); setC({ phone }); }}
        inputMode="numeric" placeholder="Mobile number" aria-label="Customer mobile" autoFocus className={`${cell} h-12 w-full`} />
      <input value={c.name} onChange={(e) => setC({ name: e.target.value })} placeholder="Name (optional)" aria-label="Customer name" className={`${cell} h-12 w-full`} />
      <Toggle checked={cart.b2b} onChange={(b2b) => cart.set({ b2b })} label="Business customer (B2B)" hint="Shows their GSTIN on the tax invoice." />
      {cart.b2b && (
        <>
          <input value={c.gstin} onChange={(e) => setC({ gstin: e.target.value.toUpperCase().slice(0, 15) })} placeholder="Customer GSTIN" aria-label="Customer GSTIN" className={`${cell} h-12 w-full uppercase`} />
          <input value={c.address} onChange={(e) => setC({ address: e.target.value })} placeholder="Billing address" aria-label="Billing address" className={`${cell} h-12 w-full`} />
        </>
      )}
      <Toggle checked={cart.deliveryMode === "dispatched"} onChange={(v) => cart.set({ deliveryMode: v ? "dispatched" : "counter" })}
        label="Goods are being sent to another place" hint="Leave off when the customer takes the goods at the counter." />
      {cart.deliveryMode === "dispatched" && (
        <select value={cart.deliveryState || shopState} onChange={(e) => cart.set({ deliveryState: e.target.value })} aria-label="Delivery state" className={`${cell} h-12 w-full`}>
          {ref.data?.states.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      )}
      <input value={cart.remarks} onChange={(e) => cart.set({ remarks: e.target.value })} placeholder="Note on bill (optional)" aria-label="Note" className={`${cell} h-12 w-full`} />
      <div className="flex gap-2">
        <Button variant="ghost" className="flex-1" onClick={() => { cart.set({ customer: { name: "", phone: "", gstin: "", address: "" }, b2b: false }); onDone(); }}>Clear</Button>
        <Button className="flex-1" onClick={onDone}>Done</Button>
      </div>
    </div>
  );
}

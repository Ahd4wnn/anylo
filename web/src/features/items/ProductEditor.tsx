import { ArrowLeft, Archive, ImagePlus, Plus, RotateCcw, ScanBarcode, Trash2, Wand2 } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { useShop } from "@/features/shop/api";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { Badge, Dialog, Section, Toggle, useToast } from "@/ui/primitives";
import {
  isLow, qtyFmt, useCatalogueRefresh, useCategories, useCreateCategory, useMovements, useProduct, useRates, useUnits,
  type Product, type ProductIn, type Variant, type VariantIn,
} from "./api";

type Row = VariantIn & { key: string; stock_qty?: string };
let keySeq = 0;
const newRow = (): Row => ({ key: `n${++keySeq}`, name: "", sku: "", barcode: "", mrp: "", sale_price: "", cost_price: "", reorder_level: "", opening_stock: "" });
const fromVariant = (v: Variant): Row => ({
  key: v.id, id: v.id, name: v.name ?? "", sku: v.sku, barcode: v.barcode ?? "", mrp: v.mrp ?? "", sale_price: v.sale_price,
  cost_price: v.cost_price, reorder_level: v.reorder_level, stock_qty: v.stock_qty,
});
const nz = (s?: string | null) => (s && s.trim() ? s.trim() : null);
const cell = "h-10 w-full rounded-md border border-border-strong bg-surface px-2.5 text-[15px] focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";

function AdjustDialog({ variant, unit, onClose }: { variant: Variant | null; unit: string; onClose: () => void }) {
  const refresh = useCatalogueRefresh();
  const toast = useToast((s) => s.show);
  const [mode, setMode] = useState<"set" | "add" | "remove">("set");
  const [damage, setDamage] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const history = useMovements(variant?.id);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setError(null);
    try {
      await api("/stock/adjustments", { method: "POST", json: {
        variant_id: variant!.id, mode, qty: String(f.get("qty")), reason: nz(String(f.get("reason"))),
        kind: mode === "remove" && damage ? "damage" : "adjustment",
      } });
      await refresh(); toast("Stock updated"); onClose();
    } catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't update stock."); }
  }
  return (
    <Dialog open={!!variant} onClose={onClose} title={`Stock: ${variant?.name ?? "item"}`}>
      {variant && (
        <form onSubmit={submit} className="space-y-4">
          <p className="text-text-2">In stock now: <span className="tnum font-semibold text-text">{qtyFmt(variant.stock_qty)} {unit.toLowerCase()}</span></p>
          <FormError message={error} />
          <div className="grid grid-cols-3 gap-2" role="radiogroup">
            {([["set", "Counted"], ["add", "Add"], ["remove", "Remove"]] as const).map(([m, label]) => (
              <button key={m} type="button" role="radio" aria-checked={mode === m} onClick={() => setMode(m)}
                className={`h-11 rounded-lg border font-medium ${mode === m ? "border-primary bg-primary-soft text-on-primary-soft" : "border-border hover:bg-surface-2"}`}>{label}</button>
            ))}
          </div>
          <Field label={mode === "set" ? "Quantity you counted" : "Quantity"} name="qty" inputMode="decimal" required pattern="[0-9]+(\.[0-9]{1,3})?" />
          {mode === "remove" && <Toggle checked={damage} onChange={setDamage} label="Damaged or expired" hint="Recorded separately as a loss." />}
          <Field label="Note (optional)" name="reason" placeholder="e.g. Stock count, wrong entry" />
          <Button type="submit" className="w-full">Save</Button>
          {!!history.data?.length && (
            <div>
              <p className="mb-2 text-sm font-semibold">Recent changes</p>
              <ul className="divide-y divide-border text-sm">
                {history.data.slice(0, 20).map((m) => (
                  <li key={m.id} className="flex justify-between gap-3 py-2">
                    <span className="capitalize text-text-2">{m.kind.replace("_", " ")}{m.reason ? ` · ${m.reason}` : ""}<br />
                      <span className="text-text-3">{new Date(m.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}{m.created_by_name ? ` · ${m.created_by_name}` : ""}</span></span>
                    <span className={`tnum font-semibold ${Number(m.qty) < 0 ? "text-danger" : "text-success"}`}>{Number(m.qty) > 0 ? "+" : ""}{qtyFmt(m.qty)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </form>
      )}
    </Dialog>
  );
}

export function ProductEditor() {
  const { id } = useParams();
  const isNew = !id;
  const navigate = useNavigate();
  const toast = useToast((s) => s.show);
  const canManage = useAuth((s) => s.can("product.manage"));
  const refresh = useCatalogueRefresh();
  const { data: product, isLoading } = useProduct(id);
  const { data: shop } = useShop();
  const { data: cats = [] } = useCategories();
  const { data: units = [] } = useUnits();
  const { data: rates = [] } = useRates();
  const createCategory = useCreateCategory();
  const fileRef = useRef<HTMLInputElement>(null);

  const [p, setP] = useState<Omit<ProductIn, "variants">>({ name: "", unit_code: "NOS", track_stock: true, price_includes_tax: null });
  const [rows, setRows] = useState<Row[]>([newRow()]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [adjusting, setAdjusting] = useState<Variant | null>(null);

  useEffect(() => {
    if (!product) return;
    const { variants, ...rest } = product;
    setP({ ...rest });
    setRows(variants.length ? variants.map(fromVariant) : [newRow()]);
  }, [product]);

  const set = <K extends keyof typeof p>(k: K, v: (typeof p)[K]) => setP((x) => ({ ...x, [k]: v }));
  const setRow = (key: string, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const regular = shop?.tax.gst_scheme === "regular";
  const multi = rows.length > 1;

  async function genBarcode(key: string) {
    const { barcode } = await api<{ barcode: string }>("/barcodes/generate", { method: "POST" });
    setRow(key, { barcode });
  }

  async function addCategory() {
    const name = window.prompt("New category name")?.trim(); // ponytail: native prompt; swap for an inline combobox if owners find it clunky
    if (!name) return;
    try { const c = await createCategory.mutateAsync(name); set("category_id", c.id); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't add the category."); }
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null); setBusy(true);
    const body: ProductIn = {
      ...p, name: p.name.trim(), brand: nz(p.brand), hsn_code: nz(p.hsn_code), description: nz(p.description),
      category_id: p.category_id || null, tax_rate_id: p.tax_rate_id || null,
      variants: rows.map((r) => ({
        id: r.id, name: nz(r.name), sku: nz(r.sku), barcode: nz(r.barcode), mrp: nz(r.mrp), sale_price: r.sale_price || "0",
        cost_price: r.cost_price || "0", reorder_level: r.reorder_level || "0", ...(r.id ? {} : { opening_stock: r.opening_stock || "0" }),
      })),
    };
    try {
      const saved = await api<Product>(isNew ? "/products" : `/products/${id}`, { method: isNew ? "POST" : "PUT", json: body });
      await refresh();
      toast(isNew ? "Item added" : "Item saved");
      navigate(isNew ? `/app/items/${saved.id}` : "/app/items", { replace: isNew });
    } catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't save this item."); }
    finally { setBusy(false); }
  }

  async function photo(file: File | null) {
    try {
      if (file) { const body = new FormData(); body.append("file", file); await api(`/products/${id}/photo`, { method: "POST", body }); }
      else await api(`/products/${id}/photo`, { method: "DELETE" });
      await refresh();
    } catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't update the photo."); }
  }

  async function archive(restore: boolean) {
    await api(restore ? `/products/${id}/restore` : `/products/${id}`, { method: restore ? "POST" : "DELETE" });
    await refresh(); toast(restore ? "Item restored" : "Item archived. It's hidden from billing but history is kept.");
    if (!restore) navigate("/app/items");
  }

  if (!isNew && isLoading) return <p className="text-text-2">Loading…</p>;

  return (
    <>
    <form onSubmit={save} className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link to="/app/items" className="grid h-10 w-10 place-items-center rounded-lg hover:bg-surface-2" aria-label="Back to items"><ArrowLeft className="h-5 w-5" /></Link>
          <h1 className="text-2xl font-bold tracking-tight">{isNew ? "Add item" : p.name || "Item"}</h1>
          {product?.archived && <Badge>Archived</Badge>}
        </div>
        {canManage && (
          <div className="flex gap-2">
            {!isNew && <Button type="button" variant="ghost" size="md" onClick={() => void archive(!!product?.archived)}>
              {product?.archived ? <><RotateCcw className="h-4 w-4" aria-hidden />Restore</> : <><Archive className="h-4 w-4" aria-hidden />Archive</>}
            </Button>}
            <Button type="submit" size="md" loading={busy}>Save</Button>
          </div>
        )}
      </div>
      <FormError message={error} />

      <fieldset disabled={!canManage} className="space-y-6">
        <Section title="Details">
          <div className="flex gap-5">
            {!isNew && (
              <div className="shrink-0">
                <div className="grid h-24 w-24 place-items-center overflow-hidden rounded-xl border border-border bg-surface-2">
                  {product?.photo_url ? <img src={product.photo_url} alt="" className="h-full w-full object-cover" /> : <ImagePlus className="h-7 w-7 text-text-3" aria-hidden />}
                </div>
                <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(e) => void photo(e.target.files?.[0] ?? null)} />
                <button type="button" onClick={() => fileRef.current?.click()} className="mt-2 block w-24 text-center text-sm font-semibold text-primary">{product?.photo_url ? "Change" : "Add photo"}</button>
                {product?.photo_url && <button type="button" onClick={() => void photo(null)} className="block w-24 text-center text-sm text-text-2">Remove</button>}
              </div>
            )}
            <div className="grid flex-1 gap-5 sm:grid-cols-2">
              <Field label="Item name" value={p.name} onChange={(e) => set("name", e.target.value)} required maxLength={120} placeholder="e.g. Basmati Rice" />
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label htmlFor="cat" className="text-sm font-semibold">Category</label>
                  {canManage && <button type="button" onClick={() => void addCategory()} className="text-sm font-semibold text-primary">+ New</button>}
                </div>
                <select id="cat" value={p.category_id ?? ""} onChange={(e) => set("category_id", e.target.value || null)} className="h-12 w-full rounded-md border border-border-strong bg-surface px-3">
                  <option value="">No category</option>
                  {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <Field label="Brand (optional)" value={p.brand ?? ""} onChange={(e) => set("brand", e.target.value)} />
              <div className="space-y-1.5">
                <label htmlFor="unit" className="text-sm font-semibold">Sold in</label>
                <select id="unit" value={p.unit_code} onChange={(e) => set("unit_code", e.target.value)} className="h-12 w-full rounded-md border border-border-strong bg-surface px-3">
                  {units.map((u) => <option key={u.code} value={u.code}>{u.label} ({u.code}){u.allows_decimal ? " · decimals" : ""}</option>)}
                </select>
              </div>
            </div>
          </div>
          <div className="grid gap-x-8 sm:grid-cols-2">
            <Toggle checked={p.track_stock} onChange={(v) => set("track_stock", v)} label="Track stock" hint="Off for services or items you don't count." />
            <Toggle checked={!!p.is_service} onChange={(v) => setP((x) => ({ ...x, is_service: v, track_stock: v ? false : x.track_stock }))} label="This is a service" hint="Repairs, alterations, delivery…" />
          </div>
        </Section>

        <Section title="GST" description={regular ? "Needed for tax invoices and GST returns." : "Your shop isn't registered for regular GST, so these are optional."}>
          {regular && product?.missing_tax_info && <p className="rounded-lg bg-warning-soft px-4 py-3 text-sm text-warning">Add the HSN code and GST rate so this item can go on a tax invoice.</p>}
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label={p.is_service ? "SAC code" : "HSN code"} value={p.hsn_code ?? ""} inputMode="numeric" maxLength={8} placeholder="e.g. 1006"
              onChange={(e) => set("hsn_code", e.target.value.replace(/\D/g, ""))}
              hint={`At least ${shop?.tax.hsn_digits_required ?? 4} digits.`} />
            <div className="space-y-1.5">
              <label htmlFor="rate" className="text-sm font-semibold">GST rate</label>
              <select id="rate" value={p.tax_rate_id ?? ""} onChange={(e) => set("tax_rate_id", e.target.value || null)} className="h-12 w-full rounded-md border border-border-strong bg-surface px-3">
                <option value="">Not set</option>
                {rates.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </div>
          </div>
          <Toggle checked={p.price_includes_tax ?? shop?.tax.prices_include_tax ?? true} onChange={(v) => set("price_includes_tax", v)}
            label="Selling price includes GST" hint="On for MRP items. Off adds GST on top at billing." />
        </Section>

        <Section title={multi ? "Variants and prices" : "Price and stock"}
          description={multi ? "Each size or colour has its own price, barcode and stock." : "Add variants if this item comes in sizes or colours."}
          footer={canManage && <Button type="button" variant="secondary" size="md" onClick={() => setRows((r) => [...r, newRow()])}><Plus className="h-4 w-4" aria-hidden />Add variant</Button>}>
          <div className="space-y-4">
            {rows.map((r) => {
              const live = product?.variants.find((v) => v.id === r.id);
              return (
                <div key={r.key} className="rounded-lg border border-border p-4">
                  <div className="grid gap-3 sm:grid-cols-6">
                    {multi && <label className="sm:col-span-2"><span className="mb-1 block text-xs font-semibold text-text-2">Variant name</span>
                      <input className={cell} value={r.name ?? ""} onChange={(e) => setRow(r.key, { name: e.target.value })} placeholder="e.g. 500 g, Red / M" required /></label>}
                    <label><span className="mb-1 block text-xs font-semibold text-text-2">Selling price ₹</span>
                      <input className={`${cell} tnum`} inputMode="decimal" value={r.sale_price} onChange={(e) => setRow(r.key, { sale_price: e.target.value })} required /></label>
                    <label><span className="mb-1 block text-xs font-semibold text-text-2">MRP ₹</span>
                      <input className={`${cell} tnum`} inputMode="decimal" value={r.mrp ?? ""} onChange={(e) => setRow(r.key, { mrp: e.target.value })} /></label>
                    <label><span className="mb-1 block text-xs font-semibold text-text-2">Cost price ₹</span>
                      <input className={`${cell} tnum`} inputMode="decimal" value={r.cost_price ?? ""} onChange={(e) => setRow(r.key, { cost_price: e.target.value })} /></label>
                    {p.track_stock && <label><span className="mb-1 block text-xs font-semibold text-text-2">Alert below</span>
                      <input className={`${cell} tnum`} inputMode="decimal" value={r.reorder_level ?? ""} onChange={(e) => setRow(r.key, { reorder_level: e.target.value })} /></label>}
                    <label className="sm:col-span-2"><span className="mb-1 block text-xs font-semibold text-text-2">Barcode</span>
                      <span className="flex gap-1.5">
                        <input className={cell} value={r.barcode ?? ""} onChange={(e) => setRow(r.key, { barcode: e.target.value.trim() })} placeholder="Scan or type" />
                        <button type="button" title="Make a barcode" aria-label="Generate barcode" onClick={() => void genBarcode(r.key)} className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-border-strong hover:bg-surface-2"><Wand2 className="h-4 w-4" /></button>
                      </span></label>
                    <label><span className="mb-1 block text-xs font-semibold text-text-2">SKU</span>
                      <input className={cell} value={r.sku ?? ""} onChange={(e) => setRow(r.key, { sku: e.target.value })} placeholder="Auto" /></label>
                    {p.track_stock && !r.id && <label><span className="mb-1 block text-xs font-semibold text-text-2">Opening stock</span>
                      <input className={`${cell} tnum`} inputMode="decimal" value={r.opening_stock ?? ""} onChange={(e) => setRow(r.key, { opening_stock: e.target.value })} /></label>}
                  </div>
                  {(live || rows.length > 1) && (
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
                      {live && p.track_stock ? (
                        <button type="button" onClick={() => setAdjusting(live)} className={`flex items-center gap-2 text-sm font-semibold ${isLow(live) ? "text-warning" : "text-primary"}`}>
                          <ScanBarcode className="h-4 w-4" aria-hidden />In stock: <span className="tnum">{qtyFmt(live.stock_qty)}</span>{isLow(live) && " (low)"} · Adjust
                        </button>
                      ) : <span />}
                      {rows.length > 1 && <button type="button" onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))} className="flex items-center gap-1 text-sm text-text-2 hover:text-danger"><Trash2 className="h-4 w-4" aria-hidden />Remove</button>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Section>
      </fieldset>
    </form>
    {/* Outside the product form: a form can't contain another form. */}
    <AdjustDialog variant={adjusting} unit={p.unit_code} onClose={() => setAdjusting(null)} />
    </>
  );
}

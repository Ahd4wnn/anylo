import { AlertTriangle, Barcode, Download, Package, Plus, Search, Upload } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, saveFile } from "@/api/client";
import { useAuth } from "@/features/auth/store";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Badge, PageHeader } from "@/ui/primitives";
import { isLow, qtyFmt, useCategories, useProducts, type Product } from "./api";

function priceRange(p: Product) {
  const prices = p.variants.map((v) => Number(v.sale_price));
  if (!prices.length) return "—";
  const lo = Math.min(...prices), hi = Math.max(...prices);
  return lo === hi ? formatINR(lo) : `${formatINR(lo)} – ${formatINR(hi)}`;
}

function stockOf(p: Product) {
  if (!p.track_stock) return { text: "Not tracked", low: false };
  const total = p.variants.reduce((n, v) => n + Number(v.stock_qty), 0);
  return { text: `${qtyFmt(String(total))} ${p.unit_code.toLowerCase()}`, low: p.variants.some(isLow) };
}

function Thumb({ p }: { p: Product }) {
  return (
    <div className="grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-lg bg-surface-2">
      {p.thumb_url ? <img src={p.thumb_url} alt="" className="h-full w-full object-cover" loading="lazy" /> : <Package className="h-5 w-5 text-text-3" aria-hidden />}
    </div>
  );
}

export function ItemsPage() {
  const navigate = useNavigate();
  const canManage = useAuth((s) => s.can("product.manage"));
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [low, setLow] = useState(false);
  const [archived, setArchived] = useState(false);
  const [cursor, setCursor] = useState<string | undefined>();
  const { data: cats = [] } = useCategories();
  const { data, isLoading, isFetching } = useProducts({ q: q.trim(), category_id: category, low_stock: low, include_archived: archived, cursor });
  const reset = <T,>(fn: (v: T) => void) => (v: T) => { setCursor(undefined); fn(v); };

  async function exportXlsx() {
    saveFile(await api<Blob>("/products/export", { blob: true }), "anylo-items.xlsx");
  }

  return (
    <>
      <PageHeader title="Items" description={data ? `${data.total.toLocaleString("en-IN")} items` : undefined}
        action={canManage && (
          <div className="flex flex-wrap gap-2">
            <Link to="/app/items/stock" className="inline-flex h-10 items-center gap-2 rounded-lg border border-border-strong bg-surface px-4 text-[15px] font-semibold hover:bg-surface-2">Stock</Link>
            <Button variant="secondary" size="md" onClick={() => void exportXlsx()}><Download className="h-4 w-4" aria-hidden />Export</Button>
            <Link to="/app/items/import" className="inline-flex h-10 items-center gap-2 rounded-lg border border-border-strong bg-surface px-4 text-[15px] font-semibold hover:bg-surface-2"><Upload className="h-4 w-4" aria-hidden />Import</Link>
            <Link to="/app/items/labels" className="inline-flex h-10 items-center gap-2 rounded-lg border border-border-strong bg-surface px-4 text-[15px] font-semibold hover:bg-surface-2"><Barcode className="h-4 w-4" aria-hidden />Labels</Link>
            <Button size="md" onClick={() => navigate("/app/items/new")}><Plus className="h-4 w-4" aria-hidden />Add item</Button>
          </div>
        )} />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="relative min-w-[220px] flex-1">
          <span className="sr-only">Search items</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-text-3" aria-hidden />
          <input value={q} onChange={(e) => reset(setQ)(e.target.value)} placeholder="Search name, SKU, barcode or brand"
            className="h-11 w-full rounded-lg border border-border-strong bg-surface pl-10 pr-3 focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/15" />
        </label>
        <select value={category} onChange={(e) => reset(setCategory)(e.target.value)} aria-label="Category"
          className="h-11 rounded-lg border border-border-strong bg-surface px-3">
          <option value="">All categories</option>
          {cats.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.product_count})</option>)}
        </select>
        <button onClick={() => reset(setLow)(!low)} aria-pressed={low}
          className={`h-11 rounded-lg border px-4 font-medium ${low ? "border-warning-fill bg-warning-soft text-warning" : "border-border-strong bg-surface hover:bg-surface-2"}`}>
          Low stock
        </button>
        {canManage && (
          <button onClick={() => reset(setArchived)(!archived)} aria-pressed={archived}
            className={`h-11 rounded-lg border px-4 font-medium ${archived ? "border-primary bg-primary-soft text-on-primary-soft" : "border-border-strong bg-surface hover:bg-surface-2"}`}>
            Show archived
          </button>
        )}
      </div>

      {isLoading ? <p className="text-text-2">Loading…</p> : !data?.items.length ? (
        <div className="rounded-xl border border-dashed border-border-strong bg-surface p-10 text-center">
          <Package className="mx-auto h-8 w-8 text-text-3" aria-hidden />
          <p className="mt-3 font-semibold">{q || category || low ? "No items match." : "No items yet."}</p>
          {canManage && !q && <p className="mt-1 text-text-2">Add your first item, import a spreadsheet, or load starter items from Settings.</p>}
        </div>
      ) : (
        <ul className={`divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface ${isFetching ? "opacity-70" : ""}`}>
          {data.items.map((p) => {
            const s = stockOf(p);
            return (
              <li key={p.id}>
                <Link to={`/app/items/${p.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-surface-2">
                  <Thumb p={p} />
                  <div className="min-w-0 flex-1">
                    <p className={`truncate font-medium ${p.archived ? "text-text-3" : ""}`}>{p.name}</p>
                    <p className="truncate text-sm text-text-2">
                      {[p.category_name, p.brand, p.variants.length > 1 ? `${p.variants.length} variants` : p.variants[0]?.sku].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <div className="hidden flex-wrap justify-end gap-1.5 sm:flex">
                    {p.archived && <Badge>Archived</Badge>}
                    {p.missing_tax_info && <Badge tone="warning">Set GST</Badge>}
                  </div>
                  <div className="w-28 text-right">
                    <p className="tnum font-semibold">{priceRange(p)}</p>
                    <p className={`tnum text-sm ${s.low ? "font-semibold text-warning" : "text-text-2"}`}>
                      {s.low && <AlertTriangle className="mr-1 inline h-3.5 w-3.5" aria-label="Low stock" />}{s.text}
                    </p>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      {data?.next_cursor && (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" size="md" onClick={() => setCursor(data.next_cursor ?? undefined)}>Next page</Button>
        </div>
      )}
      {cursor && <div className="mt-2 flex justify-center"><Button variant="ghost" size="md" onClick={() => setCursor(undefined)}>Back to first page</Button></div>}
    </>
  );
}

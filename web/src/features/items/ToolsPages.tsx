import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Download, FileSpreadsheet, Images, Minus, Plus, Printer, Search, XCircle } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, saveFile } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Badge, PageHeader, Section, Toggle, useToast } from "@/ui/primitives";
import { isLow, qtyFmt, useCatalogueRefresh, useMovements, useProducts, type Product } from "./api";

const Back = () => (
  <Link to="/app/items" className="mb-4 inline-flex items-center gap-2 text-sm font-semibold text-text-2 hover:text-text"><ArrowLeft className="h-4 w-4" aria-hidden />Items</Link>
);

interface ImportResult { committed: boolean; creates: number; updates: number; errors: number; rows: { row: number; name: string; action: string; errors: string[] }[] }

export function ImportPage() {
  const refresh = useCatalogueRefresh();
  const toast = useToast((s) => s.show);
  const fileRef = useRef<HTMLInputElement>(null);
  const zipRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [photos, setPhotos] = useState<{ matched: string[]; unmatched: string[] } | null>(null);

  async function run(f: File, commit: boolean) {
    setBusy(true); setError(null);
    try {
      const body = new FormData(); body.append("file", f);
      const r = await api<ImportResult>(`/products/import?dry_run=${!commit}`, { method: "POST", body });
      setResult(r);
      if (r.committed) { await refresh(); toast(`Imported: ${r.creates} new, ${r.updates} updated`); }
    } catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't read this file."); }
    finally { setBusy(false); }
  }

  async function uploadZip(f: File) {
    setBusy(true); setError(null);
    try {
      const body = new FormData(); body.append("file", f);
      setPhotos(await api("/products/photos/zip", { method: "POST", body }));
      await refresh();
    } catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't read this zip."); }
    finally { setBusy(false); }
  }

  return (
    <>
      <Back />
      <PageHeader title="Import items" description="Add or update many items at once from Excel or CSV." />
      <div className="space-y-6">
        <FormError message={error} />
        <Section title="1. Get the template" description="Fill one row per item (or per size/colour). Existing SKUs or barcodes update those items.">
          <Button variant="secondary" size="md" onClick={async () => saveFile(await api<Blob>("/products/import/template", { blob: true }), "anylo-items-template.xlsx")}>
            <Download className="h-4 w-4" aria-hidden />Download template
          </Button>
        </Section>
        <Section title="2. Upload and check" description="We check every row first. Nothing is saved until you confirm.">
          <input ref={fileRef} type="file" accept=".xlsx,.csv" hidden onChange={(e) => { const f = e.target.files?.[0] ?? null; setFile(f); setResult(null); if (f) void run(f, false); }} />
          <Button variant="secondary" size="md" loading={busy && !result} onClick={() => fileRef.current?.click()}>
            <FileSpreadsheet className="h-4 w-4" aria-hidden />{file ? `Change file (${file.name})` : "Choose file"}
          </Button>
          {result && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <Badge tone="success">{result.creates} new</Badge><Badge tone="brand">{result.updates} updates</Badge>
                {result.errors > 0 && <Badge tone="warning">{result.errors} rows need fixing</Badge>}
                {result.committed && <Badge tone="success">Saved</Badge>}
              </div>
              <ul className="max-h-80 divide-y divide-border overflow-auto rounded-lg border border-border">
                {result.rows.map((r) => (
                  <li key={r.row} className="flex items-start gap-3 px-4 py-2.5 text-sm">
                    {r.errors.length ? <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden /> : <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />}
                    <span className="w-14 shrink-0 text-text-3">Row {r.row}</span>
                    <span className="flex-1"><span className="font-medium">{r.name || "—"}</span>
                      {r.errors.length ? <span className="block text-danger">{r.errors.join("; ")}</span> : <span className="ml-2 capitalize text-text-2">{r.action}</span>}</span>
                  </li>
                ))}
              </ul>
              {!result.committed && (result.errors > 0
                ? <p className="text-sm text-text-2">Fix the rows above in your file and choose it again.</p>
                : <Button loading={busy} onClick={() => file && void run(file, true)}>Import {result.creates + result.updates} items</Button>)}
            </div>
          )}
        </Section>
        <Section title="Photos in bulk" description="Zip your photos. Name each file after the item's SKU or name, e.g. AN-000012.jpg or basmati-rice.jpg.">
          <input ref={zipRef} type="file" accept=".zip" hidden onChange={(e) => e.target.files?.[0] && void uploadZip(e.target.files[0])} />
          <Button variant="secondary" size="md" loading={busy && !!photos} onClick={() => zipRef.current?.click()}><Images className="h-4 w-4" aria-hidden />Upload photo zip</Button>
          {photos && <p className="text-sm text-text-2">Matched {photos.matched.length}. {photos.unmatched.length > 0 && `Not matched: ${photos.unmatched.slice(0, 8).join(", ")}${photos.unmatched.length > 8 ? "…" : ""}`}</p>}
        </Section>
      </div>
    </>
  );
}

type Pick = { variantId: string; label: string; price: string; copies: number };

export function LabelsPage() {
  const [q, setQ] = useState("");
  const [picks, setPicks] = useState<Pick[]>([]);
  const [layout, setLayout] = useState<"a4_24" | "a4_65" | "roll_50x25">("a4_24");
  const [mrp, setMrp] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data } = useProducts({ q: q.trim() });
  const add = (p: Product) => setPicks((cur) => [
    ...cur,
    ...p.variants.filter((v) => !cur.some((c) => c.variantId === v.id))
      .map((v) => ({ variantId: v.id, label: `${p.name}${v.name ? ` · ${v.name}` : ""}`, price: v.sale_price, copies: 1 })),
  ]);
  const setCopies = (id: string, n: number) => setPicks((cur) => cur.map((c) => (c.variantId === id ? { ...c, copies: Math.max(1, Math.min(500, n)) } : c)));

  async function print() {
    setBusy(true); setError(null);
    try {
      const blob = await api<Blob>("/products/labels", { method: "POST", blob: true, json: { layout, show_mrp: mrp, items: picks.map((p) => ({ variant_id: p.variantId, copies: p.copies })) } });
      window.open(URL.createObjectURL(blob), "_blank", "noopener");
    } catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't make labels."); }
    finally { setBusy(false); }
  }

  return (
    <>
      <Back />
      <PageHeader title="Barcode labels" description="Print price stickers with barcodes for shelves and products." />
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <Section title="Choose items">
          <label className="relative block">
            <span className="sr-only">Search items</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-text-3" aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search items" className="h-11 w-full rounded-lg border border-border-strong bg-surface pl-10 pr-3" />
          </label>
          <ul className="max-h-96 divide-y divide-border overflow-auto">
            {data?.items.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-3 py-2.5">
                <span><span className="font-medium">{p.name}</span><span className="block text-sm text-text-2">{p.variants.length > 1 ? `${p.variants.length} variants` : formatINR(p.variants[0]?.sale_price ?? 0)}</span></span>
                <Button variant="soft" size="md" onClick={() => add(p)}><Plus className="h-4 w-4" aria-hidden />Add</Button>
              </li>
            ))}
          </ul>
        </Section>
        <Section title={`Labels (${picks.reduce((n, p) => n + p.copies, 0)})`}
          footer={<Button loading={busy} disabled={!picks.length} onClick={() => void print()}><Printer className="h-4 w-4" aria-hidden />Make PDF</Button>}>
          <FormError message={error} />
          {!picks.length ? <p className="text-text-2">Add items from the list.</p> : (
            <ul className="divide-y divide-border">
              {picks.map((p) => (
                <li key={p.variantId} className="flex items-center gap-2 py-2">
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{p.label}</span>
                  <button onClick={() => setCopies(p.variantId, p.copies - 1)} className="grid h-8 w-8 place-items-center rounded-md border border-border" aria-label="Fewer"><Minus className="h-3.5 w-3.5" /></button>
                  <input value={p.copies} onChange={(e) => setCopies(p.variantId, Number(e.target.value) || 1)} className="tnum h-8 w-12 rounded-md border border-border text-center" aria-label="Copies" />
                  <button onClick={() => setCopies(p.variantId, p.copies + 1)} className="grid h-8 w-8 place-items-center rounded-md border border-border" aria-label="More"><Plus className="h-3.5 w-3.5" /></button>
                  <button onClick={() => setPicks((c) => c.filter((x) => x.variantId !== p.variantId))} className="px-1 text-text-3 hover:text-danger" aria-label="Remove"><XCircle className="h-4 w-4" /></button>
                </li>
              ))}
            </ul>
          )}
          <label className="block">
            <span className="mb-1.5 block text-sm font-semibold">Sheet</span>
            <select value={layout} onChange={(e) => setLayout(e.target.value as typeof layout)} className="h-11 w-full rounded-md border border-border-strong bg-surface px-3">
              <option value="a4_24">A4, 24 per sheet (70 × 37 mm)</option>
              <option value="a4_65">A4, 65 per sheet (38 × 21 mm)</option>
              <option value="roll_50x25">Label printer roll (50 × 25 mm)</option>
            </select>
          </label>
          <Toggle checked={mrp} onChange={setMrp} label="Show MRP when it's higher than the price" />
        </Section>
      </div>
    </>
  );
}

export function StockPage() {
  const [tab, setTab] = useState<"low" | "history" | "value">("low");
  const low = useQuery({ queryKey: ["low"], queryFn: () => api<{ items: Product[] }>("/stock/low") });
  const value = useQuery({ queryKey: ["valuation"], queryFn: () => api<{ rows: { category: string; items: number; quantity: string; value: string }[]; total_value: string }>("/stock/valuation"), enabled: tab === "value" });
  const history = useMovements();
  const tabs = [["low", "Low stock"], ["history", "Stock history"], ["value", "Stock value"]] as const;
  return (
    <>
      <Back />
      <PageHeader title="Stock" />
      <nav className="mb-6 flex gap-1 border-b border-border" aria-label="Stock views">
        {tabs.map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)} aria-current={tab === k}
            className={`-mb-px border-b-2 px-4 py-2.5 font-medium ${tab === k ? "border-primary text-primary" : "border-transparent text-text-2 hover:text-text"}`}>{label}</button>
        ))}
      </nav>
      {tab === "low" && (low.data?.items.length ? (
        <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
          {low.data.items.flatMap((p) => p.variants.filter(isLow).map((v) => (
            <li key={v.id}><Link to={`/app/items/${p.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-surface-2">
              <span className="font-medium">{p.name}{v.name ? ` · ${v.name}` : ""}</span>
              <span className="tnum text-sm"><span className="font-semibold text-warning">{qtyFmt(v.stock_qty)}</span><span className="text-text-2"> left · alert at {qtyFmt(v.reorder_level)}</span></span>
            </Link></li>
          )))}
        </ul>
      ) : <p className="rounded-xl bg-success-soft p-5 text-success">Nothing is running low. Nice.</p>)}
      {tab === "history" && (
        <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
          {history.data?.map((m) => (
            <li key={m.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
              <span><span className="font-medium">{m.product_name}{m.variant_name ? ` · ${m.variant_name}` : ""}</span>
                <span className="block capitalize text-text-2">{m.kind.replace("_", " ")}{m.reason ? ` · ${m.reason}` : ""} · {new Date(m.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}{m.created_by_name ? ` · ${m.created_by_name}` : ""}</span></span>
              <span className={`tnum font-semibold ${Number(m.qty) < 0 ? "text-danger" : "text-success"}`}>{Number(m.qty) > 0 ? "+" : ""}{qtyFmt(m.qty)}</span>
            </li>
          ))}
          {!history.data?.length && <li className="p-5 text-text-2">No stock changes yet.</li>}
        </ul>
      )}
      {tab === "value" && value.data && (
        <Section title={`Stock value ${formatINR(value.data.total_value, { always: true })}`} description="Quantity in stock × cost price.">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-text-2"><th className="py-2 font-medium">Category</th><th className="font-medium">Items</th><th className="text-right font-medium">Value</th></tr></thead>
            <tbody className="divide-y divide-border">
              {value.data.rows.map((r) => <tr key={r.category}><td className="py-2.5">{r.category}</td><td className="tnum">{r.items}</td><td className="tnum text-right font-semibold">{formatINR(r.value, { always: true })}</td></tr>)}
            </tbody>
          </table>
        </Section>
      )}
    </>
  );
}

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useCategories } from "@/features/items/api";
import { cell, dayTime } from "@/features/money/api";
import { useHidScanner } from "@/features/pos/inputs";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Badge, useToast } from "@/ui/primitives";

interface CountRow { id: string; name: string; status: "open" | "posted" | "cancelled"; created_at: string; counted: number; items: number; started_by_name: string | null }
interface Count extends CountRow {
  variance_value: string;
  lines: { variant_id: string; name: string; variant_name: string | null; barcode: string | null; unit_code: string; expected_qty: string; counted_qty: string | null; variance_qty: string | null; variance_value: string | null }[];
}
const qtyFmt = (v: string | null) => (v === null ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 3 }));

export function StockCountPanel() {
  return (
    <Routes>
      <Route index element={<CountList />} />
      <Route path=":id" element={<CountSheet />} />
    </Routes>
  );
}

function CountList() {
  const navigate = useNavigate();
  const toast = useToast((s) => s.show);
  const { data } = useQuery({ queryKey: ["counts"], queryFn: () => api<CountRow[]>("/stock-counts") });
  const cats = useCategories();
  const [cat, setCat] = useState("");
  async function start() {
    try {
      const c = await api<Count>("/stock-counts", { method: "POST", json: { name: cat ? `Count · ${cats.data?.find((x) => x.id === cat)?.name}` : "Full stock count", category_id: cat || null } });
      navigate(c.id);
    } catch (e) { toast(e instanceof ApiError ? e.message : "Couldn't start."); }
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-surface p-4">
        <p className="flex-1 text-text-2">Count what's on the shelf. Items you don't count are left alone.</p>
        <select value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Category" className={cell}>
          <option value="">All items</option>
          {cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <Button size="md" onClick={() => void start()}>Start count</Button>
      </div>
      {!!data?.length && (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
          {data.map((c) => (
            <li key={c.id}><Link to={c.id} className="flex items-center gap-3 px-4 py-3 hover:bg-surface-2">
              <div className="flex-1"><p className="font-medium">{c.name}</p><p className="text-sm text-text-2">{dayTime(c.created_at)} · {c.counted} of {c.items} counted</p></div>
              <Badge tone={c.status === "posted" ? "success" : c.status === "open" ? "brand" : "neutral"}>{c.status === "open" ? "In progress" : c.status === "posted" ? "Posted" : "Cancelled"}</Badge>
            </Link></li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CountSheet() {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const { data: c } = useQuery({ queryKey: ["count", id], queryFn: () => api<Count>(`/stock-counts/${id}`) });
  const [filter, setFilter] = useState("");
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["count", id] }); void qc.invalidateQueries({ queryKey: ["counts"] }); };
  async function setLine(body: object) {
    try { await api(`/stock-counts/${id}/lines`, { method: "POST", json: body }); refresh(); }
    catch (e) { toast(e instanceof ApiError ? e.message : "Couldn't save."); }
  }
  useHidScanner((code) => void setLine({ code, add: "1" }), c?.status === "open"); // each scan counts one
  async function finish(action: "post" | "cancel") {
    try { await api(`/stock-counts/${id}/${action}`, { method: "POST" }); refresh(); void qc.invalidateQueries({ queryKey: ["products"] }); toast(action === "post" ? "Stock updated" : "Count cancelled"); if (action === "cancel") navigate(".."); }
    catch (e) { toast(e instanceof ApiError ? e.message : "Couldn't save."); }
  }
  if (!c) return <p className="text-text-2">Loading…</p>;
  const open = c.status === "open";
  const shown = c.lines.filter((l) => !filter || l.name.toLowerCase().includes(filter.toLowerCase()) || l.barcode === filter);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="text-lg font-bold">{c.name}</h2><p className="text-sm text-text-2">{c.counted} of {c.lines.length} counted · difference {formatINR(c.variance_value, { always: true })} at cost</p></div>
        {open && <div className="flex gap-2"><Button size="md" variant="ghost" onClick={() => void finish("cancel")}>Cancel</Button><Button size="md" disabled={!c.counted} onClick={() => void finish("post")}>Post count</Button></div>}
      </div>
      {open && <input value={filter} onChange={(e) => setFilter(e.target.value)} data-scan-target="" placeholder="Find an item (or just scan barcodes: each scan adds 1)" aria-label="Find item" className={`${cell} h-12 w-full`} />}
      <div className="overflow-x-auto rounded-xl border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="text-left text-text-2"><tr className="border-b border-border"><th className="px-4 py-2 font-medium">Item</th><th className="px-4 py-2 text-right font-medium">System</th><th className="px-4 py-2 font-medium">Counted</th><th className="px-4 py-2 text-right font-medium">Difference</th></tr></thead>
          <tbody className="tnum divide-y divide-border">
            {shown.map((l) => (
              <tr key={l.variant_id}>
                <td className="px-4 py-2">{l.name}{l.variant_name && <span className="text-text-2"> · {l.variant_name}</span>}</td>
                <td className="px-4 py-2 text-right text-text-2">{qtyFmt(l.expected_qty)}</td>
                <td className="px-4 py-2">{open
                  ? <input defaultValue={l.counted_qty === null ? "" : String(Number(l.counted_qty))} key={l.counted_qty ?? "none"} inputMode="decimal" aria-label={`Counted ${l.name}`}
                      onBlur={(e) => e.target.value.trim() !== "" && Number(e.target.value) !== Number(l.counted_qty) && void setLine({ variant_id: l.variant_id, counted_qty: e.target.value.trim() })}
                      className={`${cell} w-24`} />
                  : qtyFmt(l.counted_qty)}</td>
                <td className={`px-4 py-2 text-right ${Number(l.variance_qty) < 0 ? "text-danger" : Number(l.variance_qty) > 0 ? "text-success" : "text-text-2"}`}>
                  {l.variance_qty === null ? "" : `${Number(l.variance_qty) > 0 ? "+" : ""}${qtyFmt(l.variance_qty)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

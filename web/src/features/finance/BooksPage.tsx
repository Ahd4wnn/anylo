import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, Upload } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Badge, Dialog, Section, useToast } from "@/ui/primitives";

const rupees = (v: string | number) => formatINR(String(v), { always: true });
const cell = "h-12 w-full rounded-lg border border-border-strong bg-surface px-3";
const err = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);
const today = () => new Date().toLocaleDateString("en-CA");

type Line = { name: string; amount: string };
interface Position {
  as_of: string; books_start: string; assets: Line[]; liabilities: Line[]; capital: Line[];
  total_assets: string; total_liabilities_capital: string; note: string;
  trial_balance: { account: string; debit: string; credit: string }[]; trial_totals: { debit: string; credit: string };
}
interface Bank { id: string; name: string; account_last4: string | null; is_default: boolean; book_balance: string; statement_balance: string; unmatched: number }
interface Asset { id: string; name: string; block: string; cost: string; bought_on: string; sold_on: string | null; rate: number; opening: string; depreciation: string; closing: string }
interface Due { return_type: string; name: string; period: string; due_on: string; status: "filed" | "overdue" | "due_soon" | "upcoming"; arn: string | null }

function Rows({ lines }: { lines: Line[] }) {
  return <>{lines.map((l) => <div key={l.name} className="flex justify-between gap-3 py-1.5"><span className="text-text-2">{l.name}</span><span className="tnum">{rupees(l.amount)}</span></div>)}</>;
}

export function Books() {
  const can = useAuth((s) => s.can);
  const [asOf, setAsOf] = useState(today());
  const { data: p } = useQuery({ queryKey: ["position", asOf], queryFn: () => api<Position>(`/books/position?as_of=${asOf}`) });
  const [tb, setTb] = useState(false);
  return (
    <div className="space-y-6">
      <Section title="Balance sheet" description={p ? `What the shop owns and owes, from ${p.books_start}.` : undefined}>
        <label className="mb-4 flex items-center gap-2 text-sm font-semibold">As on<input type="date" value={asOf} max={today()} onChange={(e) => setAsOf(e.target.value)} className="h-10 rounded-lg border border-border-strong bg-surface px-3 font-normal" /></label>
        {p && (
          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <h3 className="mb-1 font-semibold">Owns</h3><Rows lines={p.assets} />
              <div className="mt-2 flex justify-between border-t border-border pt-2 font-semibold"><span>Total</span><span className="tnum">{rupees(p.total_assets)}</span></div>
            </div>
            <div>
              <h3 className="mb-1 font-semibold">Owes</h3><Rows lines={p.liabilities} />
              <h3 className="mb-1 mt-3 font-semibold">Owner's capital</h3><Rows lines={p.capital} />
              <div className="mt-2 flex justify-between border-t border-border pt-2 font-semibold"><span>Total</span><span className="tnum">{rupees(p.total_liabilities_capital)}</span></div>
            </div>
          </div>
        )}
        {p && <p className="mt-4 text-sm text-text-2">{p.note}</p>}
        <button onClick={() => setTb(!tb)} className="mt-3 text-sm font-semibold text-primary hover:underline">{tb ? "Hide" : "Show"} trial balance</button>
        {tb && p && (
          <table className="tnum mt-3 w-full text-sm">
            <thead className="text-left text-text-2"><tr className="border-b border-border"><th className="py-2 font-medium">Account</th><th className="py-2 text-right font-medium">Debit</th><th className="py-2 text-right font-medium">Credit</th></tr></thead>
            <tbody className="divide-y divide-border">{p.trial_balance.map((r) => <tr key={r.account}><td className="py-2">{r.account}</td><td className="py-2 text-right">{Number(r.debit) ? rupees(r.debit) : ""}</td><td className="py-2 text-right">{Number(r.credit) ? rupees(r.credit) : ""}</td></tr>)}</tbody>
            <tfoot className="border-t-2 border-border font-semibold"><tr><td className="py-2">Total</td><td className="py-2 text-right">{rupees(p.trial_totals.debit)}</td><td className="py-2 text-right">{rupees(p.trial_totals.credit)}</td></tr></tfoot>
          </table>
        )}
      </Section>
      <Banks />
      <OwnerMoney />
      <Assets />
      {can("books.lock") && <YearClose />}
    </div>
  );
}

function Banks() {
  const can = useAuth((s) => s.can);
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const { data } = useQuery({ queryKey: ["banks"], queryFn: () => api<Bank[]>("/books/banks") });
  const [adding, setAdding] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const [target, setTarget] = useState<string | null>(null);
  async function upload(f: File) {
    const body = new FormData(); body.append("file", f);
    try {
      const r = await api<{ added: number; matched: number }>(`/books/banks/${target}/statement`, { method: "POST", body });
      toast(`${r.added} new lines, ${r.matched} matched.`);
      void qc.invalidateQueries({ queryKey: ["banks"] });
    } catch (e) { toast(err(e, "Couldn't read that statement.")); }
  }
  return (
    <Section title="Bank accounts" description="Upload the bank statement (CSV or Excel). Anylo matches each line with your UPI, card and bank entries.">
      <input ref={file} type="file" accept=".csv,.xlsx" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
      <div className="space-y-2">
        {data?.map((b) => (
          <div key={b.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-3">
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{b.name}{b.account_last4 && <span className="text-text-2"> ··{b.account_last4}</span>} {b.is_default && <Badge>Default</Badge>}</p>
              <p className="text-sm text-text-2">In Anylo {rupees(b.book_balance)} · Statement {rupees(b.statement_balance)}{b.unmatched > 0 && ` · ${b.unmatched} to check`}</p>
            </div>
            {can("books.manage") && <Button size="md" variant="secondary" onClick={() => { setTarget(b.id); file.current?.click(); }}><Upload className="h-4 w-4" aria-hidden />Statement</Button>}
          </div>
        ))}
        {data?.length === 0 && <p className="text-text-2">No bank account yet. UPI and card money is counted together until you add one.</p>}
      </div>
      {can("books.manage") && <Button size="md" variant="secondary" className="mt-3" onClick={() => setAdding(true)}>Add bank account</Button>}
      {adding && <BankDialog onClose={() => setAdding(false)} />}
    </Section>
  );
}

function BankDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(null);
    const f = new FormData(e.currentTarget);
    try {
      await api("/books/banks", { method: "POST", json: { name: f.get("name"), account_last4: f.get("last4") || null, opening_balance: f.get("opening") || "0" } });
      void qc.invalidateQueries({ queryKey: ["banks"] }); onClose();
    } catch (e2) { setError(err(e2, "Couldn't save.")); }
  }
  return (
    <Dialog open onClose={onClose} title="Add bank account">
      <form onSubmit={submit} className="space-y-4">
        <FormError message={error} />
        <input name="name" required placeholder="Bank name, like SBI Current" aria-label="Bank name" className={cell} />
        <input name="last4" inputMode="numeric" maxLength={4} pattern="[0-9]{4}" placeholder="Last 4 digits of account (optional)" aria-label="Last 4 digits" className={cell} />
        <input name="opening" inputMode="decimal" placeholder="Balance on the books start date" aria-label="Opening balance" className={cell} />
        <Button type="submit" className="w-full">Save</Button>
      </form>
    </Dialog>
  );
}

function OwnerMoney() {
  const can = useAuth((s) => s.can);
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const { data } = useQuery({ queryKey: ["owner-money"], queryFn: () => api<{ items: { id: string; kind: string; amount: string; method: string; occurred_at: string; note: string | null }[]; capital: string; drawings: string }>("/books/owner") });
  const [kind, setKind] = useState<"capital" | "drawing">("capital");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  async function add(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/books/owner", { method: "POST", json: { kind, amount, method } });
      setAmount(""); void qc.invalidateQueries({ queryKey: ["owner-money"] }); void qc.invalidateQueries({ queryKey: ["position"] });
    } catch (e2) { toast(err(e2, "Couldn't save.")); }
  }
  async function remove(id: string) { await api(`/books/owner/${id}`, { method: "DELETE" }); void qc.invalidateQueries({ queryKey: ["owner-money"] }); void qc.invalidateQueries({ queryKey: ["position"] }); }
  return (
    <Section title="Owner's money" description="Money you put into the shop, and money you take home. Taking money home is not an expense.">
      {data && <p className="mb-3 text-sm">Put in <b className="tnum">{rupees(data.capital)}</b> · Taken home <b className="tnum">{rupees(data.drawings)}</b></p>}
      {can("books.lock") && (
        <form onSubmit={add} className="mb-3 flex flex-wrap gap-2">
          <select value={kind} onChange={(e) => setKind(e.target.value as "capital" | "drawing")} aria-label="Type" className="h-11 rounded-lg border border-border-strong bg-surface px-3">
            <option value="capital">Put in</option><option value="drawing">Took home</option>
          </select>
          <input value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))} required inputMode="decimal" placeholder="Amount" aria-label="Amount" className="h-11 w-32 rounded-lg border border-border-strong bg-surface px-3" />
          <select value={method} onChange={(e) => setMethod(e.target.value)} aria-label="Paid by" className="h-11 rounded-lg border border-border-strong bg-surface px-3">
            {["cash", "upi", "bank", "cheque"].map((m) => <option key={m} value={m}>{m.toUpperCase()}</option>)}
          </select>
          <Button size="md" type="submit" disabled={!amount}>Add</Button>
        </form>
      )}
      <ul className="divide-y divide-border">
        {data?.items.slice(0, 10).map((r) => (
          <li key={r.id} className="flex items-center gap-3 py-2 text-sm">
            <span className="flex-1">{r.kind === "capital" ? "Put in" : "Took home"} · {r.method.toUpperCase()} · {new Date(r.occurred_at).toLocaleDateString("en-IN")}</span>
            <span className="tnum font-semibold">{rupees(r.amount)}</span>
            {can("books.lock") && <button onClick={() => void remove(r.id)} aria-label="Remove" className="text-text-3 hover:text-danger"><Trash2 className="h-4 w-4" /></button>}
          </li>
        ))}
      </ul>
    </Section>
  );
}

const BLOCKS = [["furniture", "Furniture & fittings (10%)"], ["plant", "Machinery, fridge, AC (15%)"], ["computer", "Computer, printer (40%)"], ["vehicle", "Vehicle (15%)"], ["building", "Building (10%)"]];

function Assets() {
  const can = useAuth((s) => s.can);
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["assets"], queryFn: () => api<{ fy: string; items: Asset[]; totals: Record<string, string> }>("/books/assets") });
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(null);
    const f = new FormData(e.currentTarget);
    try {
      await api("/books/assets", { method: "POST", json: { name: f.get("name"), block: f.get("block"), cost: f.get("cost"), bought_on: f.get("on"), paid_method: f.get("paid") || null } });
      void qc.invalidateQueries({ queryKey: ["assets"] }); void qc.invalidateQueries({ queryKey: ["position"] }); setAdding(false);
    } catch (e2) { setError(err(e2, "Couldn't save.")); }
  }
  async function remove(id: string) { await api(`/books/assets/${id}`, { method: "DELETE" }); void qc.invalidateQueries({ queryKey: ["assets"] }); void qc.invalidateQueries({ queryKey: ["position"] }); }
  return (
    <Section title="Fixed assets" description={data ? `Things the shop owns for years. Depreciation for FY ${data.fy}, income-tax rates.` : undefined}>
      <ul className="divide-y divide-border">
        {data?.items.map((a) => (
          <li key={a.id} className="flex items-center gap-3 py-2 text-sm">
            <span className="flex-1"><b>{a.name}</b> · bought {a.bought_on} for {rupees(a.cost)}{a.sold_on && ` · sold ${a.sold_on}`}</span>
            <span className="tnum text-text-2">Dep. {rupees(a.depreciation)}</span>
            <span className="tnum font-semibold">{rupees(a.closing)}</span>
            {can("books.manage") && <button onClick={() => void remove(a.id)} aria-label={`Remove ${a.name}`} className="text-text-3 hover:text-danger"><Trash2 className="h-4 w-4" /></button>}
          </li>
        ))}
      </ul>
      {data?.items.length === 0 && <p className="text-text-2">Add the counter, fridge, computer or vehicle so their wear shows in profit.</p>}
      {can("books.manage") && <Button size="md" variant="secondary" className="mt-3" onClick={() => setAdding(true)}>Add asset</Button>}
      {adding && (
        <Dialog open onClose={() => setAdding(false)} title="Add asset">
          <form onSubmit={submit} className="space-y-4">
            <FormError message={error} />
            <input name="name" required placeholder="What is it?" aria-label="Asset name" className={cell} />
            <select name="block" aria-label="Type" className={cell}>{BLOCKS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            <input name="cost" required inputMode="decimal" placeholder="Cost" aria-label="Cost" className={cell} />
            <label className="block text-sm font-semibold">Bought on<input name="on" type="date" required max={today()} defaultValue={today()} className={`${cell} mt-1 font-normal`} /></label>
            <select name="paid" aria-label="Paid now by" className={cell}>
              <option value="">Already paid before the books start</option>
              {["cash", "upi", "bank", "cheque"].map((m) => <option key={m} value={m}>Paid now by {m.toUpperCase()}</option>)}
            </select>
            <Button type="submit" className="w-full">Save</Button>
          </form>
        </Dialog>
      )}
    </Section>
  );
}

function YearClose() {
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const { data } = useQuery({ queryKey: ["locks"], queryFn: () => api<{ fy: string; locked_until: string }[]>("/books/locks") });
  const y = new Date().getMonth() >= 3 ? new Date().getFullYear() : new Date().getFullYear() - 1;
  const last = `${y - 1}-${String(y % 100).padStart(2, "0")}`;
  async function run(method: "POST" | "DELETE", fy: string) {
    try { await api(method === "POST" ? "/books/locks" : `/books/locks/${fy}`, { method, json: method === "POST" ? { fy } : undefined }); void qc.invalidateQueries({ queryKey: ["locks"] }); }
    catch (e) { toast(err(e, "Couldn't change that.")); }
  }
  const closed = new Set(data?.map((l) => l.fy));
  return (
    <Section title="Close the year" description="After your CA files the return, close the year so nothing dated in it can change.">
      <ul className="space-y-2">
        {data?.map((l) => <li key={l.fy} className="flex items-center gap-3 text-sm"><Badge tone="success">Closed</Badge><span className="flex-1">FY {l.fy}</span><button onClick={() => void run("DELETE", l.fy)} className="font-semibold text-primary hover:underline">Reopen</button></li>)}
      </ul>
      {!closed.has(last) && <Button size="md" variant="secondary" className="mt-3" onClick={() => void run("POST", last)}>Close FY {last}</Button>}
    </Section>
  );
}

const STATUS: Record<Due["status"], { label: string; tone: "success" | "warning" | "brand" | "neutral" }> = {
  filed: { label: "Filed", tone: "success" }, overdue: { label: "Overdue", tone: "warning" }, due_soon: { label: "Due soon", tone: "brand" }, upcoming: { label: "Upcoming", tone: "neutral" },
};

export function Filings() {
  const can = useAuth((s) => s.can);
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["calendar"], queryFn: () => api<Due[]>("/books/calendar") });
  const [filing, setFiling] = useState<Due | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(null);
    const f = new FormData(e.currentTarget);
    try {
      await api("/books/filings", { method: "POST", json: { return_type: filing!.return_type, period: filing!.period, filed_on: f.get("on"), arn: f.get("arn") || null, tax_paid: f.get("tax") || "0", method: "bank" } });
      void qc.invalidateQueries({ queryKey: ["calendar"] }); setFiling(null);
    } catch (e2) { setError(err(e2, "Couldn't save.")); }
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-text-2">Standard due dates. The government sometimes extends them; your CA will know.</p>
      <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
        {data?.map((d) => (
          <li key={`${d.return_type}-${d.period}`} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1"><p className="font-semibold">{d.name} <span className="font-normal text-text-2">· {d.period}</span></p><p className="text-sm text-text-2">Due {new Date(d.due_on).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}{d.arn && ` · ARN ${d.arn}`}</p></div>
            <Badge tone={STATUS[d.status].tone}>{STATUS[d.status].label}</Badge>
            {can("books.manage") && d.status !== "filed" && <Button size="md" variant="secondary" onClick={() => setFiling(d)}>Mark filed</Button>}
          </li>
        ))}
      </ul>
      {filing && (
        <Dialog open onClose={() => setFiling(null)} title={`${filing.name} · ${filing.period}`}>
          <form onSubmit={submit} className="space-y-4">
            <FormError message={error} />
            <label className="block text-sm font-semibold">Filed on<input name="on" type="date" required max={today()} defaultValue={today()} className={`${cell} mt-1 font-normal`} /></label>
            <input name="arn" placeholder="ARN (optional)" aria-label="ARN" className={cell} />
            <input name="tax" inputMode="decimal" placeholder="Tax paid with it (optional)" aria-label="Tax paid" className={cell} />
            <Button type="submit" className="w-full">Save</Button>
          </form>
        </Dialog>
      )}
    </div>
  );
}

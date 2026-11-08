import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { formatINR } from "@/lib/money";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { Dialog, useToast } from "@/ui/primitives";
import { cell, day, todayIso, type Worker } from "./api";

const rupees = (v: string | number) => formatINR(String(v), { always: true });
const MARKS = [["present", "P", "Present"], ["half_day", "½", "Half day"], ["absent", "A", "Absent"]] as const;

export function LabourPanel() {
  const can = useAuth((s) => s.can);
  const manage = can("labour.manage");
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const { data } = useQuery({ queryKey: ["workers"], queryFn: () => api<{ items: Worker[]; balance_to_pay: string }>("/labour/workers") });
  const [editing, setEditing] = useState<Worker | "new" | null>(null);
  const [paying, setPaying] = useState<Worker | null>(null);
  const [viewing, setViewing] = useState<Worker | null>(null);
  async function mark(w: Worker, status: string) {
    try {
      await api("/labour/attendance", { method: "POST", json: { labourer_id: w.id, day: todayIso(), status } });
      void qc.invalidateQueries({ queryKey: ["workers"] });
    } catch (e) { toast(e instanceof ApiError ? e.message : "Couldn't mark attendance."); }
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        {data && manage && <p className="font-semibold">Wages to pay: {rupees(data.balance_to_pay)}</p>}
        {manage && <Button size="md" className="ml-auto" onClick={() => setEditing("new")}>Add worker</Button>}
      </div>
      {data && (data.items.length ? (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
          {data.items.map((w) => (
            <li key={w.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <button onClick={() => manage && setViewing(w)} className="min-w-0 flex-1 text-left">
                <p className="font-medium">{w.name}</p>
                <p className="truncate text-sm text-text-2">
                  {w.wage_type === "monthly" ? `${rupees(w.monthly_wage)}/month` : `${rupees(w.daily_wage)}/day`}
                  {manage && ` · earned ${rupees(w.earned)} · paid ${rupees(w.total_paid)}`}
                </p>
              </button>
              <div className="flex gap-1" role="radiogroup" aria-label={`${w.name} today`}>
                {MARKS.map(([s, short, label]) => (
                  <button key={s} role="radio" aria-checked={w.today === s} aria-label={label} title={label} onClick={() => void mark(w, s)}
                    className={`h-10 w-10 rounded-lg border font-semibold ${w.today === s ? (s === "absent" ? "border-danger bg-danger-soft text-danger" : "border-primary bg-primary-soft text-on-primary-soft") : "border-border hover:bg-surface-2"}`}>{short}</button>
                ))}
              </div>
              {manage && (
                <div className="flex items-center gap-2">
                  <p className={`tnum w-28 text-right font-semibold ${Number(w.balance_to_pay) < 0 ? "text-success" : ""}`} title={Number(w.balance_to_pay) < 0 ? "Paid in advance" : "Balance to pay"}>
                    {Number(w.balance_to_pay) < 0 ? `Adv ${rupees(-Number(w.balance_to_pay))}` : rupees(w.balance_to_pay)}
                  </p>
                  <Button size="md" variant="secondary" onClick={() => setPaying(w)}>Pay</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      ) : <p className="rounded-xl border border-dashed border-border-strong bg-surface p-8 text-center text-text-2">Add your workers to mark attendance and keep their wages straight.</p>)}
      <p className="text-sm text-text-2">P = present, ½ = half day, A = absent. Monthly workers: leaves beyond their paid leaves cost 1/30 of the salary each.</p>
      {editing && <WorkerDialog worker={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
      {paying && <PayDialog worker={paying} onClose={() => setPaying(null)} />}
      {viewing && <StatementDialog worker={viewing} onEdit={() => { setEditing(viewing); setViewing(null); }} onClose={() => setViewing(null)} />}
    </div>
  );
}

function WorkerDialog({ worker, onClose }: { worker?: Worker; onClose: () => void }) {
  const qc = useQueryClient();
  const [type, setType] = useState(worker?.wage_type ?? "daily");
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(null);
    const f = new FormData(e.currentTarget);
    const v = (k: string) => String(f.get(k) ?? "").trim();
    try {
      await api(worker ? `/labour/workers/${worker.id}` : "/labour/workers", { method: worker ? "PUT" : "POST", json: {
        name: v("name"), phone: v("phone") || null, aadhaar_last4: v("aadhaar") || null, gender: v("gender"), wage_type: type,
        daily_wage: type === "daily" ? v("wage") : "0", monthly_wage: type === "monthly" ? v("wage") : "0",
        paid_leaves_per_month: Number(v("leaves") || 0), joined_on: v("joined") || null, is_active: true,
      } });
      void qc.invalidateQueries({ queryKey: ["workers"] }); onClose();
    } catch (e2) { setError(e2 instanceof ApiError ? e2.message : "Couldn't save."); }
  }
  return (
    <Dialog open onClose={onClose} title={worker ? `Edit ${worker.name}` : "Add worker"}>
      <form onSubmit={submit} className="space-y-4">
        <FormError message={error} />
        <Field label="Name" name="name" required defaultValue={worker?.name} />
        <div className="grid grid-cols-2 gap-3">
          <Field label="Mobile (optional)" name="phone" inputMode="numeric" maxLength={10} defaultValue={worker?.phone ?? ""} />
          <Field label="Aadhaar last 4 (optional)" name="aadhaar" inputMode="numeric" maxLength={4} defaultValue={worker?.aadhaar_last4 ?? ""} hint="Only the last 4 digits are kept." />
        </div>
        <select name="gender" defaultValue={worker?.gender ?? "male"} aria-label="Gender" className={`${cell} h-12 w-full`}>
          <option value="male">Male</option><option value="female">Female</option><option value="other">Other</option>
        </select>
        <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Paid">
          {(["daily", "monthly"] as const).map((t) => (
            <button type="button" key={t} role="radio" aria-checked={type === t} onClick={() => setType(t)}
              className={`h-11 rounded-lg border font-semibold ${type === t ? "border-primary bg-primary-soft text-on-primary-soft" : "border-border hover:bg-surface-2"}`}>{t === "daily" ? "Daily wage" : "Monthly salary"}</button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label={type === "daily" ? "Wage per day ₹" : "Salary per month ₹"} name="wage" required inputMode="decimal"
            defaultValue={worker ? (worker.wage_type === "monthly" ? worker.monthly_wage : worker.daily_wage) : ""} />
          {type === "monthly" && <Field label="Paid leaves per month" name="leaves" inputMode="numeric" defaultValue={String(worker?.paid_leaves_per_month ?? 0)} />}
        </div>
        <Field label="Joined on" name="joined" type="date" max={todayIso()} defaultValue={worker?.joined_on ?? todayIso()} />
        <Button type="submit" className="w-full">Save</Button>
      </form>
    </Dialog>
  );
}

function PayDialog({ worker, onClose }: { worker: Worker; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const owed = Math.max(0, Number(worker.balance_to_pay));
  const [kind, setKind] = useState<"wage" | "advance">(owed > 0 ? "wage" : "advance");
  const [cash, setCash] = useState(owed ? owed.toFixed(2) : "");
  const [upi, setUpi] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(null);
    try {
      await api("/labour/payments", { method: "POST", json: { labourer_id: worker.id, kind, cash_amount: cash || "0", upi_amount: upi || "0", note: String(new FormData(e.currentTarget).get("note") || "") || null } });
      void qc.invalidateQueries({ queryKey: ["workers"] }); void qc.invalidateQueries({ queryKey: ["cash"] });
      toast(`Paid ${worker.name}`); onClose();
    } catch (e2) { setError(e2 instanceof ApiError ? e2.message : "Couldn't save."); }
  }
  return (
    <Dialog open onClose={onClose} title={`Pay ${worker.name}`}>
      <form onSubmit={submit} className="space-y-4">
        <FormError message={error} />
        <p className="text-text-2">Earned {rupees(worker.earned)} · paid {rupees(worker.total_paid)} · {owed > 0 ? `owed ${rupees(owed)}` : "nothing owed now"}</p>
        <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Payment type">
          {(["wage", "advance"] as const).map((k) => (
            <button type="button" key={k} role="radio" aria-checked={kind === k} onClick={() => setKind(k)}
              className={`h-11 rounded-lg border font-semibold ${kind === k ? "border-primary bg-primary-soft text-on-primary-soft" : "border-border hover:bg-surface-2"}`}>{k === "wage" ? "Wages" : "Advance"}</button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Cash ₹" value={cash} onChange={(e) => setCash(e.target.value.replace(/[^\d.]/g, ""))} inputMode="decimal" />
          <Field label="UPI ₹" value={upi} onChange={(e) => setUpi(e.target.value.replace(/[^\d.]/g, ""))} inputMode="decimal" />
        </div>
        <Field label="Note (optional)" name="note" />
        <Button type="submit" className="w-full" disabled={!Number(cash) && !Number(upi)}>Pay {rupees(Number(cash || 0) + Number(upi || 0))}</Button>
      </form>
    </Dialog>
  );
}

interface Statement { worker: Worker; attendance: { day: string; status: string }[]; payments: { id: string; kind: string; amount: string; paid_on: string; cash_amount: string; upi_amount: string; note: string | null }[] }

function StatementDialog({ worker, onEdit, onClose }: { worker: Worker; onEdit: () => void; onClose: () => void }) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["worker", worker.id], queryFn: () => api<Statement>(`/labour/workers/${worker.id}/statement`) });
  async function undo(id: string) {
    await api(`/labour/payments/${id}`, { method: "DELETE" });
    void qc.invalidateQueries({ queryKey: ["worker", worker.id] }); void qc.invalidateQueries({ queryKey: ["workers"] }); void qc.invalidateQueries({ queryKey: ["cash"] });
  }
  const w = data?.worker ?? worker;
  return (
    <Dialog open onClose={onClose} title={w.name}>
      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div><p className="text-text-2">Earned</p><p className="tnum font-semibold">{rupees(w.earned)}</p></div>
          <div><p className="text-text-2">Paid</p><p className="tnum font-semibold">{rupees(w.total_paid)}</p></div>
          <div><p className="text-text-2">{Number(w.balance_to_pay) < 0 ? "Advance" : "To pay"}</p><p className="tnum font-semibold">{rupees(Math.abs(Number(w.balance_to_pay)))}</p></div>
        </div>
        {w.wage_type === "monthly" && <p className="text-sm text-text-2">This month: {w.leaves_this_month} leaves, {w.unpaid_leaves_this_month} unpaid{w.accrued_through ? ` · counted up to ${day(w.accrued_through)}` : ""}</p>}
        <div>
          <h3 className="mb-1 text-sm font-semibold">Recent attendance</h3>
          <div className="flex flex-wrap gap-1">
            {data?.attendance.slice(0, 31).map((a) => (
              <span key={a.day} title={`${day(a.day)}: ${a.status.replace("_", " ")}`}
                className={`grid h-8 w-8 place-items-center rounded text-xs font-semibold ${a.status === "present" ? "bg-success-soft text-success" : a.status === "half_day" ? "bg-warning-soft text-warning" : "bg-danger-soft text-danger"}`}>
                {new Date(a.day).getDate()}
              </span>
            ))}
          </div>
        </div>
        <div>
          <h3 className="mb-1 text-sm font-semibold">Payments</h3>
          <ul className="divide-y divide-border text-sm">
            {data?.payments.map((p) => (
              <li key={p.id} className="flex items-center gap-2 py-2">
                <span className="flex-1">{day(p.paid_on)} · {p.kind === "advance" ? "Advance" : "Wages"}{p.note ? ` · ${p.note}` : ""}</span>
                <span className="tnum font-medium">{rupees(p.amount)}</span>
                <button onClick={() => void undo(p.id)} className="text-xs font-semibold text-text-3 hover:text-danger">Undo</button>
              </li>
            ))}
          </ul>
        </div>
        <Button variant="secondary" className="w-full" onClick={onEdit}>Edit worker</Button>
      </div>
    </Dialog>
  );
}

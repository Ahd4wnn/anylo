import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { useStaff, type Staff } from "@/features/shop/api";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { Select } from "@/ui/Select";
import { Badge, Dialog, Section, useToast } from "@/ui/primitives";

type Created = Staff & { temporary_password: string };

function Credentials({ created, onDone }: { created: Created; onDone: () => void }) {
  const toast = useToast((s) => s.show);
  const text = `Anylo login\nEmail: ${created.email}\nTemporary password: ${created.temporary_password}`;
  return (
    <div className="space-y-4">
      <p className="text-text-2">Share these with <span className="font-semibold text-text">{created.full_name}</span>. They'll choose their own password after logging in. <span className="font-medium text-text">This password is shown only once.</span></p>
      <div className="rounded-lg bg-tint p-4 font-mono text-[15px] leading-7">
        <div>Email: {created.email}</div>
        <div>Password: <span className="font-bold tracking-wider">{created.temporary_password}</span></div>
      </div>
      <div className="flex gap-3">
        <Button variant="secondary" size="md" className="flex-1" onClick={() => { void navigator.clipboard.writeText(text); toast("Copied"); }}>
          <Copy className="h-4 w-4" aria-hidden />Copy
        </Button>
        <Button size="md" className="flex-1" onClick={onDone}>Done</Button>
      </div>
    </div>
  );
}

export function AddStaffForm({ onCreated }: { onCreated: (c: Created) => void }) {
  const canManagers = useAuth((s) => s.can("staff.managers"));
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: (body: Record<string, string | null>) => api<Created>("/shop/staff", { method: "POST", json: body }),
    onSuccess: (c) => { void qc.invalidateQueries({ queryKey: ["staff"] }); onCreated(c); },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Couldn't add this person."),
  });
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    setError(null);
    create.mutate({ ...f, phone: f.phone?.trim() || null });
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <FormError message={error} />
      <Field label="Full name" name="full_name" required />
      <Field label="Email (used to log in)" name="email" type="email" required />
      <Field label="Mobile (optional)" name="phone" inputMode="numeric" maxLength={10} />
      <Select label="Role" name="role" defaultValue="salesperson"
        options={[{ value: "salesperson", label: "Salesperson: makes bills" }, ...(canManagers ? [{ value: "manager", label: "Manager: runs the shop" }] : [])]} />
      <Button type="submit" className="w-full" loading={create.isPending}><UserPlus className="h-4 w-4" aria-hidden />Add staff</Button>
    </form>
  );
}

export function StaffPanel() {
  const { data: staff = [], isLoading } = useStaff();
  const me = useAuth((s) => s.me);
  const canManagers = useAuth((s) => s.can("staff.managers"));
  const qc = useQueryClient();
  const toast = useToast((s) => s.show);
  const [adding, setAdding] = useState(false);
  const [created, setCreated] = useState<Created | null>(null);

  const update = useMutation({
    mutationFn: ({ id, ...body }: { id: string; is_active: boolean }) => api(`/shop/staff/${id}`, { method: "PATCH", json: body }),
    onSuccess: (_d, v) => { void qc.invalidateQueries({ queryKey: ["staff"] }); toast(v.is_active ? "Switched on" : "Switched off. They've been logged out."); },
  });
  const reset = useMutation({
    mutationFn: (id: string) => api<Created>(`/shop/staff/${id}/reset-password`, { method: "POST" }),
    onSuccess: (c) => { setCreated(c); setAdding(true); },
  });

  return (
    <Section title="Staff" description="Each person gets their own login, so every bill shows who made it."
      footer={<Button size="md" onClick={() => { setCreated(null); setAdding(true); }}><UserPlus className="h-4 w-4" aria-hidden />Add staff</Button>}>
      {isLoading ? <p className="text-text-2">Loading…</p> : staff.length === 0 ? (
        <p className="rounded-lg bg-surface-2 p-5 text-center text-text-2">No staff yet. Add a salesperson so they can make bills on their own login.</p>
      ) : (
        <ul className="divide-y divide-border">
          {staff.map((s) => {
            const locked = s.role === "manager" && !canManagers;
            return (
              <li key={s.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary-soft font-semibold text-on-primary-soft">{s.full_name[0]}</div>
                <div className="min-w-0 flex-1">
                  <p className={`truncate font-medium ${s.is_active ? "" : "text-text-3 line-through"}`}>{s.full_name}</p>
                  <p className="truncate text-sm text-text-2">{s.email}</p>
                </div>
                <Badge tone={s.role === "manager" ? "brand" : "neutral"}>{s.role === "manager" ? "Manager" : "Salesperson"}</Badge>
                {s.must_change_password && s.is_active && <Badge tone="warning">Not logged in yet</Badge>}
                {!locked && s.id !== me?.user.id && (
                  <div className="flex gap-1">
                    <Button variant="ghost" size="md" onClick={() => reset.mutate(s.id)} aria-label={`New password for ${s.full_name}`}><KeyRound className="h-4 w-4" /></Button>
                    <Button variant="ghost" size="md" onClick={() => update.mutate({ id: s.id, is_active: !s.is_active })}>{s.is_active ? "Switch off" : "Switch on"}</Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <Dialog open={adding} onClose={() => setAdding(false)} title={created ? "Login details" : "Add staff"}>
        {created ? <Credentials created={created} onDone={() => setAdding(false)} /> : <AddStaffForm onCreated={setCreated} />}
      </Dialog>
    </Section>
  );
}

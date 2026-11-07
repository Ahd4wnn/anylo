import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Laptop, Smartphone } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { Section, useToast } from "@/ui/primitives";

const msg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Please try again.");

export function ChangePasswordForm({ onDone, submitLabel = "Change password" }: { onDone?: () => void; submitLabel?: string }) {
  const accept = useAuth((s) => s.acceptTokens);
  const toast = useToast((s) => s.show);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    if (f.get("new_password") !== f.get("confirm")) return setError("The two new passwords don't match.");
    if (String(f.get("new_password")).length < 8) return setError("Use at least 8 characters.");
    setError(null); setBusy(true);
    try {
      const t = await api<{ access_token: string }>("/auth/password/change", {
        method: "POST", json: { current_password: f.get("current_password"), new_password: f.get("new_password"), platform: "web" },
      });
      await accept(t.access_token);
      form.reset(); toast("Password changed. Other devices were logged out."); onDone?.();
    } catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <FormError message={error} />
      <Field label="Current password" name="current_password" type="password" autoComplete="current-password" required />
      <Field label="New password" name="new_password" type="password" autoComplete="new-password" hint="At least 8 characters." required />
      <Field label="Type the new password again" name="confirm" type="password" autoComplete="new-password" required />
      <Button type="submit" loading={busy}>{submitLabel}</Button>
    </form>
  );
}

function PinForm() {
  const toast = useToast((s) => s.show);
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (body: { password: string; pin: string }) => api("/auth/pin", { method: "PUT", json: body }),
    onSuccess: () => toast("Approval PIN saved"),
    onError: (e) => setError(msg(e)),
  });
  return (
    <form className="space-y-4" onSubmit={(e) => {
      e.preventDefault(); setError(null);
      const f = new FormData(e.currentTarget);
      save.mutate({ password: String(f.get("password")), pin: String(f.get("pin")) });
    }}>
      <FormError message={error} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="New PIN (4 to 6 digits)" name="pin" type="password" inputMode="numeric" pattern="[0-9]{4,6}" maxLength={6} required />
        <Field label="Your password" name="password" type="password" autoComplete="current-password" required />
      </div>
      <Button type="submit" variant="secondary" loading={save.isPending}>Save PIN</Button>
    </form>
  );
}

interface Session { id: string; device_label: string | null; platform: string | null; last_used_at: string }

function Sessions() {
  const qc = useQueryClient();
  const logout = useAuth((s) => s.logout);
  const { data = [] } = useQuery({ queryKey: ["sessions"], queryFn: () => api<Session[]>("/auth/sessions") });
  const revoke = useMutation({
    mutationFn: (id: string) => api(`/auth/sessions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
  const all = useMutation({ mutationFn: () => api("/auth/logout-all", { method: "POST" }), onSuccess: () => void logout() });
  return (
    <div className="space-y-4">
      <ul className="divide-y divide-border">
        {data.map((s) => (
          <li key={s.id} className="flex items-center gap-3 py-3">
            {s.platform === "web" ? <Laptop className="h-5 w-5 text-text-2" aria-hidden /> : <Smartphone className="h-5 w-5 text-text-2" aria-hidden />}
            <div className="flex-1">
              <p className="font-medium capitalize">{s.device_label ?? `${s.platform ?? "Unknown"} device`}</p>
              <p className="text-sm text-text-2">Last used {new Date(s.last_used_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</p>
            </div>
            <Button variant="ghost" size="md" onClick={() => revoke.mutate(s.id)}>Log out</Button>
          </li>
        ))}
      </ul>
      <Button variant="secondary" size="md" onClick={() => all.mutate()} loading={all.isPending}>Log out of all devices</Button>
    </div>
  );
}

export function SecurityPanel() {
  const canPin = useAuth((s) => s.can("approval.decide"));
  return (
    <div className="space-y-6">
      <Section title="Password"><ChangePasswordForm /></Section>
      {canPin && (
        <Section title="Approval PIN" description="Type this PIN on a salesperson's screen to approve a big discount or a return on the spot.">
          <PinForm />
        </Section>
      )}
      <Section title="Logged-in devices"><Sessions /></Section>
    </div>
  );
}

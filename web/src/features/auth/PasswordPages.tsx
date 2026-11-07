import { MailCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { ChangePasswordForm } from "@/features/settings/SecurityPanel";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { AuthShell, FormError } from "./AuthShell";
import { useAuth } from "./store";

export function ForgotPage() {
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api("/auth/password/forgot", { method: "POST", json: { email: new FormData(e.currentTarget).get("email") } });
      setSent(true);
    } catch (err) { setError(err instanceof ApiError ? err.message : "Something went wrong."); } finally { setBusy(false); }
  }
  return (
    <AuthShell>
      {sent ? (
        <div className="space-y-4">
          <span className="grid h-12 w-12 place-items-center rounded-full bg-success-soft"><MailCheck className="h-6 w-6 text-success" aria-hidden /></span>
          <h2 className="text-3xl font-bold tracking-tight">Check your email</h2>
          <p className="text-text-2">If that email has an Anylo account, we've sent a link to choose a new password. It works for 30 minutes.</p>
          <Link to="/login" className="inline-block font-semibold text-primary hover:underline">Back to log in</Link>
        </div>
      ) : (
        <>
          <h2 className="text-3xl font-bold tracking-tight">Forgot your password?</h2>
          <p className="mt-2 text-text-2">Enter your email and we'll send you a reset link. Staff without email: ask your owner or manager to reset it.</p>
          <form onSubmit={submit} className="mt-8 space-y-5">
            <FormError message={error} />
            <Field label="Email" name="email" type="email" autoComplete="email" required />
            <Button type="submit" size="xl" className="w-full" loading={busy}>Send reset link</Button>
            <Link to="/login" className="block text-center text-sm font-semibold text-primary hover:underline">Back to log in</Link>
          </form>
        </>
      )}
    </AuthShell>
  );
}

export function ResetPage() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (f.get("password") !== f.get("confirm")) return setError("The two passwords don't match.");
    setBusy(true); setError(null);
    try {
      await api("/auth/password/reset", { method: "POST", json: { token, password: f.get("password") } });
      navigate("/login", { replace: true, state: { reset: true } });
    } catch (err) { setError(err instanceof ApiError ? err.message : "Something went wrong."); } finally { setBusy(false); }
  }
  return (
    <AuthShell>
      <h2 className="text-3xl font-bold tracking-tight">Choose a new password</h2>
      <form onSubmit={submit} className="mt-8 space-y-5">
        <FormError message={error} />
        <Field label="New password" name="password" type="password" minLength={8} autoComplete="new-password" hint="At least 8 characters." required />
        <Field label="Type it again" name="confirm" type="password" autoComplete="new-password" required />
        <Button type="submit" size="xl" className="w-full" loading={busy}>Save password</Button>
      </form>
    </AuthShell>
  );
}

/** Staff created with a temporary password land here before anything else. */
export function ForceChangePage() {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <AuthShell>
      <h2 className="text-3xl font-bold tracking-tight">Welcome, {me?.user.full_name.split(" ")[0]}</h2>
      <p className="mt-2 mb-8 text-text-2">Choose your own password. Enter the temporary one your owner or manager gave you first.</p>
      <ChangePasswordForm submitLabel="Save my password" onDone={() => navigate("/app", { replace: true })} />
      <button onClick={logout} className="mt-6 text-sm font-semibold text-text-2 hover:text-text">Log out</button>
    </AuthShell>
  );
}

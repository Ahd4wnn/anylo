import { Eye, EyeOff } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "@/api/client";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { AuthShell, FormError } from "./AuthShell";
import { useAuth } from "./store";

export function PasswordToggle({ show, onToggle }: { show: boolean; onToggle: () => void }) {
  return (
    <button type="button" onClick={onToggle} className="grid h-10 w-10 place-items-center rounded-md text-text-2 hover:bg-surface-2" aria-label={show ? "Hide password" : "Show password"}>
      {show ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
    </button>
  );
}

export function LoginPage() {
  const login = useAuth((s) => s.login);
  const navigate = useNavigate();
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true); setError(null);
    try {
      await login(String(f.get("login")).trim(), String(f.get("password")));
      navigate("/app", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      <h2 className="text-3xl font-bold tracking-tight text-text">Welcome back</h2>
      <p className="mt-2 text-text-2">Log in to your shop.</p>
      <form onSubmit={submit} className="mt-8 space-y-5">
        <FormError message={error} />
        <Field label="Email or mobile number" name="login" autoComplete="username" required placeholder="you@shop.in or 98xxxxxxxx" />
        <Field label="Password" name="password" type={show ? "text" : "password"} autoComplete="current-password" required
          trailing={<PasswordToggle show={show} onToggle={() => setShow(!show)} />} />
        <div className="flex justify-end">
          <Link to="/forgot" className="text-sm font-semibold text-primary hover:underline">Forgot password?</Link>
        </div>
        <Button type="submit" className="w-full" size="xl" loading={busy}>Log in</Button>
      </form>
      <div className="mt-8 rounded-xl border border-border bg-surface p-5">
        <p className="font-semibold text-text">New to Anylo?</p>
        <p className="mt-1 text-sm text-text-2">30 days free, then <span className="tnum font-semibold text-text">₹599</span>/month per shop. GST included, nothing more.</p>
        <Link to="/signup" className="mt-4 inline-flex h-12 w-full items-center justify-center rounded-lg bg-primary-soft font-semibold text-on-primary-soft transition-colors hover:bg-tint">
          Start your free trial
        </Link>
      </div>
    </AuthShell>
  );
}

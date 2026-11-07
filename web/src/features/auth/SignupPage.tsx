import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { Select } from "@/ui/Select";
import { AuthShell, FormError } from "./AuthShell";
import { PasswordToggle } from "./LoginPage";
import { useAuth } from "./store";

type Option = { value: string; label: string };
type Errors = Partial<Record<"phone" | "password" | "email", string>>;

function validate(f: Record<string, string>): Errors {
  const e: Errors = {};
  if (!/^[6-9]\d{9}$/.test(f.phone)) e.phone = "Enter a 10-digit mobile number.";
  if (f.password.length < 8) e.password = "Use at least 8 characters.";
  if (!/^\S+@\S+\.\S+$/.test(f.email)) e.email = "Enter a valid email.";
  return e;
}

export function SignupPage() {
  const signup = useAuth((s) => s.signup);
  const navigate = useNavigate();
  const ref = useQuery({ queryKey: ["reference"], queryFn: () => api<{ states: Option[]; business_types: Option[] }>("/meta/reference"), staleTime: Infinity });
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Errors>({});

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    const errs = validate(f);
    setFieldErrors(errs); setError(null);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      await signup(f);
      navigate("/app", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      <h2 className="text-3xl font-bold tracking-tight text-text">Start your free trial</h2>
      <ul className="mt-3 space-y-1.5 text-text-2">
        {["30 days free, every feature", "No card needed", "Then ₹599/month per shop, GST included"].map((t) => (
          <li key={t} className="flex items-center gap-2 text-[15px]"><Check className="h-4 w-4 text-success" aria-hidden />{t}</li>
        ))}
      </ul>
      <form onSubmit={submit} className="mt-8 space-y-5" noValidate>
        <FormError message={error} />
        <Field label="Shop name" name="shop_name" required minLength={2} placeholder="e.g. Ravi Stores" autoComplete="organization" />
        <Field label="Your name" name="owner_name" required minLength={2} autoComplete="name" />
        <div className="grid gap-5 sm:grid-cols-2">
          <Select label="Type of shop" name="business_type" defaultValue="general" options={ref.data?.business_types ?? []} />
          <Select label="State" name="state_code" required defaultValue="" placeholder="Select state" options={ref.data?.states ?? []} />
        </div>
        <Field label="Mobile number" name="phone" inputMode="numeric" maxLength={10} required autoComplete="tel-national" placeholder="98xxxxxxxx" error={fieldErrors.phone} />
        <Field label="Email" name="email" type="email" required autoComplete="email" error={fieldErrors.email} />
        <Field label="Password" name="password" type={show ? "text" : "password"} required autoComplete="new-password"
          hint="At least 8 characters." error={fieldErrors.password}
          trailing={<PasswordToggle show={show} onToggle={() => setShow(!show)} />} />
        <Button type="submit" className="w-full" size="xl" loading={busy}>Create my shop</Button>
        <p className="text-center text-sm text-text-2">
          Already have an account? <Link to="/login" className="font-semibold text-primary hover:underline">Log in</Link>
        </p>
      </form>
    </AuthShell>
  );
}

import { BarChart3, Eye, EyeOff, Receipt, Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { Logo } from "@/ui/Logo";

const pillars = [
  { icon: Receipt, title: "Bill anything", text: "GST invoices in seconds: scan, tap or speak." },
  { icon: BarChart3, title: "Sell anything", text: "Any unit, any variant, stock that keeps itself right." },
  { icon: Sparkles, title: "Run everything", text: "Profit, cash, staff, goals, plus an AI manager for owners." },
];

export function LoginPage() {
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);

  function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); // wired to /v1/auth/login in M1
    setTimeout(() => setBusy(false), 600);
  }

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel */}
      <aside className="relative overflow-hidden bg-deep text-on-deep px-6 pt-8 pb-10 sm:px-10 lg:flex lg:flex-col lg:justify-between lg:p-14">
        <div aria-hidden className="pointer-events-none absolute hidden sm:block -bottom-56 -right-56 h-[26rem] w-[26rem] rounded-[30%] bg-primary/70 rotate-12" />
        <div aria-hidden className="pointer-events-none absolute -right-24 bottom-52 hidden h-44 w-44 rounded-[30%] bg-brand/35 rotate-12 lg:block" />
        <div className="relative"><Logo size={40} onDark /></div>

        <div className="relative mt-10 lg:mt-0">
          <h1 className="text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl" style={{ letterSpacing: "-0.035em" }}>
            Bill anything.<br />Sell anything.<br />Run <span className="text-accent">everything.</span>
          </h1>
          <p className="mt-5 max-w-md text-lg text-white/75">
            The GST billing and business app built for Indian shops: fast at the counter, clear in the back office.
          </p>
          <ul className="mt-10 hidden space-y-5 lg:block">
            {pillars.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-4">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-white/10"><Icon className="h-5 w-5 text-white" aria-hidden /></span>
                <span><span className="block font-semibold">{title}</span><span className="text-white/70">{text}</span></span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative mt-10 hidden text-sm text-white/60 lg:block">© {new Date().getFullYear()} Dofida Private Limited</p>
      </aside>

      {/* Form */}
      <main className="flex items-center justify-center px-6 py-10 sm:px-10">
        <div className="w-full max-w-[420px]">
          <h2 className="text-3xl font-bold tracking-tight text-text">Welcome back</h2>
          <p className="mt-2 text-text-2">Log in to your shop.</p>

          <form onSubmit={submit} className="mt-8 space-y-5" noValidate>
            <Field label="Email or mobile number" name="login" autoComplete="username" inputMode="email" required placeholder="you@shop.in or 98xxxxxxxx" />
            <Field
              label="Password" name="password" type={show ? "text" : "password"} autoComplete="current-password" required
              trailing={
                <button type="button" onClick={() => setShow(!show)} className="grid h-10 w-10 place-items-center rounded-md text-text-2 hover:bg-surface-2" aria-label={show ? "Hide password" : "Show password"}>
                  {show ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                </button>
              }
            />
            <div className="flex justify-end">
              <Link to="/forgot" className="text-sm font-semibold text-primary hover:underline">Forgot password?</Link>
            </div>
            <Button type="submit" className="w-full" size="xl" loading={busy}>Log in</Button>
          </form>

          <div className="mt-8 rounded-lg border border-border bg-tint/60 p-5 dark:bg-tint">
            <p className="font-semibold text-text">New to Anylo?</p>
            <p className="mt-1 text-sm text-text-2">30 days free, then <span className="tnum font-semibold text-text">₹599</span>/month per shop. GST included, nothing more.</p>
            <Link to="/signup" className="mt-4 inline-flex h-12 w-full items-center justify-center rounded-md bg-accent text-lg font-bold text-on-accent transition-colors hover:bg-accent-hover">
              Start free trial
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}

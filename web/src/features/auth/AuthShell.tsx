import { BarChart3, Receipt, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { Logo } from "@/ui/Logo";

const pillars = [
  { icon: Receipt, title: "Bill anything", text: "GST invoices in seconds: scan, tap or speak." },
  { icon: BarChart3, title: "Sell anything", text: "Any unit, any variant, stock that keeps itself right." },
  { icon: Sparkles, title: "Run everything", text: "Profit, cash, staff and goals, plus an AI manager for owners." },
];

/** Brand panel + form column shared by login, signup and password screens. */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-bg lg:grid lg:grid-cols-[1.05fr_1fr] lg:p-3">
      <aside className="relative overflow-hidden bg-tint px-6 pt-8 pb-10 sm:px-10 lg:sticky lg:top-3 lg:flex lg:h-[calc(100dvh-24px)] lg:flex-col lg:justify-between lg:gap-10 lg:rounded-xl lg:p-14">
        <div aria-hidden className="pointer-events-none absolute -bottom-32 -right-32 hidden h-96 w-96 rounded-full bg-primary-soft sm:block" />
        <div className="relative"><Logo size={40} /></div>
        <div className="relative mt-10 lg:mt-0">
          <h1 className="text-4xl font-bold leading-[1.08] text-text sm:text-5xl lg:text-[56px]" style={{ letterSpacing: "-0.03em" }}>
            Bill anything.<br />Sell anything.<br />Run <span className="text-brand">everything.</span>
          </h1>
          <p className="mt-5 max-w-md text-lg text-text-2">
            The calm, clear way to run your shop: fast GST billing at the counter, and the whole business at a glance.
          </p>
          <ul className="mt-10 hidden space-y-5 lg:block">
            {pillars.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-4">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-surface shadow-e1">
                  <Icon className="h-5 w-5 text-brand" aria-hidden />
                </span>
                <span><span className="block font-semibold text-text">{title}</span><span className="text-text-2">{text}</span></span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative mt-10 hidden text-sm text-text-3 lg:block">© {new Date().getFullYear()} Dofida Private Limited</p>
      </aside>
      <main className="flex items-center justify-center px-6 py-10 sm:px-10">
        <div className="w-full max-w-[420px]">{children}</div>
      </main>
    </div>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return <p role="alert" className="rounded-lg bg-danger-soft px-4 py-3 text-sm font-medium text-danger">{message}</p>;
}

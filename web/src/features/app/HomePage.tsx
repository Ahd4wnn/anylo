import { LogOut, Sparkles } from "lucide-react";
import { useAuth } from "@/features/auth/store";
import { Button } from "@/ui/Button";
import { Logo } from "@/ui/Logo";

/** Placeholder home until the dashboard lands (M6). Proves the session works end to end. */
export function HomePage() {
  const { me, logout, can } = useAuth();
  if (!me) return null;
  const shop = me.shops.find((s) => s.id === me.active_shop_id);
  const sub = me.subscription;

  return (
    <div className="min-h-dvh bg-bg">
      <header className="flex h-16 items-center justify-between border-b border-border bg-surface px-4 sm:px-8">
        <Logo size={32} />
        <Button variant="ghost" size="md" onClick={logout}><LogOut className="h-4 w-4" aria-hidden />Log out</Button>
      </header>
      {sub?.status === "trialing" && (
        <div className="border-b border-border bg-warning-soft px-4 py-2.5 text-center text-sm text-warning sm:px-8">
          Free trial: <span className="font-semibold">{sub.days_left} days left</span>. Then ₹599/month, GST included.
        </div>
      )}
      <main className="mx-auto max-w-5xl px-4 py-10 sm:px-8">
        <p className="text-text-2">{shop?.name ?? "Your shops"}</p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">Welcome, {me.user.full_name.split(" ")[0]}</h1>
        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          {["Today's sales", "Bills today", "Cash in hand"].map((t) => (
            <div key={t} className="rounded-xl border border-border bg-surface p-5">
              <p className="text-sm text-text-2">{t}</p>
              <p className="tnum mt-2 text-2xl font-bold">{t === "Bills today" ? "0" : "₹0"}</p>
            </div>
          ))}
        </div>
        {can("ai.use") && (
          <div className="mt-6 flex items-center gap-3 rounded-xl bg-tint p-5">
            <Sparkles className="h-5 w-5 text-brand" aria-hidden />
            <p className="text-text">Your AI manager is coming soon. Ask anything about your shop.</p>
          </div>
        )}
      </main>
    </div>
  );
}

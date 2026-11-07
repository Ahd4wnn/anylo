import { BarChart3, ChevronDown, Home, LogOut, Package, Settings, ShoppingCart, Store, Users } from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/features/auth/store";
import { Logo } from "@/ui/Logo";
import { Badge, Toaster } from "@/ui/primitives";

const NAV = [
  { to: "/app", label: "Home", icon: Home, end: true },
  { to: "/pos", label: "Sell", icon: ShoppingCart, soon: true },
  { to: "/app/items", label: "Items", icon: Package, soon: true },
  { to: "/app/customers", label: "Customers", icon: Users, soon: true },
  { to: "/app/reports", label: "Reports", icon: BarChart3, soon: true },
  { to: "/app/settings", label: "Settings", icon: Settings },
];

function ShopSwitcher() {
  const { me, switchShop } = useAuth();
  const [open, setOpen] = useState(false);
  if (!me || me.shops.length < 2) return <p className="truncate text-sm font-semibold text-text">{me?.shops[0]?.name}</p>;
  const active = me.shops.find((s) => s.id === me.active_shop_id);
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex h-10 max-w-[220px] items-center gap-2 rounded-lg border border-border bg-surface px-3 text-sm font-semibold hover:bg-surface-2">
        <Store className="h-4 w-4 text-brand" aria-hidden /><span className="truncate">{active?.name ?? "Choose shop"}</span>
        <ChevronDown className="h-4 w-4 text-text-2" aria-hidden />
      </button>
      {open && (
        <ul className="absolute left-0 z-30 mt-2 w-64 rounded-lg border border-border bg-surface p-1 shadow-e2">
          {me.shops.map((s) => (
            <li key={s.id}>
              <button onClick={() => { setOpen(false); void switchShop(s.id); }}
                className={`w-full rounded-md px-3 py-2.5 text-left text-sm hover:bg-surface-2 ${s.id === me.active_shop_id ? "bg-tint font-semibold" : ""}`}>
                {s.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NavItem({ to, label, icon: Icon, end, soon, compact }: (typeof NAV)[number] & { compact?: boolean }) {
  if (soon && !compact) {
    return (
      <span className="flex h-11 items-center gap-3 rounded-lg px-3 text-text-3" aria-disabled>
        <Icon className="h-5 w-5" aria-hidden />{label}<span className="ml-auto"><Badge>Soon</Badge></span>
      </span>
    );
  }
  return (
    <NavLink to={soon ? "#" : to} end={end} onClick={(e) => soon && e.preventDefault()}
      className={({ isActive }) => compact
        ? `flex flex-1 flex-col items-center gap-1 py-2 text-xs font-medium ${isActive && !soon ? "text-primary" : soon ? "text-text-3" : "text-text-2"}`
        : `flex h-11 items-center gap-3 rounded-lg px-3 font-medium transition-colors ${isActive ? "bg-primary-soft text-on-primary-soft" : "text-text-2 hover:bg-surface-2 hover:text-text"}`}>
      <Icon className="h-5 w-5" aria-hidden />{label}
    </NavLink>
  );
}

export function AppShell({ children }: { children?: ReactNode }) {
  const { me, logout } = useAuth();
  const sub = me?.subscription;
  return (
    <div className="min-h-dvh bg-bg lg:grid lg:grid-cols-[256px_1fr]">
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-border bg-surface p-4 lg:flex">
        <div className="px-2 pb-6 pt-2"><Logo size={32} /></div>
        <nav className="space-y-1" aria-label="Main">{NAV.map((n) => <NavItem key={n.to} {...n} />)}</nav>
        <div className="mt-auto rounded-lg border border-border p-3">
          <p className="truncate text-sm font-semibold">{me?.user.full_name}</p>
          <p className="truncate text-xs capitalize text-text-2">{me?.user.role}</p>
          <button onClick={logout} className="mt-3 flex items-center gap-2 text-sm font-medium text-text-2 hover:text-danger">
            <LogOut className="h-4 w-4" aria-hidden />Log out
          </button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-col pb-20 lg:pb-0">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-border bg-surface/90 px-4 backdrop-blur sm:px-6">
          <span className="lg:hidden"><Logo size={28} /></span>
          <ShopSwitcher />
          <button onClick={logout} className="ml-auto grid h-10 w-10 place-items-center rounded-lg text-text-2 hover:bg-surface-2 lg:hidden" aria-label="Log out">
            <LogOut className="h-5 w-5" />
          </button>
        </header>
        {sub?.status === "trialing" && (
          <div className="border-b border-border bg-warning-soft px-4 py-2 text-center text-sm text-warning sm:px-6">
            Free trial: <span className="font-semibold">{sub.days_left} days left</span>. Then ₹599/month, GST included.
          </div>
        )}
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children ?? <Outlet />}</main>
      </div>
      <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-border bg-surface lg:hidden" aria-label="Main">
        {NAV.filter((n) => n.label !== "Customers").map((n) => <NavItem key={n.to} {...n} compact />)}
      </nav>
      <Toaster />
    </div>
  );
}

import { Plus, Sparkles, Store } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { useShop } from "@/features/shop/api";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { Dialog, PageHeader } from "@/ui/primitives";

function AddShop() {
  const switchShop = useAuth((s) => s.switchShop);
  const { data: shop } = useShop();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const name = String(new FormData(e.currentTarget).get("name")).trim();
    setError(null);
    try {
      // A new shop starts in the same state as the current one; its GSTIN step can change it.
      const { id } = await api<{ id: string }>("/shops", { method: "POST", json: { name, state_code: shop?.state_code ?? "32" } });
      setOpen(false); await switchShop(id);
    } catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't add the shop."); }
  }
  return (
    <>
      <Button variant="secondary" size="md" onClick={() => setOpen(true)}><Plus className="h-4 w-4" aria-hidden />Add another shop</Button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Add a shop">
        <form onSubmit={submit} className="space-y-4">
          <FormError message={error} />
          <Field label="Shop name" name="name" required minLength={2} />
          <p className="text-sm text-text-2">Each shop gets its own 30-day free trial, then ₹599/month.</p>
          <Button type="submit" className="w-full">Add shop</Button>
        </form>
      </Dialog>
    </>
  );
}

/** Placeholder home until the dashboard lands (M6). */
export function HomePage() {
  const { me, can, switchShop } = useAuth();
  if (!me) return null;

  if (!me.active_shop_id && me.shops.length > 1) {
    return (
      <>
        <PageHeader title="Choose a shop" description="Pick the shop you want to work in." />
        <ul className="grid gap-3 sm:grid-cols-2">
          {me.shops.map((s) => (
            <li key={s.id}>
              <button onClick={() => void switchShop(s.id)} className="flex w-full items-center gap-4 rounded-xl border border-border bg-surface p-5 text-left hover:border-primary">
                <span className="grid h-11 w-11 place-items-center rounded-full bg-primary-soft"><Store className="h-5 w-5 text-brand" aria-hidden /></span>
                <span className="font-semibold">{s.name}</span>
              </button>
            </li>
          ))}
        </ul>
      </>
    );
  }

  const shop = me.shops.find((s) => s.id === me.active_shop_id);
  return (
    <>
      <PageHeader title={`Welcome, ${me.user.full_name.split(" ")[0]}`} description={shop?.name} action={me.user.role === "owner" && <AddShop />} />
      <div className="grid gap-4 sm:grid-cols-3">
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
    </>
  );
}

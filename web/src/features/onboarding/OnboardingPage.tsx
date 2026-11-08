import { useMutation } from "@tanstack/react-query";
import { Check, PartyPopper } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useAuth } from "@/features/auth/store";
import { BusinessForm, LogoAndUpiForm, TaxForm } from "@/features/settings/forms";
import { AddStaffForm } from "@/features/settings/StaffPanel";
import { useShop } from "@/features/shop/api";
import { Button } from "@/ui/Button";
import { Logo } from "@/ui/Logo";
import { Section } from "@/ui/primitives";

const STEPS = ["Business", "GST", "Logo & UPI", "Staff", "Items", "Done"];

export function OnboardingPage() {
  const { data: shop } = useShop();
  const { refreshMe, can, me } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [added, setAdded] = useState<string[]>([]);
  const [starter, setStarter] = useState<number | null>(null);
  const [addingStarter, setAddingStarter] = useState(false);
  async function addStarter() {
    setAddingStarter(true);
    try { setStarter((await api<{ added: number }>("/shop/starter-products", { method: "POST" })).added); }
    finally { setAddingStarter(false); }
  }
  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  // Managers can't edit GST, so they skip that step.
  const skipTax = !can("shop.tax_profile");
  const finish = useMutation({
    mutationFn: () => api("/shop/onboarding/complete", { method: "POST" }),
    onSuccess: async () => { await refreshMe(); navigate("/app", { replace: true }); },
  });

  if (!shop) return <div className="grid min-h-dvh place-items-center bg-bg text-text-2">Loading…</div>;
  const stepView = [
    <BusinessForm key="b" shop={shop} onSaved={() => setStep(skipTax ? 2 : 1)} submitLabel="Save and continue" />,
    <TaxForm key="t" shop={shop} onSaved={next} submitLabel="Save and continue" />,
    <LogoAndUpiForm key="l" shop={shop} onSaved={next} submitLabel="Save and continue" />,
    <Section key="s" title="Add your staff" description="Optional. Each salesperson gets their own login so every bill shows who made it."
      footer={<Button size="md" onClick={next}>{added.length ? "Continue" : "Skip for now"}</Button>}>
      {added.length > 0 && <p className="rounded-lg bg-success-soft px-4 py-3 text-sm text-success">Added: {added.join(", ")}. Their login details are in Settings → Staff.</p>}
      <AddStaffForm onCreated={(c) => setAdded((a) => [...a, `${c.full_name} (password ${c.temporary_password})`])} />
    </Section>,
    <Section key="p" title="Add your items" description="Start with common items for your type of shop, or import your own list. You can do this later too."
      footer={<Button size="md" onClick={next}>{starter ? "Continue" : "Skip for now"}</Button>}>
      {starter !== null && <p className="rounded-lg bg-success-soft px-4 py-3 text-sm text-success">Added {starter} starter items at ₹0. Set their prices in Items.</p>}
      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" size="md" loading={addingStarter} onClick={() => void addStarter()}>Add starter items</Button>
        <Button variant="ghost" size="md" onClick={() => navigate("/app/items/import")}>Import a spreadsheet instead</Button>
      </div>
    </Section>,
    <Section key="d" title="Your shop is ready" footer={<Button size="lg" loading={finish.isPending} onClick={() => finish.mutate()}>Go to my shop</Button>}>
      <div className="flex items-start gap-4">
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-primary-soft"><PartyPopper className="h-6 w-6 text-brand" aria-hidden /></span>
        <div className="space-y-2 text-text-2">
          <p><span className="font-semibold text-text">{shop.name}</span> is set up, {me?.user.full_name.split(" ")[0]}.</p>
          <p>Next you'll make your first bill. You can change anything later in Settings.</p>
        </div>
      </div>
    </Section>,
  ];

  return (
    <div className="min-h-dvh bg-bg">
      <header className="flex h-16 items-center border-b border-border bg-surface px-4 sm:px-8"><Logo size={30} /></header>
      <main className="mx-auto max-w-2xl px-4 py-8 sm:px-6">
        <p className="text-sm font-semibold text-brand">Step {step + 1} of {STEPS.length}</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Let's set up your shop</h1>
        <ol className="mt-6 mb-8 flex gap-2" aria-label="Progress">
          {STEPS.map((s, i) => (
            <li key={s} className="flex-1">
              <div className={`h-1.5 rounded-full ${i <= step ? "bg-primary" : "bg-border"}`} />
              <span className={`mt-2 hidden items-center gap-1 text-xs font-medium sm:flex ${i <= step ? "text-text" : "text-text-3"}`}>
                {i < step && <Check className="h-3 w-3 text-primary" aria-hidden />}{s}
              </span>
            </li>
          ))}
        </ol>
        {stepView[step]}
        {step > 0 && step < STEPS.length - 1 && (
          <button onClick={() => setStep(step === 2 && skipTax ? 0 : step - 1)} className="mt-4 text-sm font-semibold text-text-2 hover:text-text">← Back</button>
        )}
      </main>
    </div>
  );
}

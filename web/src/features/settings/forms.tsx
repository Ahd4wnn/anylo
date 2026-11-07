import { useQuery } from "@tanstack/react-query";
import { Building2, CheckCircle2, ImagePlus, Trash2 } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "@/api/client";
import { FormError } from "@/features/auth/AuthShell";
import { useAuth } from "@/features/auth/store";
import { usePatchShop, usePutTax, useUploadLogo, type Scheme, type Shop } from "@/features/shop/api";
import { gstinHint, isValidGstin } from "@/lib/gstin";
import { Button } from "@/ui/Button";
import { Field } from "@/ui/Field";
import { Select } from "@/ui/Select";
import { Section, Toggle, useToast } from "@/ui/primitives";

type Option = { value: string; label: string };
const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
const useReference = () =>
  useQuery({ queryKey: ["reference"], queryFn: () => api<{ states: Option[]; business_types: Option[] }>("/meta/reference"), staleTime: Infinity });

/** Business details form; `onSaved` lets the onboarding wizard advance. */
export function BusinessForm({ shop, onSaved, submitLabel = "Save changes" }: { shop: Shop; onSaved?: () => void; submitLabel?: string }) {
  const patch = usePatchShop();
  const ref = useReference();
  const toast = useToast((s) => s.show);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.trim() || null]));
    setError(null);
    try { await patch.mutateAsync(body); toast("Business details saved"); onSaved?.(); }
    catch (err) { setError(errMsg(err)); }
  }

  return (
    <form onSubmit={submit}>
      <Section title="Business details" description="Printed on every bill and invoice."
        footer={<Button type="submit" size="md" loading={patch.isPending}>{submitLabel}</Button>}>
        <FormError message={error} />
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Shop name" name="name" defaultValue={shop.name} required />
          <Select label="Type of shop" name="business_type" defaultValue={shop.business_type} options={ref.data?.business_types ?? []} />
          <Field label="Shop phone" name="phone" defaultValue={shop.phone ?? ""} inputMode="numeric" maxLength={10} />
          <Field label="Shop email" name="email" type="email" defaultValue={shop.email ?? ""} />
        </div>
        <Field label="Address" name="address_line1" defaultValue={shop.address_line1 ?? ""} placeholder="Building, street" required />
        <Field label="Area / landmark (optional)" name="address_line2" defaultValue={shop.address_line2 ?? ""} />
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="City" name="city" defaultValue={shop.city ?? ""} required />
          <Field label="PIN code" name="pincode" defaultValue={shop.pincode ?? ""} inputMode="numeric" maxLength={6} required />
        </div>
        <p className="text-sm text-text-2">State: <span className="font-medium text-text">{shop.state_name}</span>. It follows your GSTIN.</p>
      </Section>
    </form>
  );
}

const SCHEMES: { value: Scheme; title: string; text: string }[] = [
  { value: "regular", title: "Regular GST", text: "You charge GST and issue tax invoices." },
  { value: "composition", title: "Composition", text: "You pay a fixed % and issue bills of supply." },
  { value: "unregistered", title: "Not registered", text: "No GSTIN yet. Simple bills without tax." },
];

export function TaxForm({ shop, onSaved, submitLabel = "Save GST settings" }: { shop: Shop; onSaved?: () => void; submitLabel?: string }) {
  const put = usePutTax();
  const toast = useToast((s) => s.show);
  const canEdit = useAuth((s) => s.can("shop.tax_profile"));
  const t = shop.tax;
  const [scheme, setScheme] = useState<Scheme>(t.gst_scheme);
  const [gstin, setGstin] = useState(t.gstin ?? "");
  const [inclusive, setInclusive] = useState(t.prices_include_tax);
  const [roundOff, setRoundOff] = useState(t.invoice_round_off);
  const [error, setError] = useState<string | null>(null);
  const needsGstin = scheme !== "unregistered";
  const hint = needsGstin ? gstinHint(gstin) : undefined;
  const valid = !needsGstin || isValidGstin(gstin.trim().toUpperCase());

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setError(null);
    try {
      await put.mutateAsync({
        gst_scheme: scheme, gstin: needsGstin ? gstin.trim().toUpperCase() : null,
        legal_name: String(f.get("legal_name") ?? "").trim() || null, trade_name: String(f.get("trade_name") ?? "").trim() || null,
        prices_include_tax: inclusive, invoice_round_off: roundOff,
        hsn_digits_required: Number(f.get("hsn_digits_required") ?? 4) as 4 | 6,
      });
      toast("GST settings saved"); onSaved?.();
    } catch (err) { setError(errMsg(err)); }
  }

  return (
    <form onSubmit={submit}>
      <Section title="GST" description={canEdit ? "This decides how tax appears on your bills." : "Only the owner can change GST settings."}
        footer={canEdit && <Button type="submit" size="md" loading={put.isPending} disabled={!valid}>{submitLabel}</Button>}>
        <FormError message={error} />
        <fieldset disabled={!canEdit} className="space-y-5">
          <legend className="sr-only">GST registration</legend>
          <div className="grid gap-3 sm:grid-cols-3" role="radiogroup">
            {SCHEMES.map((s) => (
              <button key={s.value} type="button" role="radio" aria-checked={scheme === s.value} onClick={() => setScheme(s.value)}
                className={`rounded-lg border p-4 text-left transition-colors ${scheme === s.value ? "border-primary bg-primary-soft" : "border-border hover:bg-surface-2"}`}>
                <span className="flex items-center justify-between font-semibold">{s.title}{scheme === s.value && <CheckCircle2 className="h-5 w-5 text-primary" aria-hidden />}</span>
                <span className="mt-1 block text-sm text-text-2">{s.text}</span>
              </button>
            ))}
          </div>
          {needsGstin && (
            <>
              <Field label="GSTIN" value={gstin} onChange={(e) => setGstin(e.target.value.toUpperCase())} maxLength={15}
                placeholder="32ABCDE1234F1Z5" className="uppercase" autoComplete="off" error={gstin.length === 15 ? hint : undefined}
                hint={gstin.length !== 15 ? hint ?? "15 characters, from your GST certificate." : valid ? "Looks good." : undefined} />
              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="Legal name (as on GST certificate)" name="legal_name" defaultValue={t.legal_name ?? ""} />
                <Field label="Trade name (optional)" name="trade_name" defaultValue={t.trade_name ?? ""} />
              </div>
              <Toggle checked={inclusive} onChange={setInclusive} label="My prices include GST"
                hint="Usual for MRP items. Turn off if you add GST on top of your price." />
              <Select label="HSN code length" name="hsn_digits_required" defaultValue={String(t.hsn_digits_required)}
                options={[{ value: "4", label: "4 digits (turnover up to ₹5 crore)" }, { value: "6", label: "6 digits (turnover above ₹5 crore)" }]} />
            </>
          )}
          <Toggle checked={roundOff} onChange={setRoundOff} label="Round bill totals to the nearest rupee" />
        </fieldset>
      </Section>
    </form>
  );
}

export function LogoAndUpiForm({ shop, onSaved, submitLabel = "Save" }: { shop: Shop; onSaved?: () => void; submitLabel?: string }) {
  const upload = useUploadLogo();
  const patch = usePatchShop();
  const canUpi = useAuth((s) => s.can("shop.payment_details"));
  const toast = useToast((s) => s.show);
  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  async function pick(file: File | null) {
    setError(null);
    try { await upload.mutateAsync(file); toast(file ? "Logo updated" : "Logo removed"); }
    catch (err) { setError(errMsg(err)); }
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setError(null);
    try {
      if (canUpi) await patch.mutateAsync({ upi_vpa: String(f.get("upi_vpa")).trim() || null, upi_payee_name: String(f.get("upi_payee_name")).trim() || null });
      toast("Saved"); onSaved?.();
    } catch (err) { setError(errMsg(err)); }
  }

  return (
    <form onSubmit={submit}>
      <Section title="Logo and UPI" description="Your logo goes on bills. Your UPI ID makes a payment QR on every bill."
        footer={<Button type="submit" size="md" loading={patch.isPending}>{submitLabel}</Button>}>
        <FormError message={error} />
        <div className="flex items-center gap-5">
          <div className="grid h-20 w-20 shrink-0 place-items-center overflow-hidden rounded-xl border border-border bg-surface-2">
            {shop.logo_url ? <img src={shop.logo_url} alt="Shop logo" className="h-full w-full object-contain" /> : <Building2 className="h-8 w-8 text-text-3" aria-hidden />}
          </div>
          <div className="flex flex-wrap gap-2">
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(e) => void pick(e.target.files?.[0] ?? null)} />
            <Button type="button" variant="secondary" size="md" loading={upload.isPending} onClick={() => fileRef.current?.click()}>
              <ImagePlus className="h-4 w-4" aria-hidden />{shop.logo_url ? "Change logo" : "Upload logo"}
            </Button>
            {shop.logo_url && <Button type="button" variant="ghost" size="md" onClick={() => void pick(null)}><Trash2 className="h-4 w-4" aria-hidden />Remove</Button>}
          </div>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="UPI ID" name="upi_vpa" defaultValue={shop.upi_vpa ?? ""} placeholder="yourshop@okaxis" disabled={!canUpi}
            hint={canUpi ? undefined : "Only the owner can change payment details."} />
          <Field label="Name shown on UPI" name="upi_payee_name" defaultValue={shop.upi_payee_name ?? shop.name} disabled={!canUpi} />
        </div>
      </Section>
    </form>
  );
}

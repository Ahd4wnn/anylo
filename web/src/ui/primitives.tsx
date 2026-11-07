import { CheckCircle2, X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { create } from "zustand";

/** Modal built on the native <dialog>: focus trap, Esc and backdrop handled by the browser. */
export function Dialog({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className="w-[min(480px,calc(100vw-32px))] rounded-xl border border-border bg-surface p-0 text-text shadow-e2 backdrop:bg-text/30"
    >
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <h2 className="text-lg font-semibold">{title}</h2>
        <button onClick={onClose} className="grid h-9 w-9 place-items-center rounded-md text-text-2 hover:bg-surface-2" aria-label="Close"><X className="h-5 w-5" /></button>
      </div>
      <div className="p-6">{open && children}</div>
    </dialog>
  );
}

interface ToastState { message: string | null; show: (m: string) => void }
export const useToast = create<ToastState>((set) => ({
  message: null,
  show: (message) => { set({ message }); setTimeout(() => set({ message: null }), 3000); },
}));

export function Toaster() {
  const message = useToast((s) => s.message);
  if (!message) return null;
  return (
    <div role="status" className="fixed bottom-24 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-lg bg-text px-4 py-3 text-sm font-medium text-surface shadow-e2 lg:bottom-6">
      <CheckCircle2 className="h-4 w-4" aria-hidden />{message}
    </div>
  );
}

export function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 py-1">
      <span><span className="block font-medium text-text">{label}</span>{hint && <span className="text-sm text-text-2">{hint}</span>}</span>
      <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-7 w-12 shrink-0 rounded-full transition-colors duration-200 ${checked ? "bg-primary" : "bg-border-strong"}`}>
        <span className={`absolute top-0.5 h-6 w-6 rounded-full bg-white shadow-e1 transition-transform duration-200 ease-brand ${checked ? "translate-x-[22px]" : "translate-x-0.5"}`} />
      </button>
    </label>
  );
}

export function Section({ title, description, children, footer }: { title: string; description?: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <section className="rounded-xl border border-border bg-surface">
      <div className="px-5 pt-5 sm:px-6 sm:pt-6">
        <h2 className="text-lg font-semibold">{title}</h2>
        {description && <p className="mt-1 text-sm text-text-2">{description}</p>}
      </div>
      <div className="space-y-5 p-5 sm:p-6">{children}</div>
      {footer && <div className="flex justify-end gap-3 border-t border-border px-5 py-4 sm:px-6">{footer}</div>}
    </section>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "success" | "warning" | "brand"; children: ReactNode }) {
  const tones = {
    neutral: "bg-surface-2 text-text-2", success: "bg-success-soft text-success",
    warning: "bg-warning-soft text-warning", brand: "bg-primary-soft text-on-primary-soft",
  };
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
}

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
        {description && <p className="mt-1 text-text-2">{description}</p>}
      </div>
      {action}
    </div>
  );
}

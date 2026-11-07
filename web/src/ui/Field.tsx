import { useId, type InputHTMLAttributes, type ReactNode } from "react";

export function Field({
  label, hint, error, trailing, ...input
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string; trailing?: ReactNode }) {
  const id = useId();
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-semibold text-text">{label}</label>
      <div className="relative">
        <input
          id={id}
          aria-invalid={!!error}
          aria-describedby={error || hint ? `${id}-msg` : undefined}
          {...input}
          className={`h-12 w-full rounded-md border bg-surface px-3.5 text-base text-text placeholder:text-text-3 transition-colors duration-100 focus:outline-none focus:border-primary focus:ring-4 focus:ring-primary/15 ${error ? "border-danger" : "border-border-strong"} ${trailing ? "pr-12" : ""}`}
        />
        {trailing && <div className="absolute inset-y-0 right-1 flex items-center">{trailing}</div>}
      </div>
      {(error || hint) && (
        <p id={`${id}-msg`} className={`text-sm ${error ? "text-danger" : "text-text-2"}`}>{error ?? hint}</p>
      )}
    </div>
  );
}

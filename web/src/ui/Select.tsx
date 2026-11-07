import { ChevronDown } from "lucide-react";
import { useId, type SelectHTMLAttributes } from "react";

export function Select({
  label, options, error, placeholder, ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & {
  label: string; options: { value: string; label: string }[]; error?: string; placeholder?: string;
}) {
  const id = useId();
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-semibold text-text">{label}</label>
      <div className="relative">
        <select
          id={id}
          aria-invalid={!!error}
          {...rest}
          className={`h-12 w-full appearance-none rounded-md border bg-surface pl-3.5 pr-10 text-base text-text focus:outline-none focus:border-primary focus:ring-4 focus:ring-primary/15 ${error ? "border-danger" : "border-border-strong"}`}
        >
          {placeholder && <option value="" disabled>{placeholder}</option>}
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <ChevronDown aria-hidden className="pointer-events-none absolute right-3 top-1/2 h-5 w-5 -translate-y-1/2 text-text-2" />
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}

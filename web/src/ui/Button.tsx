import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "accent" | "secondary" | "ghost" | "danger";
type Size = "md" | "lg" | "xl";

const variants: Record<Variant, string> = {
  primary: "bg-primary text-on-primary hover:bg-primary-hover",
  // Accent (Energy Orange) is reserved for money moments: Pay, Save bill, Subscribe. Always large.
  accent: "bg-accent text-on-accent hover:bg-accent-hover font-bold",
  secondary: "bg-surface text-text border border-border-strong hover:bg-surface-2",
  ghost: "text-primary hover:bg-tint",
  danger: "bg-danger text-white hover:opacity-90",
};
const sizes: Record<Size, string> = {
  md: "h-10 px-4 text-[15px]",
  lg: "h-12 px-5 text-base",
  xl: "h-14 px-6 text-lg",
};

export function Button({
  variant = "primary", size = "lg", loading = false, className = "", children, disabled, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean }) {
  const s = variant === "accent" && size === "md" ? "lg" : size;
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-md font-semibold transition-[background-color,transform] duration-100 ease-brand active:scale-[.98] disabled:opacity-50 disabled:pointer-events-none ${variants[variant]} ${sizes[s]} ${className}`}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

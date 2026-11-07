import type { Config } from "tailwindcss";

// Colours come only from tokens (src/styles/tokens.css, generated from design/tokens.json).
const tokens = [
  "bg", "surface", "surface-2", "tint", "border", "border-strong", "text", "text-2", "text-3",
  "primary", "primary-hover", "on-primary", "accent", "accent-hover", "on-accent", "brand",
  "deep", "on-deep", "highlight", "on-highlight", "success", "danger", "info",
  "pay-cash", "pay-upi", "pay-card", "pay-due",
];

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      white: "#FFFFFF",
      ...Object.fromEntries(tokens.map((t) => [t, `rgb(var(--${t}) / <alpha-value>)`])),
    },
    extend: {
      fontFamily: { sans: ["Inter", "Noto Sans", "system-ui", "sans-serif"] },
      borderRadius: { sm: "6px", md: "10px", lg: "14px", xl: "20px" },
      boxShadow: {
        e1: "0 1px 2px rgb(3 18 115 / .06)",
        e2: "0 8px 24px rgb(3 18 115 / .12)",
      },
      transitionTimingFunction: { brand: "cubic-bezier(.2,.8,.2,1)" },
    },
  },
} satisfies Config;

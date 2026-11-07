import Decimal from "decimal.js";

const inr = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const inrWhole = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** ₹1,25,450.75 (paise shown only when non-zero unless `always`). */
export function formatINR(value: Decimal.Value, opts: { always?: boolean } = {}): string {
  const d = new Decimal(value);
  const body = opts.always || !d.isInteger() ? inr.format(d.toNumber()) : inrWhole.format(d.toNumber());
  return `₹${body}`;
}

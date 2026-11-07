// Port of backend/app/services/gst/engine.py (docs/06-gst.md §5). Same fixtures, same results.
// Client-side preview only: the server recomputes and is authoritative.
import Decimal from "decimal.js";

const D = (v: Decimal.Value) => new Decimal(v);
const ZERO = D(0);
const q2 = (x: Decimal) => x.toDecimalPlaces(2, Decimal.ROUND_HALF_UP);

export type Scheme = "regular" | "composition" | "unregistered";
export type SupplyType = "intra" | "inter";

export interface LineIn {
  qty: Decimal.Value;
  unitPrice: Decimal.Value;
  rate?: Decimal.Value;
  cessRate?: Decimal.Value;
  priceIncludesTax?: boolean;
  lineDiscount?: Decimal.Value;
}

export interface InvoiceIn {
  lines: LineIn[];
  supplyType?: SupplyType;
  scheme?: Scheme;
  discountType?: "flat" | "percent" | null;
  discountValue?: Decimal.Value;
  roundOff?: boolean;
}

export interface LineOut {
  gross: Decimal; lineDiscount: Decimal; invoiceDiscountShare: Decimal; taxable: Decimal;
  rate: Decimal; cgst: Decimal; sgst: Decimal; igst: Decimal; cess: Decimal; total: Decimal;
}

export interface InvoiceOut {
  lines: LineOut[];
  subtotalGross: Decimal; discountTotal: Decimal; taxableTotal: Decimal;
  cgstTotal: Decimal; sgstTotal: Decimal; igstTotal: Decimal; cessTotal: Decimal;
  roundOff: Decimal; grandTotal: Decimal;
}

export class GstError extends Error {
  constructor(public code: string, message: string) { super(message); }
}

const sum = (xs: Decimal[]) => xs.reduce((a, b) => a.plus(b), ZERO);

function allocate(amount: Decimal, bases: Decimal[]): Decimal[] {
  const total = sum(bases);
  if (amount.isZero() || total.isZero()) return bases.map(() => ZERO);
  const shares = bases.map((b) => q2(amount.times(b).div(total)));
  let biggest = 0;
  bases.forEach((b, i) => { if (b.gt(bases[biggest])) biggest = i; });
  shares[biggest] = shares[biggest].plus(amount.minus(sum(shares)));
  return shares;
}

export function computeInvoice(inv: InvoiceIn): InvoiceOut {
  const supply = inv.supplyType ?? "intra";
  const scheme = inv.scheme ?? "regular";
  if (!inv.lines.length) throw new GstError("gst.empty", "Add at least one item to the bill.");
  if (scheme === "composition" && supply === "inter")
    throw new GstError("gst.composition_interstate_blocked", "Composition shops cannot sell goods to another state.");

  const bases = inv.lines.map((ln) => {
    const qty = D(ln.qty), price = D(ln.unitPrice), disc = D(ln.lineDiscount ?? 0);
    if (qty.lte(0)) throw new GstError("gst.qty_invalid", "Quantity must be more than zero.");
    if (price.lt(0) || disc.lt(0) || D(ln.rate ?? 0).lt(0))
      throw new GstError("gst.negative_value", "Prices, discounts and rates cannot be negative.");
    const gross = q2(price.times(qty));
    if (disc.gt(gross)) throw new GstError("gst.line_discount_too_large", "An item discount is more than the item price.");
    return gross.minus(disc);
  });

  const baseSum = sum(bases);
  let invDiscount = ZERO;
  if (inv.discountType === "percent") {
    const pct = D(inv.discountValue ?? 0);
    if (pct.lt(0) || pct.gt(100)) throw new GstError("gst.discount_invalid", "Discount percent must be between 0 and 100.");
    invDiscount = q2(baseSum.times(pct).div(100));
  } else if (inv.discountType === "flat") {
    invDiscount = D(inv.discountValue ?? 0);
    if (invDiscount.lt(0) || invDiscount.gt(baseSum))
      throw new GstError("gst.discount_invalid", "Discount cannot be more than the bill amount.");
  }

  const taxed = scheme === "regular";
  const intra = supply === "intra";
  const shares = allocate(invDiscount, bases);
  const lines: LineOut[] = inv.lines.map((ln, i) => {
    const net = bases[i].minus(shares[i]);
    const rate = taxed ? D(ln.rate ?? 0) : ZERO;
    const cessRate = taxed ? D(ln.cessRate ?? 0) : ZERO;
    let cgst = ZERO, sgst = ZERO, igst = ZERO, cess: Decimal, taxable: Decimal;
    if (ln.priceIncludesTax ?? true) {
      const k = rate.plus(cessRate).plus(100);
      cess = q2(net.times(cessRate).div(k));
      if (intra) cgst = sgst = q2(net.times(rate).div(k.times(2)));
      else igst = q2(net.times(rate).div(k));
      taxable = net.minus(cgst).minus(sgst).minus(igst).minus(cess);
    } else {
      taxable = net;
      cess = q2(taxable.times(cessRate).div(100));
      if (intra) cgst = sgst = q2(taxable.times(rate).div(200));
      else igst = q2(taxable.times(rate).div(100));
    }
    return {
      gross: q2(D(ln.unitPrice).times(D(ln.qty))), lineDiscount: D(ln.lineDiscount ?? 0),
      invoiceDiscountShare: shares[i], taxable, rate, cgst, sgst, igst, cess,
      total: taxable.plus(cgst).plus(sgst).plus(igst).plus(cess),
    };
  });

  const before = sum(lines.map((l) => l.total));
  const grandTotal = (inv.roundOff ?? true) ? before.toDecimalPlaces(0, Decimal.ROUND_HALF_UP) : before;
  return {
    lines,
    subtotalGross: sum(lines.map((l) => l.gross)),
    discountTotal: sum(lines.map((l) => l.lineDiscount.plus(l.invoiceDiscountShare))),
    taxableTotal: sum(lines.map((l) => l.taxable)),
    cgstTotal: sum(lines.map((l) => l.cgst)),
    sgstTotal: sum(lines.map((l) => l.sgst)),
    igstTotal: sum(lines.map((l) => l.igst)),
    cessTotal: sum(lines.map((l) => l.cess)),
    roundOff: grandTotal.minus(before),
    grandTotal,
  };
}

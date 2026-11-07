import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { computeInvoice, GstError, type InvoiceIn } from "./gst";

// The backend's fixture file is the single source of truth for every platform.
const data = JSON.parse(
  readFileSync(new URL("../../../backend/tests/fixtures/gst_cases.json", import.meta.url), "utf8"),
);
const camel = (s: string) => s.replace(/_(\w)/g, (_, c: string) => c.toUpperCase());

type Case = Record<string, any>;

const toInvoice = (c: Case): InvoiceIn => ({
  lines: c.lines.map((l: Case) => ({
    qty: l.qty, unitPrice: l.unit_price, rate: l.rate ?? "0",
    priceIncludesTax: l.price_includes_tax ?? true, lineDiscount: l.line_discount ?? "0",
  })),
  supplyType: c.supply_type, scheme: c.scheme, discountType: c.discount_type ?? null,
  discountValue: c.discount_value ?? "0", roundOff: c.round_off,
});

describe("GST engine matches backend fixtures", () => {
  for (const c of data.cases as Case[]) {
    it(c.id, () => {
      if (c.expect_error) {
        expect(() => computeInvoice(toInvoice(c))).toThrowError(GstError);
        try { computeInvoice(toInvoice(c)); } catch (e) { expect((e as GstError).code).toBe(c.expect_error); }
        return;
      }
      const out = computeInvoice(toInvoice(c)) as unknown as Record<string, any>;
      (c.expect.lines ?? []).forEach((line: Case, i: number) => {
        for (const [k, v] of Object.entries(line)) expect(out.lines[i][camel(k)].toFixed(2), `${c.id} ${i} ${k}`).toBe(Number(v).toFixed(2));
      });
      for (const [k, v] of Object.entries(c.expect)) {
        if (k !== "lines") expect(out[camel(k)].toFixed(2), `${c.id} ${k}`).toBe(Number(v).toFixed(2));
      }
    });
  }
});

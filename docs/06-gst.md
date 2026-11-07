# 06 · GST

Anylo must produce invoices that are correct under Indian GST law and export data a shop (or its CA) can file from. This doc is the spec for `backend/app/services/gst/`. The worked examples in §9 are **test fixtures**: they must pass byte-for-byte.

> ⚠️ GST rules and rates change, most recently with the September 2025 rate rationalization. That is why **rates, thresholds and HSN data are database rows, not code constants.** Get a Chartered Accountant to review this doc before launch and after any GST Council change.

## 1. Shop tax profile (`shops` + `shop_tax_profiles`)

| Field | Values | Effect |
|---|---|---|
| `gst_scheme` | `regular`, `composition`, `unregistered` | Decides the document type and whether tax is charged |
| `gstin` | 15-char, validated (§8) | Required for `regular` and `composition` |
| `legal_name`, `trade_name` | text | Printed on the invoice |
| `state_code` | 2-digit (§10) | Must match GSTIN[0:2]; decides intra- vs inter-state |
| `address`, `pincode` | text | Printed |
| `composition_rate` | decimal (e.g. 1.00) | Used only for the composition liability report |
| `prices_include_tax` | bool, default `true` | Default for new products (Indian retail usually prices MRP-inclusive) |
| `hsn_digits_required` | 4 or 6 | 4 if aggregate turnover ≤ ₹5 Cr, else 6 |
| `invoice_round_off` | bool, default `true` | Rounds the grand total to the nearest rupee |

**Document type by scheme:**

| Scheme | Taxable sale | Exempt / nil-rated-only sale |
|---|---|---|
| regular | **Tax Invoice** | **Bill of Supply** |
| composition | **Bill of Supply** with the declaration *"Composition taxable person, not eligible to collect tax on supplies"* | Bill of Supply |
| unregistered | **Invoice / Cash Memo**: no tax lines, no GSTIN | same |

A regular shop selling a mix of taxable and exempt items issues one Tax Invoice with 0% lines.

## 2. Product tax fields

| Field | Notes |
|---|---|
| `hsn_code` | 4–8 digits for goods; SAC (starting `99`) for services. Validated against shop `hsn_digits_required` for B2B |
| `tax_rate_id` | FK to `gst_rates` (§3) |
| `cess_rate` | decimal %, default 0 |
| `price_includes_tax` | overrides the shop default |
| `is_service` | prints SAC instead of HSN |

Bulk import accepts HSN and rate columns. Products with no rate on a `regular` shop block checkout with the message "Set a GST rate for <name>" (owner/manager can fix it inline).

## 3. Rate table (`gst_rates`, platform-managed)

```
id, label, rate NUMERIC(5,2), kind ('taxable'|'nil'|'exempt'|'non_gst'), effective_from, effective_to, is_active
```

Seed values after the 2025 rationalization:

| rate | kind |
|---|---|
| 0 | nil / exempt / non_gst |
| 0.25 | taxable |
| 3 | taxable |
| 5 | taxable |
| 18 | taxable |
| 40 | taxable |

Legacy 12% and 28% stay as inactive rows so old invoices still render. An admin screen manages the table, and changing it never rewrites past invoices because each line snapshots its rate.

## 4. Place of supply

- **Default:** the shop's `state_code` (an over-the-counter sale), so the sale is **intra-state → CGST + SGST** (UTGST in UTs without a legislature; printed as "UTGST" when the shop's state code is a UT).
- **B2B with a customer GSTIN:** place of supply defaults to the customer's GSTIN state. The cashier can override it (for example, goods delivered elsewhere).
- **Delivery to another state** (B2C): the cashier picks the delivery state.
- If `place_of_supply != shop.state_code`, the sale is **inter-state → IGST**.

The invoice stores `place_of_supply` (state code) and `supply_type` (`intra` | `inter`).

## 5. Calculation algorithm (per invoice)

All amounts are `Decimal`. `q2(x)` = quantize to 0.01 with ROUND_HALF_UP.

```
for each line:
    gross_i = q2(unit_price_i × qty_i)                       # unit_price is as entered (incl or excl)

invoice_discount = flat amount, or q2(Σ gross_i × pct / 100)
allocate invoice_discount across lines proportional to gross_i:
    d_i = q2(invoice_discount × gross_i / Σ gross)
    put the rounding remainder (invoice_discount − Σ d_i) on the line with the largest gross
line_discount_i (if the line has its own discount) is applied first, then the invoice discount is allocated on what remains.

net_i = gross_i − line_discount_i − d_i                      # still incl or excl as entered

if line is tax-inclusive:
    taxable_i = q2(net_i × 100 / (100 + rate_i + cess_i))
    tax_total_i = net_i − taxable_i                          # line total == net_i exactly
else:
    taxable_i = net_i
    tax_total_i computed below

intra-state:
    cgst_i = q2(taxable_i × rate_i / 2 / 100)
    sgst_i = cgst_i
    (inclusive lines: cgst_i = q2((tax_total_i − cess_amt_i) / 2); sgst_i = tax_total_i − cess_amt_i − cgst_i)
inter-state:
    igst_i = q2(taxable_i × rate_i / 100)   (inclusive: igst_i = tax_total_i − cess_amt_i)
cess_amt_i = q2(taxable_i × cess_i / 100)

line_total_i = taxable_i + cgst_i + sgst_i + igst_i + cess_amt_i

invoice:
    taxable_total = Σ taxable_i;  cgst_total = Σ cgst_i;  …
    total_before_round = Σ line_total_i
    grand_total = round_half_up(total_before_round, 0) if round_off else total_before_round
    round_off = grand_total − total_before_round                 # printed, in [-0.50, +0.50]
```

**Rules**
- Tax is computed **per line and then summed**, never on the invoice total. Printed line amounts must add up exactly.
- Composition and unregistered shops: `rate_i` is treated as 0 for calculation, and lines show no tax.
- Prices below 0, quantity ≤ 0, or a discount greater than gross are rejected.
- Line `unit_price` and `rate` are **snapshotted** on the invoice line.

## 6. Invoice numbering

- Series table `doc_series(shop_id, doc_type, prefix, fy, next_seq)`. Doc types:
  - `invoice`
  - `bill_of_supply`
  - `credit_note`
  - `debit_note`
  - `receipt` (payment receipts)
- The number is `prefix + FY + "/" + zero-padded seq`, for example `AN/25-26/00042`. **≤ 16 characters**, using only `A–Z 0–9 / -`, unique within the financial year (1 Apr – 31 Mar).
- Allocation: `UPDATE doc_series SET next_seq = next_seq + 1 WHERE … RETURNING next_seq - 1`, inside the checkout savepoint. That makes it gapless and race-free (the PlantBill pattern).
- A new FY row is created lazily on the first document of the year.
- **Cancelled invoices keep their number.** Status `cancelled` and amounts are zeroed in reports; the series still counts them in "documents issued".
- Invoices are never deleted.

## 7. Mandatory invoice contents (Rule 46 checklist)

The printed and PDF invoice must show:
1. Supplier legal/trade name, address, GSTIN.
2. Document title (Tax Invoice / Bill of Supply).
3. Invoice number and date.
4. Recipient name, address and GSTIN (B2B). For B2C, name and address are required when the invoice value ≥ ₹50,000; otherwise optional.
5. Place of supply (state name + code), required when inter-state; Anylo always prints it.
6. Per line: description, HSN/SAC, quantity, unit (UQC), rate, taxable value, tax rate, and tax amounts split CGST/SGST or IGST (+ cess).
7. Totals: taxable value, each tax, round-off, grand total, **amount in words** (Indian system: lakh/crore).
8. "Whether tax is payable on reverse charge: No."
9. Signature or "This is a computer-generated invoice" + authorised signatory name.
10. Composition declaration when applicable.

The 58 mm thermal receipt layout is in `07-pos-billing.md`. It prints a compact form with the same mandatory fields and a per-rate tax summary instead of per-line tax columns.

## 8. GSTIN validation

1. Format: `^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$`.
2. The first two digits must be a valid state code (§10).
3. The 15th character is a checksum. Map characters `0–9A–Z` to 0–35. For the first 14 characters, multiply each value by a factor that alternates 1, 2, 1, 2, … starting at 1. For each product `p`, add `p // 36 + p % 36` to the sum. Check value = `(36 − sum % 36) % 36`, mapped back to a character.

Validate on shop setup and on B2B customer entry. v1 does no online GSTIN lookup; it is planned later via a GSP API.

## 9. Worked examples (test fixtures)

Shop is in Kerala (32), regular scheme, round-off on.

**E1: intra-state, tax-exclusive**

| Item | Qty | Price | Rate | Taxable | CGST | SGST | Total |
|---|---|---|---|---|---|---|---|
| A | 2 | 100.00 | 18 | 200.00 | 18.00 | 18.00 | 236.00 |
| B | 1 | 50.50 | 5 | 50.50 | 1.26 | 1.26 | 53.02 |
| **Σ** | | | | 250.50 | 19.26 | 19.26 | 289.02 |

Round-off −0.02 → **Grand total 289.00**.

**E2: intra-state, tax-inclusive (MRP pricing)**

| Item | Qty | Price (incl) | Rate | Gross | Taxable | CGST | SGST | Total |
|---|---|---|---|---|---|---|---|---|
| C | 1 | 118.00 | 18 | 118.00 | 100.00 | 9.00 | 9.00 | 118.00 |
| D | 3 | 99.00 | 5 | 297.00 | 282.86 | 7.07 | 7.07 | 297.00 |
| **Σ** | | | | 415.00 | 382.86 | 16.07 | 16.07 | 415.00 |

Round-off 0.00 → **415.00**. (For D: 297 × 100 / 105 = 282.857… → 282.86; tax 14.14 → 7.07 + 7.07.)

**E3: inter-state B2B** (customer GSTIN starts with 29, Karnataka; place of supply 29)

| Item | Qty | Price | Rate | Taxable | IGST | Total |
|---|---|---|---|---|---|---|
| E | 10 | 1,250.00 | 18 | 12,500.00 | 2,250.00 | 14,750.00 |

**Grand total 14,750.00.**

**E4: invoice discount ₹50 flat, exclusive, intra-state**

| Item | Gross | Disc share | Taxable | Rate | CGST | SGST | Total |
|---|---|---|---|---|---|---|---|
| F | 300.00 | 30.00 | 270.00 | 18 | 24.30 | 24.30 | 318.60 |
| G | 200.00 | 20.00 | 180.00 | 5 | 4.50 | 4.50 | 189.00 |
| **Σ** | 500.00 | 50.00 | 450.00 | | 28.80 | 28.80 | 507.60 |

Round-off +0.40 → **508.00**.

**E5: discount remainder.** ₹10 flat over three equal lines of ₹100.00: shares are 3.33, 3.33, 3.33 = 9.99, so the remainder 0.01 goes to the largest line (the first one on a tie, by line order). Result: 3.34, 3.33, 3.33.

**E6: composition shop.** Same items as E1 → Bill of Supply, no tax lines. Total 200.00 + 50.50 = 250.50; half-up to the rupee → round-off **+0.50**, **grand total 251.00**. (This fixture locks in half-up behaviour at exactly ₹0.50.)

**E7: amount in words.** 1,25,450.75 → "Rupees One Lakh Twenty-Five Thousand Four Hundred Fifty and Seventy-Five Paise Only".

## 10. State codes (seed `gst_states`)

| Code | State / UT | Code | State / UT |
|---|---|---|---|
| 01 | Jammu & Kashmir (UT) | 20 | Jharkhand |
| 02 | Himachal Pradesh | 21 | Odisha |
| 03 | Punjab | 22 | Chhattisgarh |
| 04 | Chandigarh (UT) | 23 | Madhya Pradesh |
| 05 | Uttarakhand | 24 | Gujarat |
| 06 | Haryana | 26 | Dadra & Nagar Haveli and Daman & Diu (UT) |
| 07 | Delhi (UT) | 27 | Maharashtra |
| 08 | Rajasthan | 29 | Karnataka |
| 09 | Uttar Pradesh | 30 | Goa |
| 10 | Bihar | 31 | Lakshadweep (UT) |
| 11 | Sikkim | 32 | Kerala |
| 12 | Arunachal Pradesh | 33 | Tamil Nadu |
| 13 | Nagaland | 34 | Puducherry (UT) |
| 14 | Manipur | 35 | Andaman & Nicobar Islands (UT) |
| 15 | Mizoram | 36 | Telangana |
| 16 | Tripura | 37 | Andhra Pradesh |
| 17 | Meghalaya | 38 | Ladakh (UT) |
| 18 | Assam | 97 | Other Territory |
| 19 | West Bengal | 96 | Other Country (exports, not in v1) |

Codes 25 (old Daman & Diu) and 28 (old Andhra Pradesh) are accepted only on legacy GSTINs. UTs that use UTGST instead of SGST: 04, 26, 31, 35, 38, 97.

## 11. Returns: credit notes and debit notes

- A **sales return** creates a **credit note** that references the original invoice number and date. It must use the same rates and place of supply as the original, at the pro-rata taxable value of the returned quantity.
- Partial returns are allowed. Returned quantity is capped at sold quantity minus already-returned quantity.
- Refund modes: cash, UPI, original method, or **store credit** (customer ledger).
- Stock goes back in (`08-inventory.md`) unless it is marked damaged.
- Time limit: a credit note can be issued up to **30 November after the end of the FY** of the original invoice (or the annual return date, if earlier). After that, the UI blocks the credit note and suggests a non-GST adjustment.
- **Debit notes** (price increase after the sale) are rare in retail and are API-only in v1.

## 12. Purchases and input tax credit

- Purchase entries (`08-inventory.md`) record:
  - supplier GSTIN
  - supplier invoice number and date
  - per-line taxable value
  - CGST/SGST/IGST/cess
  - the `itc_eligible` flag
- They feed the GSTR-3B Table 4 ITC estimate. **This is not a reconciliation with GSTR-2B.** v1 shows a "compare with your 2B" checklist only.

## 13. GST reports (`09-finance-reports-goals.md`)

| Report | Content | Format |
|---|---|---|
| **GSTR-1** | **B2B**: invoices to GSTINs, rate-wise<br>**B2CL**: inter-state B2C invoices > ₹1,00,000, per invoice<br>**B2CS**: all other B2C, grouped by place of supply + rate<br>**CDNR / CDNUR**: credit notes to registered / unregistered customers<br>**HSN summary**: split B2B / B2C, HSN + UQC + qty + taxable + taxes<br>**Documents issued** (Table 13): series ranges, total, cancelled<br>**Nil / exempt** | XLSX in the layout of the GST offline tool sheets, plus JSON (best effort; the portal schema version is recorded in the file) |
| **GSTR-3B summary** | 3.1(a) outward taxable; 3.1(c) nil/exempt; 4(A)(5) ITC from purchases; net tax payable by head | XLSX + on-screen |
| **CMP-08 helper** (composition) | Quarterly turnover × composition rate | XLSX + on-screen |
| **Sales register / purchase register** | Line-level with all tax columns | XLSX / CSV |

Every GST export carries a header row with GSTIN, period, generated-at, and the disclaimer *"Prepared by Anylo for filing assistance. Verify before filing."*

## 14. Out of scope for v1

- **E-invoicing (IRN/QR):** needed only when aggregate turnover is > ₹5 Cr.
- E-way bills.
- Reverse charge.
- Exports and SEZ.
- TCS for e-commerce.
- Direct GSTR-1 filing through a GSP.

The data model keeps room for these: `invoices.irn`, `invoices.ack_no`, `invoices.signed_qr` (nullable).

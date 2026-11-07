# 07 · POS & billing

Goal: **a 3-item cash bill in under 10 seconds** on a phone, and faster on a desktop with a scanner.

## 1. Adding items

| Method | Web | Android | Notes |
|---|---|---|---|
| Tap product tile | ✅ | ✅ | Grid with photo; list mode for big catalogues |
| Search | ✅ | ✅ | Name / SKU / barcode / brand, trigram + local index. **Enter** adds the top hit |
| Barcode: USB/Bluetooth HID scanner | ✅ | ✅ | Keyboard-wedge: a burst of keystrokes < 50 ms apart ending in Enter while not focused in a text field → `GET /products/lookup?barcode=` |
| Barcode: camera | ✅ (`BarcodeDetector` API, ZXing-wasm fallback) | ✅ (ML Kit barcode scanning, CameraX) | Continuous scan mode: each scan adds +1, with a beep and haptic |
| Voice | ✅ (Web Speech, en-IN) | ✅ (RecognizerIntent) | PlantBill `PhoneticMatcher`, generalized. Shows top 3 matches; **never auto-adds below 0.6 confidence** |
| Custom line | ✅ | ✅ | Name, price, qty, GST rate (default shop's most common rate), HSN optional. **Not saved to the catalogue** (fixes PlantBill's "Quick Add" pollution); optional "Save as product" checkbox for O/M |
| Weighing items | ✅ | ✅ | Units with `allows_decimal` open a qty keypad that accepts 0.001 steps, or price-to-qty ("₹50 worth of X") |

**Variants:** tapping a product that has variants opens a variant picker (chips). Scanning a barcode resolves straight to the variant.

**Same item twice:** adds to the existing line's quantity. A long-press or "Split line" creates a separate line, for example for a different price.

## 2. Cart

Each line has qty stepper, unit price (editable by O/M; by S only if `settings.staff_can_edit_price`), line discount and a remove action.
- Price below cost triggers a warning; for S it is blocked.
- Totals come from `POST /invoices/preview`, debounced 250 ms. The client also computes them locally with the same GST algorithm, so the UI never waits. The server result wins if the two differ.
- Invoice discount: flat ₹ or %. Above `max_discount_pct` → approval (§6).
- Customer:
  - Optional; phone lookup (10 digits) shows name, last visit and outstanding balance.
  - A **B2B toggle** reveals GSTIN (validated), billing name, address and state. Place of supply then defaults to the GSTIN state.
  - Walk-in is the default.
- Remarks: free text, printed.
- **Hold:** saves the cart to `held_bills` (server) and to local storage. A "Held (3)" chip lists them. Resuming a held bill while a cart is open parks the current cart first.
- **Cart persistence:** web keeps the cart in IndexedDB and Android in DataStore, so a refresh or crash doesn't lose it.

## 3. Payment

Methods: **Cash, UPI, Card, Due (credit), Split.**
- **Cash:** optional "received" field shows change to return.
- **UPI:**
  - Shows a QR generated **locally** from `upi://pay?pa=<vpa>&pn=<name>&am=<total>&tn=<invoice no>&cu=INR`.
  - The cashier confirms "Received" (no gateway confirmation in v1).
  - An optional UPI ref can be entered.
- **Card:** external terminal; enter the last 4 digits / approval code (optional).
- **Due:**
  - Needs a customer with a phone number.
  - Checks `credit_limit` (warn; O/M can override).
- **Split:** any combination. The remaining amount auto-fills the last field. Save is enabled only when Σ = grand total (paise-exact).

## 4. Checkout

1. The client generates an `Idempotency-Key` when the payment sheet opens. The same key is reused on retry until the request succeeds.
2. `POST /invoices`. The server, in a single transaction:
   - validates permissions, subscription and stock (`allow_negative_stock`);
   - recomputes everything (`06-gst.md` §5);
   - allocates the number;
   - writes the invoice, lines, payments and stock movements (`sale`);
   - upserts the customer;
   - enqueues the WhatsApp job;
   - writes the audit row.
3. Response: the full invoice.
4. The UI shows a **success screen** with the number and total, plus big buttons:
   - **New bill** (default focus; Enter)
   - **Print**
   - **WhatsApp**
   - **PDF**
   - **Share link**

   If the printer is set to auto-print, the receipt prints immediately.

**Failure handling:**
- On network failure the cart stays, with "Retry" using the same key.
- On 402 (subscription read-only) a dialog explains the problem and links the owner to pay; the cart is kept as a held bill.

## 5. After the sale

| Action | Who | Rule |
|---|---|---|
| Reprint / share | O M S | Any time |
| Edit | O M | Same business day, and not in a period the owner marked "GST filed". Creates an audit entry with the before/after diff and sets `is_edited`. Stock movements are re-posted as a diff. |
| Cancel | O M | Number kept, status `cancelled`, stock reversed, payments reversed (refund recorded). Reason required. |
| Return / exchange | O M (S → approval) | Credit note (`06-gst.md` §11). Exchange = credit note + new invoice paid with store credit |
| Collect due | O M S | Against the invoice or the customer (FIFO). S creates `pending_approval` payments; cash isn't counted as "in hand" until approved. Prints a payment receipt (`RCPT/25-26/0001`) |

## 6. Approvals

The following create an approval request:
- discount above the limit
- returns by a salesperson
- due collections by a salesperson
- a salesperson's day close

Two ways to approve:
- **On the spot:** a manager enters their PIN on the same device (`POST /approvals/pin`). The bill goes through immediately.
- **Later:** the request appears in the manager's Approvals inbox, and the bill is saved as a **held bill** tagged "awaiting approval".

## 7. Receipts and printing

### Thermal (58 mm = 384 dots, 80 mm = 576 dots)
- **Rendered as a bitmap on the client** and sent as ESC/POS raster (`GS v 0`), so ₹ and every Indic script print correctly. Ported from PlantBill Android `ReceiptRenderer` + `RasterEscPos`. The web gets the same renderer on `<canvas>`.
- The server returns a structured `ReceiptModel` (`GET /invoices/{id}/receipt`). Each client lays it out, so web, Android and iOS look identical.
- Connection:
  - Web: Web Bluetooth (BLE printers), Web Serial, WebUSB.
  - Android: Classic Bluetooth SPP + USB host.
  - iOS: BLE printers only.
  - All clients use connect → print → disconnect with a mutex, so several devices can share one printer (PlantBill pattern).
- Settings: paper width, auto-cut, auto-print, copies, logo on/off, footer text, language of labels.

**Thermal tax-invoice layout (58 mm):**
```
            [LOGO]
        SHOP TRADE NAME
   Address line, City - PIN
 GSTIN: 32ABCDE1234F1Z5  Ph: 98xxxxxx
          TAX INVOICE
 No: AN/25-26/00042   08-11-2026 14:32
 Bill to: Ravi K (98xxxx1234)
 POS: Kerala (32)
 --------------------------------
 Item              Qty   Rate   Amt
 Basmati Rice 5kg    1  540.00 540.00
  HSN 1006  GST 5%
 Pen Blue x10        2   50.00 100.00
  HSN 9608  GST 18%
 --------------------------------
 Taxable value                599.02
 CGST                          20.49
 SGST                          20.49
 Round off                     +0.00
 TOTAL                     ₹  640.00
 Rupees Six Hundred Forty Only
 Paid: UPI 640.00
 --------------------------------
 GST   Taxable   CGST   SGST
 5%     514.28   12.86  12.86
 18%     84.74    7.63   7.63
 --------------------------------
   Thank you! Visit again.
   Computer generated invoice
        [QR: public link]
```
Prices are tax-inclusive (MRP). The figures follow `06-gst.md` §5 (see fixture E2b for the rice line).

### A4/A5 PDF
- Generated server-side with WeasyPrint (HTML templates; better Indic text shaping than reportlab). Fonts: Noto Sans + Noto Sans {Devanagari, Malayalam, Tamil, Kannada}.
- Full Rule 46 layout: per-line tax columns, HSN summary table, bank/UPI details, terms, signature block.
- Cached at `MEDIA_ROOT/invoices/{shop}/{fy}/{number}.pdf`. Regenerated when the invoice is edited.

### WhatsApp
- Meta Cloud API template `anylo_invoice` (customer name, invoice no., amount, link) + the PDF document.
- Sent only with consent (a phone given at checkout = consent; opt-out is honoured). Requires `WHATSAPP_ENABLED`.
- Fallback when the API is off: a `wa.me` deep link with prefilled text + public link.

### Public link
- `https://anylo.in/i/<public_token>`: a mobile-friendly invoice view with a PDF download.
- The customer phone is masked. The token is random (not the invoice UUID) and can be revoked by regenerating it.

## 8. Day close

At the end of the day:
1. The cashier taps **Close day**, sees expected cash (opening + cash sales + cash collections − cash expenses − cash labour − cash repayments + cash borrowed), enters the counted cash and adds a note.
2. If O/M confirm and the difference is ≠ 0, it is flagged on the dashboard.
3. The next day's opening cash = counted cash.

This replaces PlantBill's editable "cash in hand base" with an auditable daily trail. The running "cash in hand" figure is still shown.

## 9. Keyboard shortcuts (web POS)

| Key | Action |
|---|---|
| `/` or `F2` | Focus search |
| `Enter` (in search) | Add top result |
| `+` / `-` | Qty of the selected line |
| `F4` | Customer |
| `F6` | Discount |
| `F8` | Hold bill |
| `F9` | Held bills |
| `F10` | Pay |
| `F12` | Pay cash exact & save |
| `Esc` | Close dialog / back |
| `Ctrl+P` | Print last invoice |

All shortcuts are shown in a `?` overlay.

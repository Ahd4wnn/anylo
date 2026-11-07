# 08 · Inventory

"Sell anything": products of any kind, in any unit, with stock that stays right without manual effort.

## 1. Product model

- **Product** = what the customer recognises ("Basmati Rice", "Cotton Kurta").
  - Holds the shared data: category, brand, HSN, GST rate, unit, photo, `track_stock`.
- **Variant** = what is actually sold and counted ("5 kg", "Red / M").
  - Holds SKU, barcode, MRP, sale price, cost price, stock and reorder level.
  - A simple product has exactly one hidden default variant, so billing, stock and reports only ever deal with variants.
- **Services** (alteration, repair, delivery charge): `is_service = true`, `track_stock = false`, SAC code.

### Business-type presets
At signup the shop picks a business type. That type seeds:
- categories
- common units
- a default GST rate suggestion
- an optional starter catalogue of generic items at ₹0 for the owner to price

The starter catalogues live in `backend/app/data/presets/<type>.yaml`:

| Business type | Examples |
|---|---|
| grocery | Rice, Atta, Sugar, Oil (KGS/LTR) |
| apparel | Shirt, Kurta, Jeans with size variants |
| electronics | Charger, Cable, Earphones |
| hardware | Screws (BOX), Pipe (MTR), Paint (LTR) |
| stationery | Pens (NOS), Notebooks |
| nursery | PlantBill's list moves here |
| pharmacy | Categories only; batch/expiry is a later feature |

## 2. Catalogue management

| Feature | Detail |
|---|---|
| Create / edit | Single form. **Variants** section: add a size or colour axis, then the grid generates combinations (max 100). Bulk-edit prices across variants |
| SKU | Auto `AN-000001` per shop if blank; editable; unique |
| Barcode | Scan into the field with the camera or a HID scanner. Unique per shop. "Generate" creates an internal EAN-13 using the GS1 restricted-circulation prefix `2` plus a check digit |
| Labels | `POST /products/labels`: PDF with Code128/EAN-13, name, price, MRP. Layouts: A4 65-up, A4 24-up, 50×25 mm roll for label printers |
| Photos | One per product (JPEG/PNG/WebP ≤ 5 MB). Re-encoded to WebP at 800 px server-side; a 200 px thumbnail is generated |
| Import | CSV/XLSX template columns: `name, variant, category, brand, sku, barcode, hsn, gst_rate, unit, mrp, sale_price, cost_price, opening_stock, reorder_level, price_includes_tax`. Two steps: **dry run** shows row-level errors and a create/update count; **commit** runs in one transaction. Upsert key: SKU, then barcode, then name+variant |
| Export | Same columns, so export → edit → import round-trips |
| Archive | Hides the product from POS and search. History stays. Restore any time |

## 3. Stock ledger

`stock_movements` is the **source of truth**. `product_variants.stock_qty` is a cache updated in the same transaction. A nightly job (`stock.verify`) recomputes the cache and logs any drift.

| Event | Movement kind | qty sign | unit_cost |
|---|---|---|---|
| Opening stock (create/import) | `opening` | + | cost_price |
| Purchase posted | `purchase` | + | purchase line landed unit cost |
| Invoice issued | `sale` | − | current avg cost (snapshotted on the invoice line for COGS) |
| Invoice cancelled | `sale` (reversal) | + | original |
| Invoice edited | diff of old vs new lines | ± | |
| Credit note with restock | `sale_return` | + | original line cost |
| Return marked damaged | `damage` | 0 net (no restock) | recorded for loss reporting |
| Purchase cancelled / returned to supplier | `purchase_return` | − | |
| Manual adjustment (stock count) | `adjustment` | ± | avg cost |
| Damage / expiry write-off | `damage` | − | avg cost |

**Negative stock:** controlled by `settings.allow_negative_stock`. It defaults to **true** for new shops, because owners rarely enter opening stock on day one and blocking sales would hurt adoption. Negative items show in the "Fix your stock" list.

**Costing:** weighted average cost. When a purchase is posted:

```
new_avg = (old_qty × old_avg + purchased_qty × purchase_unit_cost) / (old_qty + purchased_qty)
```

Taxable cost is used, excluding GST when the ITC is eligible. If `old_qty ≤ 0`, then `new_avg = purchase_unit_cost`. COGS for a sale = qty × avg cost at sale time.

## 4. Suppliers & purchases

- **Supplier:** name, GSTIN (validated), phone, state, address, opening balance (what we owe them).
- **Purchase entry:**
  - Header: supplier, their invoice number and date.
  - Lines: variant (scan or search) or a new product inline, qty, unit cost, discount, GST rate.
  - The GST engine is reused, with the place of supply derived from the supplier state.
  - Statuses:
    - **Draft:** editable.
    - **Posted:** stock in, costs updated, payable created.
    - **Cancelled:** movements reversed.
- **Payments to suppliers** use the `payments` table (direction `out`, `party_type='supplier'`). The supplier ledger shows the running balance.
- **Purchase register** and **ITC summary** feed GSTR-3B Table 4 (`06-gst.md` §12).
- **Quick restock:** the low-stock list has a "Create purchase" button that pre-fills a draft with the suggested qty (`reorder_level × 2 − stock`, minimum 1).

## 5. Alerts and insights

| Item | Behaviour |
|---|---|
| Low stock | Triggered when `stock_qty ≤ reorder_level` after a movement. Creates an in-app notification (batched hourly per shop). Shown on the dashboard |
| Dead stock | No sale in 60 days and stock > 0. Report section + AI tool |
| Fast movers | Top variants by qty and revenue over 30 days |
| Stock value | Σ qty × avg cost, by category |
| Margin | (sale price − avg cost) / sale price per variant. Variants with negative margin are flagged |

## 6. Stock count (stocktake)

1. Start a count, optionally filtered by category.
2. Scan or enter counted qty per variant (on mobile, scanning increments by 1).
3. Review: expected vs counted vs variance (qty and ₹).
4. Post: creates `adjustment` movements, with the count id as the reference.

Partial counts are allowed. Uncounted items are untouched.

## 7. Out of scope (v1)

- Batch and expiry tracking (pharmacy).
- Serial numbers / IMEI.
- Multi-warehouse and transfers (the movement kinds exist but have no UI).
- Purchase orders sent to suppliers.
- Bill of materials / manufacturing.

# 04 · Data model

PostgreSQL 16. Conventions:
- PK `id uuid DEFAULT gen_random_uuid()`.
- Every tenant table has `shop_id uuid NOT NULL REFERENCES shops ON DELETE CASCADE` and RLS (`02-architecture.md` §4). 🔒 marks PII tables that exclude `support`.
- Money is `NUMERIC(12,2)`, quantities are `NUMERIC(12,3)`, rates are `NUMERIC(5,2)`.
- `created_at timestamptz DEFAULT now()`. Mutable tables also get `updated_at` (trigger).
- **Soft delete** `deleted_at timestamptz` on money and master tables. Default queries filter `deleted_at IS NULL`.
- Enums are `text` + `CHECK`, so they are easy to evolve in migrations.
- Index every FK, plus `(shop_id, created_at DESC)` on transactional tables.

## 1. Identity & tenancy

**users**
| column | type | notes |
|---|---|---|
| email | citext UNIQUE | login |
| phone | text | optional, 10-digit Indian mobile |
| full_name | text | |
| password_hash | text | argon2id |
| pin_hash | text NULL | manager approval PIN |
| role | text | `admin, support, owner, manager, salesperson` |
| shop_id | uuid NULL | required for manager/salesperson; NULL otherwise (CHECK) |
| is_active | bool | |
| token_version | int DEFAULT 0 | bump to revoke all sessions |
| preferred_language | text DEFAULT 'en' | `en, hi, ml, ta, kn` |
| last_login_at | timestamptz | |

**auth_sessions**: refresh tokens
| column | notes |
|---|---|
| user_id | FK |
| refresh_hash | sha256 of the token; rotated on every refresh |
| family_id | uuid; reuse of a rotated token revokes the whole family |
| device_label, platform | `web/android/ios`, user agent summary |
| expires_at, revoked_at, last_used_at | |

**password_reset_tokens**: `user_id, token_hash, expires_at, used_at`.

**shops**
| column | notes |
|---|---|
| name | display name |
| business_type | `general, grocery, apparel, electronics, hardware, pharmacy, stationery, nursery, other` (drives preset categories and units) |
| phone, email, address_line1/2, city, pincode, state_code | |
| timezone | default `Asia/Kolkata` |
| logo_path | |
| upi_vpa, upi_payee_name | for QR |
| settings | jsonb: `max_discount_pct`, `allow_negative_stock`, `receipt_width_mm`, `receipt_footer`, `whatsapp_auto_send`, `default_payment_method`, `low_stock_alerts`, … |
| is_active | |
| onboarding_completed_at | |
| deleted_at | soft delete with 30-day restore window |

**shop_tax_profiles** (1:1 shop): `gst_scheme, gstin, legal_name, trade_name, state_code, composition_rate, prices_include_tax, hsn_digits_required, invoice_round_off` (see `06-gst.md` §1).

**shop_owners**: `(shop_id, owner_id)` PK. Many-to-many.

## 2. Subscription (platform-owned; RLS: owner reads own shop rows)

**plans**: `code ('standard_monthly'), name, price NUMERIC(12,2) (599.00, **GST-inclusive**), price_includes_tax bool (true), gst_rate (18), interval ('month'), razorpay_plan_id, is_active`.

**subscriptions** (1 per shop)
| column | notes |
|---|---|
| shop_id | UNIQUE |
| plan_id | |
| status | `trialing, active, past_due, grace, expired, cancelled, comped` |
| trial_ends_at | created_at + 30 days |
| current_period_start, current_period_end | |
| grace_ends_at | |
| razorpay_subscription_id, razorpay_customer_id | |
| cancel_at_period_end | bool |
| comped_until | admin-granted free period |

**subscription_payments**: `subscription_id, razorpay_payment_id UNIQUE, razorpay_invoice_id, amount, tax_amount, status, paid_at, platform_invoice_no`.

**razorpay_events**: `event_id UNIQUE, event_type, payload jsonb, received_at, processed_at, error`, so webhook handling is idempotent.

## 3. Catalogue & inventory

**categories**: `shop_id, name, parent_id NULL, sort_order`. Unique `(shop_id, lower(name))`.

**units** (platform seed + shop custom): `code (UQC: NOS, KGS, GMS, LTR, MLT, MTR, BOX, PCS, PAC, DOZ, SET, PRS…), label, allows_decimal bool, shop_id NULL`.

**products**
| column | notes |
|---|---|
| shop_id, category_id | |
| name, description | |
| brand | text NULL |
| hsn_code, is_service | |
| tax_rate_id → gst_rates, cess_rate | |
| price_includes_tax | |
| unit_code | |
| track_stock | bool (services/custom = false) |
| has_variants | bool |
| photo_path | |
| deleted_at | archive; past invoices keep their snapshots |

**product_variants** (always ≥ 1 per product; a simple product has one default variant)
| column | notes |
|---|---|
| product_id, shop_id | |
| name | e.g. "500 g", "Red / M"; NULL for default |
| sku | unique per shop, auto `AN-000123` if blank |
| barcode | unique per shop when not NULL (EAN-13/UPC/Code128/custom) |
| mrp, sale_price, cost_price | cost = weighted average, updated by purchases |
| reorder_level | for low-stock alerts |
| stock_qty | NUMERIC(12,3), cache of Σ movements, updated in the same transaction |
| is_active | |

**stock_movements** (append-only ledger)
| column | notes |
|---|---|
| variant_id, shop_id | |
| kind | `opening, purchase, sale, sale_return, purchase_return, adjustment, damage, transfer_in, transfer_out` |
| qty | signed |
| unit_cost | for valuation |
| ref_type, ref_id | invoice / purchase / adjustment id |
| reason, created_by | |

**stock_counts**: `shop_id, name, category_id NULL, status ('open','posted','cancelled'), started_by, posted_by, posted_at`.
**stock_count_lines**: `count_id, shop_id, variant_id, expected_qty (snapshot at start), counted_qty, variance_qty, variance_value`. Unique `(count_id, variant_id)`. Posting creates `adjustment` movements (`08-inventory.md` §6).

**suppliers**: `shop_id, name, gstin, phone, email, address, state_code, opening_balance, deleted_at`.

**purchases**
| column | notes |
|---|---|
| supplier_id, shop_id | |
| supplier_invoice_no, supplier_invoice_date | |
| place_of_supply, supply_type | |
| taxable_total, cgst_total, sgst_total, igst_total, cess_total, round_off, grand_total | |
| itc_eligible | bool |
| status | `draft, posted, cancelled` |
| idempotency_key | |
| notes, created_by | |

**purchase_lines**: `purchase_id, shop_id, variant_id, description, hsn_code, qty, unit_cost, discount, taxable, tax_rate, cgst, sgst, igst, cess, line_total`.

**supplier_payments**: same shape as customer payments (§5), references `purchase_id`.

## 4. Customers

**customers** 🔒
| column | notes |
|---|---|
| shop_id | |
| name, phone | unique `(shop_id, phone)` when phone not NULL |
| email | |
| gstin, billing_address, state_code | B2B |
| credit_limit | NULL = unlimited |
| opening_balance | |
| whatsapp_consent, whatsapp_opted_out_at | |
| notes, tags text[] | |
| deleted_at | |

**customer_ledger** (view or materialized via entries): built from invoices (debit for the due part), payments received (credit), credit notes (credit) and store credit used. The customer balance is `Σ debit − Σ credit`. It is implemented as the SQL view `customer_balances`, and the API reads from the view.

## 5. Sales

**invoices**
| column | notes |
|---|---|
| shop_id | |
| doc_type | `invoice, bill_of_supply, cash_memo` |
| series_id, number | `number` unique per `(shop_id, doc_type, fy)` |
| fy | `'25-26'` |
| issued_at | timestamptz |
| customer_id | NULL for walk-in |
| buyer snapshot | `buyer_name, buyer_phone, buyer_gstin, buyer_address, buyer_state_code` |
| place_of_supply, supply_type | `intra/inter` |
| is_b2b | bool (buyer_gstin present) |
| subtotal_gross | Σ line gross before discounts |
| discount_type, discount_value, discount_total | |
| taxable_total, cgst_total, sgst_total, igst_total, cess_total | |
| round_off, grand_total | |
| paid_total, due_total | `due_total = grand_total − paid_total − credit-noted amount` (kept updated) |
| status | `issued, cancelled` |
| cancel_reason, cancelled_at, cancelled_by | |
| is_edited | |
| idempotency_key | unique `(shop_id, idempotency_key)` |
| created_by, created_by_name | snapshot |
| remarks | |
| irn, ack_no, signed_qr | NULL (e-invoice later) |
| public_token | random 22-char token for the share link (not the PK) |

**invoice_lines**
| column | notes |
|---|---|
| invoice_id, shop_id | |
| variant_id | NULL for custom lines |
| line_no | |
| name, variant_name, hsn_code, unit_code | snapshots |
| qty, unit_price, price_includes_tax | |
| gross, line_discount, invoice_discount_share | |
| taxable, tax_rate, cess_rate | |
| cgst, sgst, igst, cess, line_total | |
| cost_price | snapshot for margin |
| returned_qty | |

**payments** (money in or out; one table for all methods)
| column | notes |
|---|---|
| shop_id | |
| direction | `in, out` |
| method | `cash, upi, card, bank, cheque, store_credit, other` |
| amount | > 0 |
| reference | UPI txn id / card last4 / cheque no |
| party_type, party_id | `customer, supplier, labourer, lender` |
| applies_to_type, applies_to_id | `invoice, purchase, credit_note, borrowing, labour_payment, expense` |
| status | `confirmed, pending_approval, rejected` |
| received_by, approved_by, approved_at | |
| receipt_no | from `doc_series('receipt')` for standalone due collections |
| occurred_at | |
| idempotency_key, deleted_at | |

At checkout the invoice creates `payments` rows for each non-zero method. The due is whatever remains unpaid. Settling dues later adds more `payments` rows against the invoice. A salesperson's collection is `pending_approval` (PlantBill's settlement flow, generalized).

**credit_notes** + **credit_note_lines**: same shape as invoices/lines, plus `original_invoice_id`, `reason ('return','discount','correction')`, `refund_method`, `restock bool`.

**held_bills**: `shop_id, created_by, label, payload jsonb (cart), created_at, expires_at (+7 days)`. Server-side so a bill parked on one device can be resumed on another. Android also keeps a local copy for when it is offline.

**doc_series**: `shop_id, doc_type, prefix, fy, next_seq` (`06-gst.md` §6).

**gst_filed_periods**: `shop_id, period ('2026-10'), return_type ('GSTR1','GSTR3B','CMP08'), marked_by, marked_at`. Unique `(shop_id, period, return_type)`. Once GSTR-1 for a month is marked filed, invoices in that month can't be edited or cancelled. Corrections go through credit/debit notes.

**approval_requests**: `shop_id, kind ('discount','return','collection','cash_close'), ref_id, payload jsonb, requested_by, status, decided_by, decided_at, note`.

## 6. Money out & cash

**expense_categories**: `shop_id, name, is_system`. Seeded: Rent, Electricity, Salaries, Transport, Repairs, Packaging, Marketing, Misc.

**expenses**: `shop_id, category_id, category_name (snapshot), amount, method, paid_from ('cash','bank'), note, occurred_on date, gst_amount NULL, supplier_id NULL, attachment_path NULL, created_by, deleted_at`.

**labourers**, **labour_attendance**, **labour_payments**: ported from PlantBill. Gender gains `other`. Payments use the `payments` table for the cash/UPI split. The wage engine is unchanged (`services/labour.py`).

**borrowings**: `shop_id, lender_name, lender_phone, principal, received_method, interest_note, borrowed_on, status ('open','closed'), deleted_at`. Repayments go to `payments` (direction `out`, `applies_to_type='borrowing'`).

**cash_registers**: `shop_id, name ('Main counter')`. v1 has one register per shop, but the table is there.

**day_closes**: `shop_id, register_id, business_date, opening_cash, expected_cash, counted_cash, difference, notes, closed_by, confirmed_by, status`. Unique `(shop_id, register_id, business_date)`. **Expected cash** = opening + cash in − cash out for that date. The next day's opening defaults to the last counted cash.

## 7. Finance, goals, AI

**goals**
| column | notes |
|---|---|
| shop_id | NULL = all shops of the owner (owner-level goal; RLS via `owner_id`) |
| owner_id | |
| metric | `sales, gross_profit, net_profit, invoices_count, avg_bill_value, new_customers, collections` |
| period | `month, quarter, year, custom` |
| starts_on, ends_on | |
| target | NUMERIC |
| staff_user_id | NULL, or a salesperson target |
| created_by | |

**daily_snapshots** (written by the `finance.daily_close` job): `shop_id, date, sales_gross, sales_net, tax_total, cogs, gross_profit, expenses, labour, net_profit, cash_in, cash_out, closing_cash, invoices_count, customers_count, new_customers, stock_value`. Dashboards and the AI read these for fast ranges and recompute only "today" live.

**ai_conversations** 🔒: `shop_id NULL (owner multi-shop), user_id, title, created_at`.
**ai_messages** 🔒: `conversation_id, role ('user','assistant','tool'), content, tool_name, tool_args jsonb, tokens_in, tokens_out, model, created_at`.
**snap_scans**: `shop_id, user_id, identified_name, matched_variant_id NULL, language, succeeded, tokens, created_at`. Written in its own committed step so failed scans are counted (fixes PlantBill bug 13).
**ai_usage**: `shop_id, month, requests, tokens_in, tokens_out, cost_estimate`. Quota checks read this table.

## 8. Platform & ops

| Table | Columns / purpose |
|---|---|
| **gst_rates** | `06-gst.md` §3 |
| **gst_states** | `06-gst.md` §10 |
| **audit_log** | `03-roles-permissions.md` §4; no FK |
| **jobs** | `02-architecture.md` §5 |
| **scheduled_tasks** | `name, cron, last_run_at, next_run_at, enabled` |
| **notifications** | `title, body, action_url, target ('all','shops','user')` |
| **notification_targets** | |
| **notification_reads** | |
| **crash_reports** | ported from PlantBill, plus `platform` |
| **devices** | `user_id, platform, push_token, app_version, last_seen_at`; registered in v1, push sending later |
| **feature_flags** | `key, enabled, shop_ids uuid[]` |
| **platform_ledger_entries** | PlantBill admin ledger, soft delete |
| **whatsapp_messages** | `shop_id, invoice_id, to_phone, template, status, wa_message_id, error, attempts, sent_at, delivered_at, read_at` |

## 9. Key constraints & indexes (non-exhaustive)

- `CHECK (grand_total = taxable_total + cgst_total + sgst_total + igst_total + cess_total + round_off)` on invoices, credit notes and purchases.
- `CHECK (qty > 0)` on lines. `CHECK (amount > 0)` on payments.
- `UNIQUE (shop_id, doc_type, fy, number)` on invoices.
- `UNIQUE (shop_id, idempotency_key)` on invoices, purchases, payments and credit notes.
- `UNIQUE (shop_id, barcode) WHERE barcode IS NOT NULL`; `UNIQUE (shop_id, sku)`.
- Partial index `invoices (shop_id, issued_at) WHERE status='issued'`.
- Trigram index on `products.name` and `customers.name` for fast search (`pg_trgm`).

## 10. Entity relationships (summary)

```
shops ─┬─ shop_tax_profiles (1:1)        users ──< auth_sessions
       ├─ subscriptions (1:1) ──< subscription_payments
       ├─< shop_owners >── users(owner)
       ├─< users (manager/salesperson)
       ├─< categories ──< products ──< product_variants ──< stock_movements
       ├─< suppliers ──< purchases ──< purchase_lines
       ├─< customers ──< invoices ──< invoice_lines
       │                     ├──< payments
       │                     └──< credit_notes ──< credit_note_lines
       ├─< expenses, labourers, borrowings, day_closes, held_bills
       ├─< goals, daily_snapshots
       └─< ai_conversations ──< ai_messages
```

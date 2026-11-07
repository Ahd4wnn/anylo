# 01 · PlantBill study

PlantBill (`Ahd4wnn/plantbilling`, private) is Anylo's predecessor: a billing SaaS for plant nurseries. We studied all four codebases in depth on 2026-11-08. This doc records what exists, what we port, what we fix, and what we drop.

## 1. What PlantBill is

| Layer | Stack | State |
|---|---|---|
| Backend | FastAPI 0.115, SQLAlchemy 2.0, Alembic (~45 migrations), Postgres 16, python-jose, passlib/bcrypt, openpyxl, reportlab, httpx | Solid; RLS-based multi-tenancy |
| Web | React 18, Vite 5, TS, Tailwind 3, Zustand, axios, motion, lucide, vite-plugin-pwa | Mobile-first, decent but inconsistent visuals, English only |
| Android | Kotlin 2.1, Compose M3, Hilt, Retrofit/OkHttp, kotlinx.serialization, DataStore, CameraX, ZXing, ACRA; minSdk 24, target 36 | Most mature client; 5 languages; raster thermal printing |
| iOS | SwiftUI, iOS 17, Observation, URLSession, Keychain | Early port, well behind Android |
| Deploy | Single VPS, systemd, nginx, Let's Encrypt, `git pull` deploys, no CI | Works; no staging |

### Roles
- **admin:** the platform (Dofida).
- **ops:** admin without customer PII.
- **owner:** multi-shop and read-mostly, through the `shop_owners` many-to-many table.
- **manager:** runs one shop, but **cannot bill**.
- **salesperson:** bills.

### Features
- **Billing:** editable line prices, flat or % discount, Cash/UPI/Split/Due, idempotent checkout, per-shop bill numbers, UPI QR, voice search, plant-photo identification (OpenAI), quick add.
- **Receipts:** Bluetooth/Serial/USB thermal printing, WhatsApp Cloud API PDF invoices, public receipt link.
- **Dues:** collected by salespeople, then approved by the manager.
- **Back office:** expenses with categories, labour (attendance, wages, advances), borrowings, running cash in hand.
- **Reports:** daily, weekly and monthly reports with a 10-sheet XLSX export.
- **Accounts:** 30-day trial for self-signup shops (enforced as HTTP 402 on writes after expiry), onboarding wizard and tour.
- **Admin tools:** platform ledger, notifications, crash reports.

### What is missing
- **No GST at all:** zero hits for gst/tax/hsn/gstin in the backend.
- No inventory, SKU, barcode or units (quantity is an integer).
- No suppliers or purchases.
- No real subscription billing.
- No held bills on web.
- The web barcode scanner is a simulation.
- No i18n on web.
- No financial statements beyond sales minus expenses.

## 2. Port into Anylo (proven, keep the design)

### Backend
| Item | PlantBill source | Notes |
|---|---|---|
| Two-role Postgres RLS: owner role runs migrations, app role is `NOBYPASSRLS`; `set_config(..., true)` transaction-local GUCs; `NULLIF(current_setting(...),'')::uuid`; owner branch through a join table; self-row branch on users | `app/database.py`, `alembic/versions/0001_*`, `e5f6a7b8c9d0_*`, `f6a7b8c9d0e1_*` | Rename roles to `anylo_owner` / `anylo_app` |
| RLS policy shape test + live checker | `tests/test_rls_policy_shape.py`, `scripts/rls_check.py` | Run for every new table |
| Money: `NUMERIC(12,2)`, `q2()` HALF_UP, `MoneyIn` / `MoneyOut` 2-dp strings | `app/schemas/money.py` | Unchanged |
| Idempotent checkout with savepoint + replay on `IntegrityError` | `routers/bills.py` | Move into `services/billing.py` |
| Atomic gapless numbering `UPDATE … SET next_seq = next_seq + 1 RETURNING` | `routers/bills.py` | Becomes per-series, per-financial-year (`06-gst.md`) |
| Denormalized line snapshots (name, price, category) | `models/bill.py` | Add HSN, tax rate, tax amounts |
| FK-less audit log that outlives deleted rows | `models/bill_audit.py`, `services/audit.py` | Generalize to all money entities |
| Settlement approval (one pending per bill, unique partial index) | `routers/settlements.py` | Keep |
| Labour wage engine (pure, tested) | `services/labour_wages.py` | Keep with its tests |
| Styled XLSX builder | `services/report_xlsx.py` | Extend with GST and finance sheets |
| WhatsApp eligibility / phone / template helpers | `services/whatsapp/{eligibility,phone,templates}.py` | Keep |
| Media path guard | `app/media.py` | Add magic-byte checks |
| Crash ingest, notifications, ledger soft-delete | various | Keep |

### Web
- `lib/money.ts` (paise math, `formatINR`)
- `friendlyError()`
- Typed `api/*.ts` modules
- The Zustand cart store pattern
- `lib/escposRaster.ts` together with the Bluetooth/Serial/USB printer store
- Onboarding pattern: wizard, Getting Started checklist, spotlight tour
- Voice fuzzy matcher

### Android
- `domain/Money.kt`, `CartMath` + tests
- `print/` (bitmap receipt → `RasterEscPos`, connect–print–disconnect with a mutex and retries, 58 mm / 80 mm)
- `UpiQrCode` (local ZXing)
- `NetworkMonitor`, `AnrWatchdog`, self-hosted ACRA crash reports
- `TokenStore` (encrypted, multi-account, lazy keystore)
- `UiText`, `LocaleManager` (+ `enableSplit=false`)
- `HeldBillStore`
- `PhoneticMatcher`

### iOS
- `KeychainStore` (off-main-thread)
- `APIError.userMessage`
- The `@Observable` view-model pattern

## 3. Fix (bugs and risks we must not carry over)

| # | Problem in PlantBill | Anylo fix |
|---|---|---|
| 1 | 1-year JWT, no refresh, no revocation; password change does not log out sessions | 15-min access token + rotating refresh token stored hashed; `token_version` on user; see `17-security.md` |
| 2 | No login rate limit | Per-IP + per-account throttling, lockout backoff |
| 3 | WhatsApp webhook unsigned; verify-token logged | Verify `X-Hub-Signature-256`; never log secrets |
| 4 | Salesperson can change shop UPI ID through `PATCH /shop` (fraud) | Shop settings are manager/owner only |
| 5 | DB passwords committed in `scripts/setup_roles.sql` | Script reads passwords from env/prompt |
| 6 | WhatsApp send re-sets `app.user_role='admin'` inside a user request (privilege escalation) | Worker-only privileged session |
| 7 | Background poller runs inside every uvicorn worker, no row locking → duplicate sends | Separate `anylo-worker` systemd unit, jobs table, `FOR UPDATE SKIP LOCKED` |
| 8 | New `customers` row per bill → dues per bill, not per customer | Unique `(shop_id, phone)`; customer ledger |
| 9 | Manager cannot bill | Manager can bill |
| 10 | `GET /products/sample-file` shadowed by `/{product_id}` → 422 | Static routes before parameterized ones; route tests |
| 11 | `POST /bills/summary/report/send-whatsapp` → NameError | Not ported; rebuilt on the job queue |
| 12 | Multiple managers per shop crash admin endpoints (`scalar_one_or_none`) | Model allows N managers everywhere |
| 13 | Failed AI scan row lost (flush then raise → rollback) | Log usage in a separate committed step |
| 14 | Media upload trusts declared content-type | Check magic bytes, re-encode images |
| 15 | Ops role has full admin RLS reach | `support` gets its own RLS role value; PII tables exclude it |
| 16 | Business helpers live in `routers/bills.py` and are imported by six routers | `app/services/*` layer |
| 17 | Hard deletes of expenses / labour / borrowings, no audit | Soft delete + audit for all money rows |
| 18 | Cash in hand re-sums all history each call | Daily closing snapshots (`09-finance-reports-goals.md`) |
| 19 | Web UPI QR rendered by api.qrserver.com (leaks payment data) | Local QR generation |
| 20 | Web receipts strip non-ASCII (₹, Indic names vanish), 80 mm only | Raster receipts like Android; 58/80 mm |
| 21 | `alert()` / `confirm()`, raw Tailwind colors outside tokens, 45 KB `MorePage` | Radix dialogs, token-only colors, sectioned settings |
| 22 | Release AAB/APKs committed (≈300 MB) | `.gitignore`; artifacts go to GitHub Releases / Play Console |
| 23 | Release build silently debug-signs without keystore | Fail the release build if signing config is missing |
| 24 | `usesCleartextTraffic=true` | HTTPS only (debug network-security-config for localhost) |
| 25 | Docs drifted from code (`shop_owner`, "14-day", "no self-signup") | Docs are part of the definition of done |

## 4. Drop

- **Plant-specific copy and branding:** "Nursery" strings and the leaf logo. Plant photo scan is **not** dropped: it becomes the generic **Snap & Find** for any product (§6). The preset plant list becomes the nursery starter catalogue.
- **Dead columns:** `bill_type`, `last_wholesale_price`, `products.is_active` misuse, `whatsapp_last_status`, `chat_id`.
- **Hard-wired payment columns** (`cash_amount` / `upi_amount` / `due_amount`) on every money table: replaced by a `payments` child table with a `method` enum.
- **Forced font scale and density on Android:** respect system accessibility settings and test layouts at 1.3× instead.
- **Light-only theme:** Anylo ships light + dark.

## 5. Lessons

1. The server-authoritative money model plus idempotency keys meant no reported double bills. Keep it.
2. RLS caught real cross-tenant bugs during development. Keep it, and test every policy.
3. Elderly-friendly UX (big targets, plain words) drove adoption. Keep the 48 dp / 56 dp targets, but give power users dense desktop views and keyboard shortcuts.
4. Android outpaced web and iOS because each client was hand-mirrored. Anylo uses OpenAPI as the single contract and keeps a parity checklist (`19-roadmap.md`).
5. Without a real payment flow, trial conversion depended on phone calls. Anylo needs Razorpay from day one.

## 6. Feature parity: every PlantBill feature, PRO MAX

**Rule:** Anylo ships **every** PlantBill feature. Each row must be ✅ on API, web and Android before its milestone closes (tracked in `docs/parity.md`).

| PlantBill feature | Anylo PRO MAX version | Milestone |
|---|---|---|
| Self-signup, 30-day trial, onboarding wizard, Getting Started checklist, spotlight tour | Same, plus business-type presets, a GST step, printer test and staff invites; a tour per role; the checklist stays on Home until done | M1 |
| Roles: admin, ops, owner (multi-shop), manager, salesperson | admin, support, owner, manager, salesperson. **Managers and owners can bill.** Permission matrix + approval PIN | M1 |
| Multi-owner per shop, multi-shop per owner | Same + owner shop switcher everywhere, consolidated reports, owner-level goals | M1 / M6 |
| Android saved-accounts one-tap switch | Same on Android + a web account switcher; device/session list with remote logout | M1 |
| Shop business details, logo, UPI ID | Same + GST tax profile, invoice series/prefixes, receipt footer and language. UPI/GSTIN are owner-only (fraud fix) | M1 |
| Staff management (create, activate, reset password, delete with type-to-confirm) | Same + temporary passwords forced to change, manager PIN, staff performance report | M1 |
| Product catalogue: photo, category, price, CRUD | Variants, SKU, barcode, HSN, GST rate, decimal units, MRP/cost, brand, archive/restore | M2 |
| Bulk upload CSV/XLSX + sample file | Dry-run preview with row errors, then commit; export → edit → import round-trip | M2 |
| Bulk photos via ZIP | Same, matched by SKU or name; auto WebP + thumbnail | M2 |
| Preset plant list at ₹0 | Starter catalogues per business type (nursery keeps the plant list) | M1 |
| Bill: tap to add, editable line price, blank qty until filled | Same + camera and HID scanning, variants, decimal qty, price-to-qty, keyboard shortcuts, three-pane desktop POS | M3 |
| Flat / % discount | Line + invoice discounts with pre-tax allocation; over the limit → approval | M3 |
| Cash / UPI / Split / Due | Cash (change calculator), UPI (local QR with invoice ref), Card, Due (credit limit), any split | M3 |
| UPI QR | Generated locally (no third-party leak), amount + invoice number prefilled | M3 |
| Idempotent checkout, per-shop bill numbers | Same + gapless GST series per FY with prefix; cancel keeps the number | M3 |
| Customer phone lookup, "returning customer" | Deduplicated customers, balance and last visit shown at checkout, B2B GSTIN capture | M3 / M4 |
| Quick Add (filled the catalogue with one-off items) | Custom line, not saved unless "Save as product" is ticked | M3 |
| Voice search (phonetic, Indian English) | Same matcher, generalized; top-3 picker; multilingual recognizer | M3 |
| **Plant camera identification (OpenAI)** | **Snap & Find:** photo of any item → OpenAI vision → matching catalogue products, or create a new one with suggested name, category, HSN and GST rate. Per-shop flag + monthly quota | M3 |
| Barcode scanner (fake on web) | Real: camera (BarcodeDetector/ZXing, ML Kit, VisionKit) + USB/Bluetooth HID scanners + label printing | M2 / M3 |
| Held bills (local only on Android/iOS) | Server-synced held bills across devices + local mirror + "not saved" recovery on network loss | M3 |
| Thermal printing: BT/Serial/USB (web), SPP raster (Android), AirPrint (iOS) | Raster everywhere (₹ + Indic scripts), 58/80 mm, auto-print, copies, logo; BLE on iOS; GST receipt layout | M3 |
| WhatsApp Cloud API PDF invoice: auto-send, template, footer, language, delivery/read status, resend, wa.me fallback | Same, on the job queue (no duplicate sends), with a signed webhook, consent/opt-out, due reminders and an owner weekly digest | M7 |
| Public receipt link | Random-token link (not the UUID), phone masked, PDF download, revocable | M3 |
| Sales history: filters, edited-only, staff filter, pagination | Same + number search, has-due, cancelled, returns; DataTable with export | M3 |
| Bill detail, edit (with audit), delete (manager) | Same-day edit with an item-level diff in the audit log; **cancel instead of delete** (GST-safe); returns via credit notes | M3 / M4 |
| Edit & delete audit log (FK-less) | Audit log for every money and settings entity, visible to owners | M3 |
| Dues list, partial collection, salesperson collection → manager approval | Customer ledger (khata), FIFO collection, receipts, approvals inbox, WhatsApp reminders, ageing report | M4 |
| Expenses with categories, paid from cash/UPI | Same + soft delete/audit, GST on expenses, bill-photo attachment, supplier link | M4 |
| Labour: workers, daily/monthly wages, attendance (P/A/half), advances, due-clear, statements, Aadhaar | Same engine (ported with its tests), masked Aadhaar, gender includes "other", payments in the unified payments table | M4 |
| Borrowings: lender, partial repayment | Same + repayments in the cash flow, interest notes | M4 |
| Cash in hand (running total, editable base) | Day close with counted vs expected cash, differences flagged, day book; the running total is still shown | M4 |
| Daily/weekly/monthly/custom report, staff filter, categories, top 15 products | Full report hub: P&L, cash flow, receivables/payables, product/staff/expense analysis, hour-of-day heatmap | M6 |
| 10-sheet styled XLSX report | 18-sheet business workbook + goal-tracker workbook with charts + GST workbooks | M6 |
| Report via WhatsApp (broken) | Any statement shared as a PDF link on WhatsApp | M6 / M7 |
| Owner dashboard: KPIs, sales by shop, payment mix, top sellers, staff leaderboard | Dashboard with period comparisons, goals, alerts, hour heatmap, consolidated multi-shop view | M6 |
| Charts (bar, donut, ratio, trend) | Recharts / Vico / Swift Charts in the brand palette, with tooltips and axes | M6 |
| Customers list + CSV download | Customer profiles, ledger PDF, tags, B2B details, XLSX export | M4 |
| Admin: platform dashboard, shops table with health dots, create shop, trial extend/end, plant-scan toggle, shop detail drawer | Same + subscriptions/MRR, comped months, feature flags, read-only audited impersonation | M7 |
| Admin: owners, staff directory, cross-shop customer directory + export watermark | Same; customer PII is admin-only (support excluded via RLS) | M7 |
| Admin: broadcast notifications, notification bell, read receipts | Same + device registration (ready for push later) | M7 |
| Admin: crash reports (ACRA) + ANR watchdog | Same for Android + iOS MetricKit + Sentry for API/web | M7 |
| Admin: platform ledger (sales, expenses, dues, trash/restore) | Same + Razorpay income posted automatically | M7 |
| Ops role | `support` role, with PII excluded by RLS | M1 |
| Trial expiry → read-only (402) + "contact us" | Razorpay subscription at ₹599 all-inclusive, grace period, banners, GST invoice for the fee | M7 |
| Languages: en, ml, hi, ta, kn (Android only) | All five on web, Android and iOS, reviewed by native speakers; receipts print in the chosen language | M7 |
| Network monitor, ANR watchdog, crash ingest | Same, with a non-blocking offline banner instead of a blocking dialog | M1 |
| — (new in Anylo) | GST engine, GSTR-1/3B exports, inventory and purchases, suppliers, stocktake, goals, AI manager, dark mode, keyboard-first POS | M3–M7 |

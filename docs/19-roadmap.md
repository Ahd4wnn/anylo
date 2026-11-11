# 19 · Roadmap

Each checkbox is sized to **one focused commit** (sometimes 2–3 when tests are split out). Work goes top to bottom inside a milestone. Web and Android tracks in the same milestone can run in parallel once the API part is merged.

The commit message hint in `code` style is the suggested Conventional Commit scope.

## M0 · Foundations

**Repo & tooling**
- [ ] `chore`: backend skeleton (`pyproject`, ruff, mypy config, `requirements.in` + lock)
- [ ] `chore`: web skeleton (Vite React TS, ESLint, Prettier, Vitest)
- [ ] `chore`: android skeleton (Compose, Hilt, version catalog, flavors, ktlint/detekt)
- [ ] `chore`: `design/tokens.json` + generators for Tailwind / Kotlin / iOS
- [ ] `ci`: backend, web, android and security workflows
- [ ] `chore`: `scripts/sync_fixtures.sh` + `fixtures.yml`

**Backend core**
- [ ] `feat(api)`: config, app factory, health route
- [ ] `feat(api)`: database engines, `rls_session`, `privileged_session`
- [ ] `feat(api)`: `AppError` + error handlers + request-id middleware
- [ ] `feat(db)`: alembic env + RLS policy helper
- [ ] `feat(db)`: extensions, `gst_states`, `gst_rates`, `units` seed
- [ ] `feat(db)`: users, shops, shop_owners, shop_tax_profiles + RLS
- [ ] `test(api)`: RLS policy shape test + `rls_check` script
- [ ] `feat(api)`: money schemas (`q2`, `MoneyIn`, `MoneyOut`, `QtyIn`)
- [ ] `feat(api)`: permissions map + `require_permission` + the route-coverage test

## M1 · Auth, shops, onboarding

**API**
- [ ] `feat(api)`: argon2 password hashing
- [ ] `feat(api)`: access JWT
- [ ] `feat(db)`: auth_sessions + refresh rotation with reuse detection
- [ ] `feat(api)`: signup (shop + owner + trial subscription row)
- [ ] `feat(api)`: login
- [ ] `feat(api)`: refresh
- [ ] `feat(api)`: logout + logout-all
- [ ] `feat(api)`: `/auth/me` with permissions + flags
- [ ] `feat(api)`: password forgot / reset / change
- [ ] `feat(api)`: login throttling
- [ ] `feat(api)`: shop profile GET/PATCH, tax profile PUT with GSTIN validation (+ checksum tests)
- [ ] `feat(api)`: logo upload (safe image pipeline)
- [ ] `feat(api)`: staff CRUD, temporary passwords, approval PIN
- [ ] `feat(api)`: onboarding checklist, business-type presets loader
- [ ] `feat(api)`: owner multi-shop (`X-Shop-Id`, create additional shop)

**Web**
- [ ] `feat(web)`: API client with refresh
- [ ] `feat(web)`: auth store and protected routes
- [ ] `feat(web)`: login, signup, forgot/reset pages
- [ ] `feat(web)`: app shell (sidebar, top bar, shop switcher, bottom nav)
- [ ] `feat(web)`: design-system components batch 1 (button, input, dialog, sheet, toast, card)
- [ ] `feat(web)`: onboarding wizard steps 1–8 (one commit per step)
- [ ] `feat(web)`: settings sections: business, tax, staff

**Android**
- [ ] `feat(android)`: TokenStore, authenticator, NetworkMonitor, ACRA, ANR watchdog
- [ ] `feat(android)`: login and signup
- [ ] `feat(android)`: role shells
- [ ] `feat(android)`: onboarding
- [ ] `feat(android)`: settings: business and staff

## M2 · Catalogue & inventory core

**API**
- [ ] `feat(db)`: categories, products, variants, stock_movements
- [ ] `feat(api)`: categories CRUD
- [ ] `feat(api)`: products CRUD with variants
- [ ] `feat(api)`: archive and restore
- [ ] `feat(api)`: barcode/SKU lookup
- [ ] `feat(api)`: SKU auto-numbering and internal EAN-13 generation
- [ ] `feat(api)`: product photos (WebP + thumbnail)
- [ ] `feat(api)`: import template, dry run, commit
- [ ] `feat(api)`: bulk photos ZIP
- [ ] `feat(api)`: export
- [ ] `feat(api)`: stock adjustments, low stock, valuation
- [ ] `feat(api)`: barcode label PDF

**Web**
- [ ] `feat(web)`: items list (DataTable)
- [ ] `feat(web)`: product form with variant grid
- [ ] `feat(web)`: import wizard
- [ ] `feat(web)`: labels page
- [ ] `feat(web)`: stock page

**Android**
- [ ] `feat(android)`: Room product cache + sync
- [ ] `feat(android)`: items list, form and scan-to-fill barcode

## M3 · GST engine & billing

**GST engine**
- [ ] `feat(api)`: `services/gst`: line calc (exclusive), line calc (inclusive), discount allocation, invoice totals + round-off, amount in words (one commit each, each with tests)
- [ ] `test(api)`: `gst_cases.json` fixtures + Hypothesis properties
- [ ] `feat(db)`: doc_series, invoices, invoice_lines, payments, held_bills, approval_requests, audit_log

**Checkout API**
- [ ] `feat(api)`: `/invoices/preview`
- [ ] `feat(api)`: checkout (idempotent, numbered, stock out, customer upsert, payments)
- [ ] `test(api)`: concurrency numbering + idempotency
- [ ] `feat(api)`: invoices list/detail, edit with diff + audit, cancel
- [ ] `feat(api)`: held bills
- [x] `feat(api)`: manager PIN on the bill (approvals inbox for remote approval moves to M4)
- [ ] `feat(api)`: receipt model endpoint
- [x] `feat(api)`: PDF invoice (A4, reportlab with a bundled Unicode font; WeasyPrint dropped to avoid native deps on the VPS)
- [ ] `feat(api)`: public invoice token + page data

**Web POS**
- [ ] `feat(web)`: `lib/gst.ts` port passing shared fixtures
- [ ] `feat(web)`: POS shell + catalogue + search index
- [ ] `feat(web)`: cart store with IndexedDB persistence
- [ ] `feat(web)`: payment sheet (cash/UPI/card/due/split) + local UPI QR
- [ ] `feat(web)`: checkout + success screen
- [ ] `feat(web)`: HID scanner listener
- [ ] `feat(web)`: camera barcode scanning
- [ ] `feat(web)`: voice search
- [ ] `feat(api)`: Snap & Find (OpenAI vision, matching, quota, snap_scans)
- [ ] `feat(web)`: Snap & Find sheet
- [ ] `feat(android)`: Snap & Find camera flow
- [ ] `feat(web)`: held bills
- [ ] `feat(web)`: keyboard shortcuts + help overlay
- [ ] `feat(web)`: receipt canvas renderer + raster ESC/POS
- [ ] `feat(web)`: printer transports (BLE / Serial / USB) + printer settings
- [ ] `feat(web)`: sales list + invoice detail + public invoice page

**Android POS**
- [ ] `feat(android)`: GstEngine port + fixtures
- [ ] `feat(android)`: POS catalogue + cart
- [ ] `feat(android)`: payment
- [ ] `feat(android)`: checkout + success
- [ ] `feat(android)`: ML Kit scanning
- [ ] `feat(android)`: HID scanner
- [ ] `feat(android)`: voice
- [x] `feat(android)`: held bills (server); cart saved to a file and the idempotency key kept until save, so a dropped connection never loses or doubles a bill. Offline "Save all" queue moves to M4
- [ ] `feat(android)`: receipt renderer update (GST layout)
- [ ] `feat(android)`: Bluetooth SPP + USB printing
- [ ] `feat(android)`: sales list + detail + share PDF

## M4 · Customers, dues, returns, money out, cash

**API**
- [x] `feat(db)`: customers (unique phone) + `customer_balances` view
- [x] `feat(api)`: customers CRUD, lookup, ledger (+ PDF), FIFO collection, reminders
- [x] `feat(api)`: credit notes (partial returns, restock, refund modes, time-limit rule)
- [x] `feat(api)`: expenses + categories (soft delete + audit)
- [x] `feat(api)`: labour (port the wage engine + tests), attendance, payments
- [x] `feat(api)`: borrowings + repayments
- [x] `feat(api)`: cash today, day close, day book

**Web + Android**
- [x] `feat(web)`, `feat(android)`: customers
- [x] `feat(web)`, `feat(android)`: returns
- [x] `feat(web)`, `feat(android)`: expenses
- [x] `feat(web)`, `feat(android)`: labour
- [x] `feat(web)`, `feat(android)`: borrowings
- [x] `feat(web)`, `feat(android)`: cash/day close
- [x] `feat(web)`, `feat(android)`: approvals inbox


Notes (M4 as built):
- Returning customers are found from the **first 5 digits** of their mobile (POS customer field on web and Android), so nobody repeats the full number each visit.
- Store credit can be given on returns; spending it at checkout and customer XLSX/ledger PDF exports move to M6 with the other exports.
- WhatsApp reminders open a prefilled `wa.me` message; sending through the WhatsApp Business API is M7.
- One cash register per shop, so `day_closes` has no register column yet.

## M5 · Purchases, suppliers, stock depth

**API**
- [x] `feat(db)`: suppliers, purchases, purchase_lines
- [x] `feat(api)`: supplier CRUD + ledger
- [x] `feat(api)`: purchase draft/post/cancel with weighted-average cost
- [x] `feat(api)`: supplier payments
- [x] `feat(api)`: stock count (stocktake)
- [x] `feat(api)`: quick restock drafts from low stock

**Web + Android**
- [x] `feat(web)`: purchases with scan-in
- [x] `feat(web)`: suppliers
- [x] `feat(web)`: stock count
- [x] `feat(android)`: purchases
- [x] `feat(android)`: stock count with scan

Notes (M5 as built):
- Purchases are priced with the same GST engine; the place of supply comes from the supplier's state (from their GSTIN). The same supplier bill number can't be entered twice.
- Cost is weighted average. GST is part of the cost only when ITC can't be claimed (the purchase's "I can claim this GST back" switch, always off for composition shops).
- Cancelling a posted purchase takes the stock back out and reverses its payments; the average cost is not rolled back (the next purchase re-averages).
- A stock count freezes the system quantity when it starts and posts (counted − frozen), so sales made during counting still count. Uncounted items are untouched.

## M6 · Finance, reports, goals, GST returns, dashboard

**API**
- [x] `feat(api)`: `services/finance/metrics.py` (one commit per metric family) + golden-month tests
- [x] `feat(db)`: daily_snapshots + `finance.daily_close` job + verifier
- [x] `feat(api)`: dashboard endpoint
- [x] `feat(api)`: P&L, cash flow, receivables/payables ageing, staff, product, expense reports
- [x] `feat(api)`: XLSX builder base (branding, Indian formats, formulas)
- [x] `feat(api)`: business workbook sheets (one commit per 2–3 sheets)
- [x] `feat(api)`: async export job + signed downloads
- [x] `feat(api)`: goals CRUD, progress, notifications, goal-tracker workbook with charts
- [x] `feat(api)`: GSTR-1 sections (b2b, b2cl, b2cs, cdnr/cdnur, hsn, docs, nil): one commit each
- [x] `feat(api)`: GSTR-1 xlsx + json export
- [x] `feat(api)`: GSTR-3B summary
- [x] `feat(api)`: CMP-08 helper
- [x] `feat(api)`: sales/purchase registers

**Clients**
- [x] `feat(web)`: dashboard (tiles, charts, goals, alerts)
- [x] `feat(web)`: reports hub
- [x] `feat(web)`: each report page
- [x] `feat(web)`: GST page
- [x] `feat(web)`: goals
- [x] `feat(web)`: owner overview
- [x] `feat(android)`: dashboard
- [x] `feat(android)`: reports
- [x] `feat(android)`: goals
- [x] `feat(android)`: owner overview

Notes (M6 as built):
- One metrics module (`services/finance/metrics.py`) feeds the dashboard, P&L, goals and Excel. Everything is computed live; `daily_snapshots` waits until a shop's data makes that slow.
- Dashboard: tiles vs the previous equal period, sales trend (every day shown, weekly over 62 days), payment mix, top items by sales and profit, staff, alerts, goals. Not yet: sales-by-hour strip, category share, owner multi-shop view.
- GST: GSTR-1 (B2B, B2CL, B2CS with returns netted, CDNR, CDNUR, HSN B2B/B2C, docs, nil), GSTR-3B from the same data, CMP-08. Excel in the offline-tool layout; portal JSON not yet.
- Business workbook (21 sheets, Anylo colours, banded rows, formula totals, charts, attendance register in green/amber/red). Goal-tracker workbook and large-export jobs not yet.

## M7 · Subscription, AI manager, WhatsApp, admin, launch hardening


**Books & compliance: replace the day-to-day accountant** (from the accountant-tasks research, Nov 2026; confirm rules marked uncertain with a CA)
- [x] `fix(api)`: CMP-08 on taxable turnover only (store each line's GST rate kind even for composition shops so exempt sales drop out)
- [x] `feat(api)`: compliance calendar + filing tracker (GSTR-1/IFF, 3B, CMP-08, GSTR-4/9, advance tax, ITR, licence renewals; filed on + ARN; reminders)
- [ ] `feat(api)`: opening balances at a cut-over date (cash, banks, customers, suppliers, stock, loans, capital)
- [x] `feat(api)`: bank accounts + statement import (CSV/XLS) + auto-match + reconciled flag
- [x] `feat(api)`: owner capital and drawings (drawings are never an expense)
- [x] `feat(api)`: expense GST fields (supplier GSTIN, bill no., ITC eligible) + reverse charge self-invoice + 3B table 3.1(d)
- [ ] `feat(api)`: GSTR-2B import + ITC matching + IMS to-do list (accept / reject / pending)
- [ ] `feat(api)`: generated double-entry ledger (fixed chart of accounts, journals built from existing events) + trial balance
- [x] `feat(api)`: balance sheet + capital account
- [x] `feat(api)`: fixed assets + income-tax WDV depreciation (half rate under 180 days)
- [x] `feat(api)`: loan interest / EMI split (interest to P&L)
- [ ] `feat(api)`: income-tax helper (presumptive s.58 of the Income-tax Act 2025 vs regular profit, cash-receipt % meter for audit limits, advance-tax estimate, ITR-4/ITR-3 figures sheet)
- [ ] `feat(api)`: year-end close + period lock (FY and filed GST months; edits after lock need owner approval and are audited)
- [ ] `feat(api)`: CA role (read-only, multi-shop, every view audited, invited and revoked by the owner) + "close-ready" checklist
- [ ] `feat(api)`: statutory alerts (s.393 / old 194Q TDS applicability, MSME 45-day payments, PF/ESI headcount, composition ₹1.5 Cr and e-invoice ₹5 Cr limits)
- [ ] `feat(api)`: workbook sheets for the CA: Trial Balance, Ledger by account and by party, Balance Sheet, Capital, Bank Reconciliation, ITC Register, GST Reconciliation (books vs 1 vs 3B vs 2B), Reverse Charge, Fixed Assets, Closing Stock, Loans, Payroll, Tax Computation, Filings
- [ ] `feat(api)`: Tally XML voucher export
- [ ] `docs`: switch tax references to the Income-tax Act 2025 numbering (44AD → s.58, 44AA → s.62, 44AB → s.63 / Form 26, 194Q → s.393) and re-check GST rate seeds against the Sept 2025 slabs (5% / 18% / 40%)
- [ ] `feat(web)`, `feat(android)`: screens for the above (bank, capital, assets, filings calendar, CA invite)

Notes (books, first pass):
- Opening balances: books start date + opening cash and bank balances only; customers/suppliers/loans/stock already carry their own opening figures. The rest shows as "opening capital (balancing figure)" on the balance sheet.
- Balance sheet and trial balance come from the same numbers (assets, liabilities, P&L since books start, capital, drawings). Receivables, payables and stock are today's figures, so past dates are approximate. A real double-entry ledger is still open.
- Year lock blocks back-dated expenses, wages, purchases, assets and owner money. Locking filed GST months is still open.
- CA role is read-only and invited by the owner; per-view audit and multi-shop access are still open.
- AI manager and WhatsApp show as "Coming soon" (web settings + sidebar, Android home) until the keys are in.

Left to a CA or a licensed GSP on purpose: tax audit (Form 26), certificates (CMA, net worth), filing by API / e-invoice IRN / e-way bills, TDS and PF/ESI returns, notices and appeals, company/LLP books. Anylo prepares and exports; the CA signs.

**Subscription**
- [ ] `feat(db)`: plans, subscriptions, subscription_payments, razorpay_events
- [ ] `feat(api)`: subscription dependency (402 + allow-list) + tests
- [ ] `feat(api)`: Razorpay client
- [ ] `feat(api)`: checkout
- [ ] `feat(api)`: verify
- [ ] `feat(api)`: webhooks
- [ ] `feat(api)`: sync job
- [ ] `feat(api)`: reconcile job
- [ ] `feat(api)`: cancel/resume
- [ ] `feat(api)`: platform GST invoices for subscriptions
- [ ] `feat(web)`: billing page + Razorpay Checkout + banners
- [ ] `feat(android)`: subscription status + read-only UX

**AI manager**
- [ ] `feat(api)`: OpenAI client
- [ ] `feat(api)`: tool registry
- [ ] `feat(api)`: tools (2–3 per commit)
- [ ] `feat(api)`: SSE endpoint
- [ ] `feat(api)`: quotas
- [ ] `feat(api)`: weekly digest
- [ ] `test(api)`: AI evals
- [ ] `feat(web)`: AI panel + page + chart rendering
- [ ] `feat(android)`: Ask Anylo screen + voice input

**WhatsApp**
- [ ] `feat(api)`: jobs table + worker
- [ ] `feat(api)`: WhatsApp client + signed webhook
- [ ] `feat(api)`: invoice send + status
- [ ] `feat(api)`: due reminders

**Admin**
- [ ] `feat(api)`, `feat(web)`: overview
- [ ] `feat(api)`, `feat(web)`: shops
- [ ] `feat(api)`, `feat(web)`: owners
- [ ] `feat(api)`, `feat(web)`: subscriptions
- [ ] `feat(api)`, `feat(web)`: customers (A)
- [ ] `feat(api)`, `feat(web)`: notifications
- [ ] `feat(api)`, `feat(web)`: crashes
- [ ] `feat(api)`, `feat(web)`: ledger port
- [ ] `feat(api)`, `feat(web)`: GST rates
- [ ] `feat(api)`, `feat(web)`: plans
- [ ] `feat(api)`, `feat(web)`: flags
- [ ] `feat(api)`, `feat(web)`: AI usage
- [ ] `feat(api)`, `feat(web)`: audit
- [ ] `feat(api)`, `feat(web)`: impersonation

**Launch**
- [ ] `feat(web)`: landing page, pricing, privacy, terms
- [ ] `feat(i18n)`: hi, ml, ta, kn for web + Android (one commit per language per platform)
- [ ] `ops`: deploy/rollback scripts
- [ ] `ops`: systemd units
- [ ] `ops`: nginx config
- [ ] `ops`: backups
- [ ] `ops`: monitoring
- [ ] `docs`: runbooks (deploy, restore, incident)
- [ ] `chore`: Play Store listing assets; internal → closed → production track

## M8 · iOS

Follow `15-ios.md` §6. Each step splits into the same feature-sized commits as Android.

## Later (post-launch backlog)

- Offline checkout queue (Android first)
- E-invoicing (IRN)
- E-way bill
- Batch/expiry (pharmacy)
- Serial/IMEI
- Multi-warehouse
- Loyalty
- Push notifications (FCM/APNs)
- Tally export
- Annual plan
- AI write actions
- Supplier-bill OCR
- Payment-gateway UPI confirmation (dynamic QR with webhook)

## Parity checklist

Every user-facing feature row tracks: API ✅ · Web ✅ · Android ✅ · iOS ☐. The table lives in `docs/parity.md`. It is created in M3 and updated in the same PR as each feature.

## Commit volume

Following this list literally gives roughly 350–450 commits through M7 and about 120 more for iOS. Tests, fixes, i18n strings, polish, review feedback and post-launch work take the project naturally toward ~1,000. Every commit must stand on its own: it builds, tests pass, and the change is real.

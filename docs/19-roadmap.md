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
- [ ] `feat(api)`: approvals + manager PIN
- [ ] `feat(api)`: receipt model endpoint
- [ ] `feat(api)`: PDF invoice (WeasyPrint templates A4/A5, Indic fonts)
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
- [ ] `feat(android)`: held bills + "not saved" recovery
- [ ] `feat(android)`: receipt renderer update (GST layout)
- [ ] `feat(android)`: Bluetooth SPP + USB printing
- [ ] `feat(android)`: sales list + detail + share PDF

## M4 · Customers, dues, returns, money out, cash

**API**
- [ ] `feat(db)`: customers (unique phone) + `customer_balances` view
- [ ] `feat(api)`: customers CRUD, lookup, ledger (+ PDF), FIFO collection, reminders
- [ ] `feat(api)`: credit notes (partial returns, restock, refund modes, time-limit rule)
- [ ] `feat(api)`: expenses + categories (soft delete + audit)
- [ ] `feat(api)`: labour (port the wage engine + tests), attendance, payments
- [ ] `feat(api)`: borrowings + repayments
- [ ] `feat(api)`: cash today, day close, day book

**Web + Android**
- [ ] `feat(web)`, `feat(android)`: customers
- [ ] `feat(web)`, `feat(android)`: returns
- [ ] `feat(web)`, `feat(android)`: expenses
- [ ] `feat(web)`, `feat(android)`: labour
- [ ] `feat(web)`, `feat(android)`: borrowings
- [ ] `feat(web)`, `feat(android)`: cash/day close
- [ ] `feat(web)`, `feat(android)`: approvals inbox

## M5 · Purchases, suppliers, stock depth

**API**
- [ ] `feat(db)`: suppliers, purchases, purchase_lines
- [ ] `feat(api)`: supplier CRUD + ledger
- [ ] `feat(api)`: purchase draft/post/cancel with weighted-average cost
- [ ] `feat(api)`: supplier payments
- [ ] `feat(api)`: stock count (stocktake)
- [ ] `feat(api)`: quick restock drafts from low stock

**Web + Android**
- [ ] `feat(web)`: purchases with scan-in
- [ ] `feat(web)`: suppliers
- [ ] `feat(web)`: stock count
- [ ] `feat(android)`: purchases
- [ ] `feat(android)`: stock count with scan

## M6 · Finance, reports, goals, GST returns, dashboard

**API**
- [ ] `feat(api)`: `services/finance/metrics.py` (one commit per metric family) + golden-month tests
- [ ] `feat(db)`: daily_snapshots + `finance.daily_close` job + verifier
- [ ] `feat(api)`: dashboard endpoint
- [ ] `feat(api)`: P&L, cash flow, receivables/payables ageing, staff, product, expense reports
- [ ] `feat(api)`: XLSX builder base (branding, Indian formats, formulas)
- [ ] `feat(api)`: business workbook sheets (one commit per 2–3 sheets)
- [ ] `feat(api)`: async export job + signed downloads
- [ ] `feat(api)`: goals CRUD, progress, notifications, goal-tracker workbook with charts
- [ ] `feat(api)`: GSTR-1 sections (b2b, b2cl, b2cs, cdnr/cdnur, hsn, docs, nil): one commit each
- [ ] `feat(api)`: GSTR-1 xlsx + json export
- [ ] `feat(api)`: GSTR-3B summary
- [ ] `feat(api)`: CMP-08 helper
- [ ] `feat(api)`: sales/purchase registers

**Clients**
- [ ] `feat(web)`: dashboard (tiles, charts, goals, alerts)
- [ ] `feat(web)`: reports hub
- [ ] `feat(web)`: each report page
- [ ] `feat(web)`: GST page
- [ ] `feat(web)`: goals
- [ ] `feat(web)`: owner overview
- [ ] `feat(android)`: dashboard
- [ ] `feat(android)`: reports
- [ ] `feat(android)`: goals
- [ ] `feat(android)`: owner overview

## M7 · Subscription, AI manager, WhatsApp, admin, launch hardening

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

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

- **Plant-specific:** plant photo scan, preset plant list, "Nursery" copy, leaf logo. AI image identification may return later as generic "snap to find product".
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

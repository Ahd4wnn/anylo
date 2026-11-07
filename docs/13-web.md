# 13 · Web app

One React app in `web/`. It serves the marketing landing page, the POS, the shop back office, the owner views and the platform admin. It is installable as a PWA.

## 1. Stack

| Concern | Choice |
|---|---|
| Build | Vite 5, TypeScript strict, React 18 |
| Routing | React Router 6 (data routers, lazy route modules per shell) |
| Server state | TanStack Query v5: cache, retries, focus refetch, optimistic updates for small edits |
| Client state | Zustand: cart, POS UI, printer, session |
| API types | `openapi-typescript` generates `src/api/schema.d.ts` from the backend; a thin `openapi-fetch` client |
| Forms | react-hook-form + zod (schemas mirror the API's validation) |
| UI | Tailwind 3 (tokens from `design/tokens.json`), Radix primitives, `src/ui/*` components, lucide icons |
| Tables | TanStack Table + `@tanstack/react-virtual` |
| Charts | Recharts |
| i18n | react-i18next, JSON namespaces per feature, lazy-loaded languages |
| PWA | vite-plugin-pwa: app shell + fonts cached; API responses are **not** cached; cart in IndexedDB (`idb-keyval`) |
| Barcode | `BarcodeDetector` API, falling back to `@zxing/browser` |
| QR | `qrcode` (local generation) |
| Printing | Ported `escposRaster.ts` + canvas `ReceiptRenderer`; Web Bluetooth / Serial / USB transports |
| Payments | Razorpay Checkout script (`checkout.razorpay.com/v1/checkout.js`), loaded only on the billing page |
| Tests | Vitest + Testing Library; Playwright e2e |
| Lint | ESLint (typescript-eslint, react-hooks, jsx-a11y) + Prettier; a custom rule bans raw colour classes |

## 2. Auth on the web

- The access token is held **in memory** (Zustand, not localStorage).
- The refresh token is an httpOnly, Secure, SameSite=Strict cookie on `/v1/auth`.
- On load, `POST /auth/refresh` restores the session. On a 401, the client refreshes once and retries the request; if that fails, the user goes to login.
- Multi-tab: a `BroadcastChannel('auth')` syncs logout and refresh across tabs.

## 3. Routes

```
/                       Landing (motto, features, pricing, FAQ, CTA "Start free trial")
/pricing  /privacy  /terms  /contact
/login  /signup  /forgot  /reset/:token
/i/:token               Public invoice

/pos                    POS (O M S) — full-screen shell, no sidebar
/pos/held               Held bills
/pos/success/:id

/app                    → /app/home
/app/home               Dashboard (O M) | Salesperson home (today's sales, target, held bills)
/app/sales              Invoices list + filters        /app/sales/:id   invoice detail
/app/returns            Credit notes                   /app/returns/new?invoice=:id
/app/customers          List                           /app/customers/:id  profile + ledger
/app/items              Products                       /app/items/new  /app/items/:id
/app/items/import       Import wizard                  /app/items/labels
/app/stock              Movements, adjustments, counts /app/stock/count/:id
/app/purchases          List  /app/purchases/new  /app/purchases/:id
/app/suppliers          List  /app/suppliers/:id
/app/expenses
/app/staff/labour       Workers, attendance, payments
/app/borrowings
/app/cash               Today, day closes, day book
/app/approvals
/app/reports            Report hub: P&L, cash flow, sales, stock, receivables, payables, staff, products
/app/reports/gst        GSTR-1, GSTR-3B, registers
/app/goals
/app/ai                 AI manager, owner-only (also a slide-over panel in /app for owners)
/app/notifications
/app/settings/{business,tax,invoices,printing,payments,staff,notifications,data}
/app/billing            Subscription (owner)
/app/shops              Owner: shop switcher + overview + create shop
/welcome                Onboarding wizard

/admin                  Overview
/admin/shops  /admin/shops/:id  /admin/owners  /admin/subscriptions
/admin/customers  /admin/notifications  /admin/crashes  /admin/ledger
/admin/gst-rates  /admin/plans  /admin/flags  /admin/ai-usage  /admin/audit
```

`ProtectedRoute` takes the required permission (not just the role) from `/auth/me.permissions`.

## 4. Key screens

**Landing (`/`)**
- Hero: the motto, a one-line value prop and a product screenshot (a real UI capture, not an illustration).
- Features in three columns matching the motto: Bill · Sell · Run.
- Pricing card: "30 days free, then ₹599/shop/month. That's it. GST included.".
- FAQ, then footer.
- Fast: static, < 100 KB JS (lazy-loads nothing from the app).

**Onboarding (`/welcome`)** has these steps:
1. Business type + shop details.
2. GST: scheme, GSTIN with live validation, state. "I'm not registered" is a valid choice.
3. Logo.
4. UPI ID (for the QR).
5. Products: import a file, add a few by hand, or load starter items for the business type.
6. Printer (optional; test print).
7. Invite staff.
8. Done → POS with a spotlight tour.

A "Getting started" checklist card stays on Home until it is complete.

**POS (`/pos`)**: see `07-pos-billing.md`. On desktop it uses three panes and is keyboard-first. The cart and held bills persist across reloads.

**Dashboard (`/app/home`)**: see `09` §2. The range picker is synced to the URL (`?range=this_month`) so views can be shared.

**Invoice detail:**
- receipt preview (canvas), plus actions: Print, PDF, WhatsApp, Copy link, Collect due, Return, Edit, Cancel
- payments timeline
- audit trail

**Reports hub:** cards per report. Each report page has:
- a filter bar (range, staff, category)
- summary tiles, a chart and a table
- buttons for Export XLSX, PDF and WhatsApp

**Settings:** sectioned (`12` §7). Every section saves independently, and unsaved changes show a sticky "Save changes" bar.

## 5. Structure

```
web/src/
  main.tsx  App.tsx  router.tsx
  api/          client.ts (openapi-fetch + auth refresh), schema.d.ts (generated), queries/*.ts (TanStack hooks per domain)
  ui/           design-system components
  features/
    pos/        PosPage, Catalogue, Cart, PaymentSheet, Keypad, HeldBills, Scanner, Voice, store.ts
    sales/ returns/ customers/ items/ stock/ purchases/ suppliers/ expenses/ labour/ borrowings/
    cash/ approvals/ reports/ gst/ goals/ ai/ settings/ billing/ onboarding/ owner/ admin/ landing/
  lib/          money.ts (paise), gst.ts (client preview engine, same fixtures as backend), datetime.ts,
                escposRaster.ts, receiptRenderer.ts, printer/*.ts, phonetic.ts, upi.ts
  i18n/         en/*.json hi/*.json ml/*.json ta/*.json kn/*.json
  styles/       tailwind.css
```

`lib/gst.ts` is a TypeScript port of `services/gst`. It runs against the **same JSON fixture file** (`backend/tests/fixtures/gst_cases.json`, copied by a script), so the preview and the server can't drift.

## 6. Performance budgets

- POS route JS ≤ 250 KB gzip; Landing ≤ 100 KB.
- Adding an item → cart update < 16 ms. A product search over 5,000 items < 30 ms (in-memory index).
- LCP < 2.0 s on a mid-range Android over 4G.
- Lighthouse a11y ≥ 95.

## 7. Environment

`web/.env.example`:
```
VITE_API_BASE_URL=http://localhost:8000/v1
VITE_PUBLIC_WEB_URL=http://localhost:5173
VITE_RAZORPAY_KEY_ID=rzp_test_xxx
```

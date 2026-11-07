# 05 · API

Base URL `https://api.anylo.in/v1`. JSON only, except uploads (multipart) and exports (file streams).
The live contract is FastAPI's `/v1/openapi.json`. This doc is the design-level index; every route below must exist in OpenAPI with the permission listed.

## Conventions

| Topic | Rule |
|---|---|
| Auth | `Authorization: Bearer <access_jwt>` (15 min). Refresh with `POST /auth/refresh`. Web keeps the refresh token in an httpOnly `Secure SameSite=Strict` cookie scoped to `/v1/auth`; mobile keeps it in Keystore/Keychain. |
| Shop context | Shop-scoped users have a fixed shop. Owners send `X-Shop-Id: <uuid>` on shop routes; it is validated against `shop_owners`. |
| Money | Strings with 2 decimals (`"1250.00"`). Quantities are strings with up to 3 decimals. |
| Time | ISO-8601 UTC. Date-only params (`from`, `to`) are interpreted in the shop's timezone. |
| Pagination | `?limit=50&cursor=<opaque>` → `{items, next_cursor}`. |
| Idempotency | `Idempotency-Key` header (uuid) on money-creating POSTs. A repeat returns the original response with `200` + `Idempotent-Replay: true`. |
| Errors | `{"detail": "Plain message for the user", "code": "invoice.price_below_cost", "fields": {...}}`. 401 = re-auth, 402 = subscription read-only, 403 = role, 409 = conflict, 422 = validation. |
| Versioning | Path `/v1`. Breaking changes need `/v2` or additive fields. |

Permission keys refer to `03-roles-permissions.md`. Abbreviations: **O** owner, **M** manager, **S** salesperson, **A** admin, **Su** support.

## auth

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | /auth/signup | public | Shop name, owner name, phone, email, password, business type, state → shop + owner + trial; returns tokens |
| POST | /auth/login | public | Email/phone + password → access + refresh |
| POST | /auth/refresh | refresh token | Rotate refresh token, new access token |
| POST | /auth/logout | any | Revoke current session |
| POST | /auth/logout-all | any | Bump `token_version` |
| GET | /auth/me | any | User, role, shops (for owner), active shop, subscription summary, permissions list, feature flags |
| POST | /auth/password/forgot | public | Email a reset link (always 200) |
| POST | /auth/password/reset | public | Token + new password |
| POST | /auth/password/change | any | Old + new; revokes other sessions |
| PUT | /auth/pin | O M | Set approval PIN |
| GET | /auth/sessions | any | List devices |
| DELETE | /auth/sessions/{id} | any | Revoke a device |

## shop

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | /shop | O M S | Shop profile + settings + tax profile |
| PATCH | /shop | O M | Profile and settings (M cannot change UPI or GSTIN) |
| PUT | /shop/tax-profile | O | GST scheme, GSTIN, legal name, state… (validated) |
| POST / DELETE | /shop/logo | O M | Upload / remove logo |
| GET | /shop/onboarding | O M | Checklist state |
| POST | /shop/onboarding/complete | O M | |
| GET / PATCH | /shop/doc-series | O M | Prefixes per doc type |
| GET | /shop/staff | O M | Staff list |
| POST | /shop/staff | O M | Create user (M: salesperson only) |
| PATCH | /shop/staff/{id} | O M | Name, role, active |
| POST | /shop/staff/{id}/reset-password | O M | Sets a temporary password, shown once, forced change on first login |
| DELETE | /shop/staff/{id} | O M | Deactivate + anonymize after 30 days |
| POST | /shops | O | Owner creates an additional shop (new trial subscription) |
| DELETE | /shop | O | Type-to-confirm, soft delete, 30-day restore |

## catalogue

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | /categories | O M S | |
| POST / PATCH / DELETE | /categories[/{id}] | O M | |
| GET | /units | O M S | |
| GET | /gst-rates | any | Active rates |
| GET | /products | O M S | `q, category_id, barcode, low_stock, include_archived, cursor` |
| GET | /products/lookup | O M S | `?barcode=` or `?sku=` → one variant (scanner path, < 50 ms) |
| GET | /products/{id} | O M S | With variants, stock |
| POST | /products | O M | With variants |
| PATCH | /products/{id} | O M | |
| DELETE | /products/{id} | O M | Archive |
| POST | /products/{id}/restore | O M | |
| POST / DELETE | /products/{id}/photo | O M | |
| GET | /products/import/template | O M | XLSX template (static route declared before `/{id}`) |
| POST | /products/import | O M | CSV/XLSX → preview with row errors (dry run) |
| POST | /products/import/commit | O M | Commit the previewed import |
| POST | /products/photos/zip | O M | Bulk photos matched by SKU or name |
| GET | /products/export | O M | XLSX |
| POST | /products/labels | O M | Barcode label PDF for selected variants (A4 sheets or 50×25 mm roll) |

## inventory

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | /stock/movements | O M | Filter by variant, kind, date |
| POST | /stock/adjustments | O M | Count correction / damage / opening |
| GET | /stock/low | O M S | Below reorder level |
| GET / POST | /stock/counts | O M | List / start a stocktake (optional category) |
| GET | /stock/counts/{id} | O M | Lines with expected vs counted |
| PUT | /stock/counts/{id}/lines | O M | Upsert counted quantities (batch) |
| POST | /stock/counts/{id}/post | O M | Create adjustment movements |
| POST | /stock/counts/{id}/cancel | O M | |
| GET | /stock/valuation | O M | Qty × cost by category |
| GET / POST / PATCH / DELETE | /suppliers[/{id}] | O M | |
| GET | /suppliers/{id}/ledger | O M | |
| GET | /purchases | O M | |
| POST | /purchases | O M | Draft or post; idempotent |
| GET / PATCH | /purchases/{id} | O M | Edit only while draft |
| POST | /purchases/{id}/post | O M | Stock in, cost update |
| POST | /purchases/{id}/cancel | O M | Reverses stock |
| POST | /purchases/{id}/payments | O M | Pay supplier |

## sales

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | /invoices/preview | O M S | Compute totals/taxes for a cart without saving (UI calls it debounced) |
| POST | /invoices | O M S | Checkout. Body: lines[{variant_id or custom{name,hsn,rate,unit}, qty, unit_price, line_discount}], discount, customer (id or new), place_of_supply, payments[{method, amount, reference}], remarks, send_whatsapp. Idempotent. Returns the invoice + `approval_required` when the discount exceeds the limit |
| GET | /invoices | O M S | Filters: from, to, status, customer_id, created_by, has_due, number, q. S sees only own and today's |
| GET | /invoices/{id} | O M S | |
| PATCH | /invoices/{id} | O M | Same-day edit (lines, discount, payments, remarks). Blocked once the period is marked "filed" |
| POST | /invoices/{id}/cancel | O M | Reason required |
| GET | /invoices/{id}/pdf | O M S | A4/A5 tax invoice PDF |
| GET | /invoices/{id}/receipt | O M S | Receipt model for the client raster printer (structured JSON) |
| POST | /invoices/{id}/whatsapp | O M S | Queue send |
| GET | /invoices/{id}/whatsapp | O M S | Delivery status |
| POST | /invoices/{id}/payments | O M S | Collect due (S → pending_approval) |
| GET | /public/invoices/{token} | public | Customer-facing invoice view (phone masked) |
| GET / POST | /held-bills | O M S | |
| GET / DELETE | /held-bills/{id} | O M S | |
| POST | /credit-notes | O M (S → approval) | Return against invoice lines; refund method; restock flag |
| GET | /credit-notes | O M | |
| GET | /credit-notes/{id}[/pdf] | O M | |
| GET | /approvals | O M | Pending requests |
| POST | /approvals/{id}/approve | O M | |
| POST | /approvals/{id}/reject | O M | |
| POST | /approvals/pin | O M | Approve on the same device with a PIN (`{request_id, manager_user_id, pin}`) |

## customers

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | /customers | O M S | `q` (name/phone), has_due |
| GET | /customers/lookup | O M S | `?phone=`: returning-customer hint, balance |
| POST | /customers | O M S | |
| GET | /customers/{id} | O M S | Profile + stats |
| PATCH | /customers/{id} | O M | |
| DELETE | /customers/{id} | O M | |
| GET | /customers/{id}/ledger | O M | Statement; `?format=pdf` |
| POST | /customers/{id}/payments | O M S | Collect against oldest dues first (FIFO allocation), S → approval |
| POST | /customers/{id}/remind | O M | WhatsApp due reminder |
| GET | /customers/export | O M | XLSX |

## money out

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET / POST | /expense-categories | O M S / O M | |
| PATCH / DELETE | /expense-categories/{id} | O M | |
| GET / POST | /expenses | O M S | |
| PATCH / DELETE | /expenses/{id} | O M | Soft delete + audit |
| GET / POST | /labour/workers | O M S / O M | |
| PATCH / DELETE | /labour/workers/{id} | O M | |
| GET / POST | /labour/attendance | O M S | Upsert per worker per day |
| GET / POST | /labour/payments | O M | Wage, advance, due_clear |
| PATCH / DELETE | /labour/payments/{id} | O M | |
| GET | /labour/workers/{id}/statement | O M | |
| GET / POST | /borrowings | O M | |
| POST | /borrowings/{id}/repay | O M | |
| DELETE | /borrowings/{id} | O M | |

## cash

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | /cash/today | O M S | Opening, cash in, cash out, expected |
| GET | /cash/book | O M | Day book for a range |
| POST | /cash/close | O M S | Submit counted cash (S → approval) |
| GET | /cash/closes | O M | History with differences |

## reports & finance (`09-finance-reports-goals.md`)

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | /dashboard | O M | KPIs, trend, mix, top items, goals progress, alerts for a range |
| GET | /reports/sales | O M (S: own) | Summary + by day / category / product / staff / payment method / hour |
| GET | /reports/profit-loss | O M | P&L |
| GET | /reports/cash-flow | O M | |
| GET | /reports/receivables | O M | Ageing 0-30/31-60/61-90/90+ |
| GET | /reports/payables | O M | |
| GET | /reports/stock | O M | Valuation, movement, dead stock |
| GET | /reports/gst/gstr1 | O M | `?period=2026-10` JSON summary |
| GET | /reports/gst/gstr1/export | O M | `?format=xlsx|json` |
| GET | /reports/gst/gstr3b | O M | |
| GET | /reports/gst/registers | O M | Sales/purchase register XLSX |
| GET / POST | /reports/gst/filed-periods | O M | List / mark a period filed (locks edits in that month) |
| DELETE | /reports/gst/filed-periods/{id} | O | Unlock (audited) |
| GET | /reports/export | O M | `?kind=full&from&to`: the multi-sheet business workbook (sync ≤ 5k rows, else 202 + job id) |
| GET | /exports/{job_id} | O M | Status + signed download URL |
| GET / POST | /goals | O M | |
| PATCH / DELETE | /goals/{id} | O M | |
| GET | /goals/progress | O M S | Current progress for active goals (S: own and team) |

## owner (multi-shop)

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | /owner/shops | O | Shops with today's KPIs + subscription status |
| GET | /owner/overview | O | Aggregate KPIs across shops, by-shop table, staff leaderboard, goals |
| GET | /owner/reports/profit-loss | O | Consolidated across shops |

All shop routes are also available to owners with `X-Shop-Id`.

## AI manager (`11-ai-manager.md`)

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | /ai/conversations | O M | |
| POST | /ai/conversations | O M | New conversation |
| GET / DELETE | /ai/conversations/{id} | O M | |
| POST | /ai/conversations/{id}/messages | O M | Send a message; **SSE stream** of tokens + tool-call status |
| GET | /ai/suggestions | O M | Starter questions tailored to the shop |
| GET | /ai/usage | O M | Quota used this month |

## subscription (`10-subscription-razorpay.md`)

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | /billing/subscription | O M | Status, trial days left, next charge |
| POST | /billing/subscription/checkout | O | Create a Razorpay subscription → `{subscription_id, key_id}` for Checkout |
| POST | /billing/subscription/verify | O | Verify the checkout signature (UX fast path; the webhook is the source of truth) |
| POST | /billing/subscription/cancel | O | Cancel at period end |
| GET | /billing/invoices | O | Our GST invoices to the shop (PDF links) |
| POST | /webhooks/razorpay | public, signed | Event intake → `razorpay_events` |

## notifications, misc

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | /notifications | any | Feed + unread count |
| POST | /notifications/{id}/read | any | |
| POST | /notifications/read-all | any | |
| POST | /devices | any | Register FCM/APNs token (push for later; table exists in v1) |
| POST | /crash-reports | public, size-capped | ACRA / iOS |
| GET | /health | public | `{status, db}` |
| GET / POST | /webhooks/whatsapp | public, signed | |

## admin (`/admin/*`, A + Su unless noted)

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | /admin/overview | A Su | Platform KPIs: shops, trials, paying, MRR, churn, activity |
| GET | /admin/shops | A Su | Filters: status, subscription, activity health |
| GET | /admin/shops/{id} | A Su | Detail: usage, subscription, owners, staff counts |
| PATCH | /admin/shops/{id} | A Su | Active, flags |
| POST | /admin/shops | A Su | Create shop + owner (sends invite email) |
| POST | /admin/shops/{id}/extend-trial | A Su | Su ≤ 30 days |
| POST | /admin/shops/{id}/comp | A | Free months |
| POST | /admin/shops/{id}/impersonate | A Su | Read-only token, 30 min, audited |
| DELETE | /admin/shops/{id} | A | |
| GET / POST | /admin/owners | A Su | |
| POST / DELETE | /admin/shops/{id}/owners[/{owner_id}] | A Su | |
| POST | /admin/users/{id}/send-reset | A Su | |
| GET | /admin/customers | A | Directory (PII) |
| GET | /admin/customers/export | A | |
| GET / POST / PATCH | /admin/gst-rates | A | |
| GET / POST / PATCH | /admin/plans | A | |
| GET / PATCH | /admin/feature-flags | A | |
| GET / POST / DELETE | /admin/notifications | A Su | |
| GET | /admin/crash-reports[/{id}] | A Su | |
| * | /admin/ledger/* | A (Su read) | Ported PlantBill platform ledger |
| GET | /admin/subscriptions | A Su | MRR, failed payments, dunning list |
| GET | /admin/ai-usage | A | Cost per shop |
| GET | /admin/audit | A | |

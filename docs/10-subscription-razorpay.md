# 10 · Subscription (Razorpay)

## 1. Offer

| Item | Value |
|---|---|
| Trial | 30 days from shop creation, all features, no card |
| Price | **₹600 / shop / month** + 18% GST = **₹708 charged** (`plans.price` + `plans.gst_rate`; flip to GST-inclusive by changing data, not code) |
| Billing | Razorpay Subscriptions: UPI AutoPay mandate or card (recurring) |
| Multi-shop | Each shop has its own subscription. The owner sees one billing page listing all shops |
| Cancellation | Any time; stays active until the end of the paid period |
| Refunds | None for partial months (stated in Terms) |

> Open decision: confirm whether ₹600 is GST-inclusive. Annual plan (e.g. ₹6,000/yr) is a later add: one new `plans` row.

## 2. Lifecycle

```
             signup
               │
          ┌────▼─────┐  subscribe (mandate set, first charge at trial end)
          │ trialing ├──────────────────────────────┐
          └────┬─────┘                              │
   trial ends, │ no mandate                         │
          ┌────▼─────┐                        ┌─────▼────┐
          │ expired  │◄──grace over──┐        │  active  │◄─── charged ───┐
          └────┬─────┘               │        └─────┬────┘                 │
     pays      │                ┌────┴────┐  charge │ fails                │
     ──────────┘                │  grace  │◄────────┘ (Razorpay retries)  │
                                └────┬────┘──────── payment recovered ────┘
                                     │ owner cancels
                               ┌─────▼─────┐
                               │ cancelled │  (active until period end, then expired)
                               └───────────┘
       comped: admin-granted, behaves like active until comped_until
```

| Status | Can bill / write? | Banner |
|---|---|---|
| trialing | ✅ | "Free trial: N days left · Subscribe" (from day 20: amber) |
| active / comped | ✅ | none |
| past_due → **grace** (7 days, `GRACE_DAYS`) | ✅ | red: "Payment failed. Update payment within N days" |
| expired | ❌ **read-only** (HTTP 402 on writes) | "Subscription ended. Your data is safe. Subscribe to continue billing." |
| cancelled (until period end) | ✅ | "Ends on <date> · Resume" |

**Read-only means:**
- All GET requests work, including exports and GST reports, so owners can always file and leave with their data.
- Writes return `402 {"code":"subscription.read_only"}`.
- Allow-listed writes that keep working:
  - auth
  - `/billing/*`
  - collecting dues (so money can still come in)
  - day close
- Data is retained for at least 12 months after expiry. After that, the owner is emailed 30 days before an archival deletion. Deletion is **manual** and done by an admin; it is never automatic.

## 3. Razorpay integration

**Setup:**
- One Razorpay Plan per `plans` row: period `monthly`, interval 1, amount 70800 paise.
- Its id is stored in `plans.razorpay_plan_id` (and `RAZORPAY_PLAN_ID` for bootstrap).

**Subscribe flow (web only, owner):**
1. The owner clicks **Subscribe** on `/app/billing`.
2. `POST /billing/subscription/checkout` creates a Razorpay Subscription with:
   - `plan_id`
   - `total_count = 120`
   - `customer_notify = 1`
   - `notes = {shop_id}`
   - **`start_at = trial_ends_at`** if still trialing, so the first charge happens when the trial ends. If expired, the charge starts immediately.

   The returned `subscription_id` is stored.
3. The frontend opens **Razorpay Checkout** with `subscription_id` and `key_id`. The customer authorises a UPI AutoPay mandate or card. (For a future `start_at`, Razorpay runs a small authentication transaction.)
4. On the success handler: `POST /billing/subscription/verify` with `razorpay_payment_id`, `razorpay_subscription_id` and `razorpay_signature`. The server checks `HMAC_SHA256(payment_id + "|" + subscription_id, KEY_SECRET)`. This only updates the UI optimistically. **Webhooks are the source of truth.**

**Webhooks** (`POST /webhooks/razorpay`):
- Verify `X-Razorpay-Signature` = HMAC-SHA256 of the **raw body** with `RAZORPAY_WEBHOOK_SECRET`. On mismatch, return 400 and log without the payload.
- Insert into `razorpay_events` with the unique `event_id` (from the `x-razorpay-event-id` header). A duplicate is acknowledged with 200 and skipped.
- Enqueue the `subscription.sync` job, then return 200 immediately.

| Event | Effect |
|---|---|
| `subscription.authenticated` | Mandate ready; stay `trialing` (or `active` if charged) |
| `subscription.activated` | `active`; set the period |
| `subscription.charged` | `active`; extend `current_period_end`; record `subscription_payments`; issue our GST invoice (§4); email the receipt |
| `subscription.pending` | `grace` (set `grace_ends_at` if not set) |
| `subscription.halted` | `grace` → `expired` when the grace period ends (scheduler) |
| `subscription.cancelled` | `cancelled`; expires at the period end |
| `subscription.completed` | `expired` (after 120 charges; create a new subscription) |
| `payment.failed` | Notify the owner (in-app + email) |

**Reconcile:** a nightly job fetches every non-terminal subscription from the Razorpay API and fixes any drift, because webhooks can be lost.

**Cancel:** `POST /billing/subscription/cancel` calls Razorpay cancel with `cancel_at_cycle_end=1`.

**Resume:** create a new subscription with `start_at` = the current period end.

## 4. Our GST invoice to the shop

- Dofida is the supplier (`PLATFORM_GSTIN`, `PLATFORM_STATE_CODE`). The service SAC is `998314` (IT design and development services); the CA should confirm it.
- Intra- or inter-state is decided by the shop's state.
- If the shop has a GSTIN, it is a B2B invoice, which lets the shop claim ITC.
- The invoice is generated with the same GST engine and PDF templates, in the platform series `ANY/25-26/000001`. It is listed under `/billing/invoices`.

## 5. Mobile apps and store policies

- **The Android and iOS apps do not sell subscriptions.**
  - They show the status, the trial days left and the read-only state.
  - Message: "Subscriptions are managed by the shop owner at anylo.in."
  - There is no in-app purchase button or price, and no link that steers to web checkout.

  This keeps the apps outside Google Play Billing and App Store IAP requirements for v1. The pattern is a multi-platform business service where the account is bought elsewhere.
- **Risk:** store policies change. Review Play's India user-choice-billing and Apple guideline 3.1.3 before every store submission. A fallback plan: add Play Billing for Android (Google takes a fee) and keep web pricing unchanged.

## 6. Admin tools

- `/admin/subscriptions` shows:
  - MRR
  - active, trialing and expired counts
  - trial → paid conversion
  - churn
  - failed payments, with a list of shops in grace
- An admin can:
  - extend a trial
  - comp months
  - see Razorpay ids, with a deep link to the Razorpay dashboard
  - re-run a sync
- PlantBill's manual platform ledger stays for offline or cash deals. Razorpay income is auto-posted into it as `platform_ledger_entries`.

## 7. Tests

- Signature verification:
  - a valid fixture
  - a tampered body
  - a wrong secret
- Event idempotency: the same event twice leaves exactly one state change.
- State machine: a table-driven test covering every (status, event) pair → expected status.
- The subscription dependency: each status × each HTTP method → allowed or 402, including the allow-list.
- Reconcile job against a mocked Razorpay client.

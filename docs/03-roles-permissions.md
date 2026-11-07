# 03 · Roles & permissions

## 1. Roles

| Role | Scope | Who | `users.shop_id` |
|---|---|---|---|
| `admin` | Platform | Dofida founders / engineers | NULL |
| `support` | Platform, no customer PII | Dofida support staff (PlantBill's `ops`) | NULL |
| `owner` | 1..N shops via `shop_owners` | Business owner | NULL |
| `manager` | Exactly one shop | Runs the shop day to day | required |
| `salesperson` | Exactly one shop | Counter staff | required |

- A self-signup creates a **shop + owner account**. The owner can also bill at that shop: owners act as manager in any shop they own, after picking it in the shop switcher.
- An owner can create managers and salespeople. A manager can create salespeople.
- Several managers per shop are allowed.
- One email maps to one user. A person who works in two shops needs two logins (v1).

## 2. Permission matrix

Key: ✅ allowed · 👁 read only · ⏳ needs manager approval · — not allowed. "Own" means records the user created.

### Shop operations

| Capability | owner | manager | salesperson | admin | support |
|---|---|---|---|---|---|
| Create invoice (bill) | ✅ | ✅ | ✅ | — | — |
| Hold / resume bill | ✅ | ✅ | ✅ | — | — |
| Give discount above shop limit (`settings.max_discount_pct`) | ✅ | ✅ | ⏳ (manager PIN) | — | — |
| Change line price below cost | ✅ | ✅ | — | — | — |
| View invoices | ✅ | ✅ | own + today | 👁 | 👁 (no customer phone) |
| Edit invoice (same day, before GST filing) | ✅ | ✅ | — | — | — |
| Cancel invoice (keeps number, marks cancelled) | ✅ | ✅ | — | — | — |
| Create return / credit note | ✅ | ✅ | ⏳ | — | — |
| Collect due payment | ✅ | ✅ | ⏳ | — | — |
| Approve pending collections / returns / discounts | ✅ | ✅ | — | — | — |
| Products: view | ✅ | ✅ | ✅ | 👁 | 👁 |
| Products: create / edit / import | ✅ | ✅ | — | — | — |
| Products: delete (archive) | ✅ | ✅ | — | — | — |
| Quick-add custom line (not saved to catalogue) | ✅ | ✅ | ✅ | — | — |
| Stock adjustment | ✅ | ✅ | — | — | — |
| Purchases / suppliers | ✅ | ✅ | — | — | — |
| Customers: view / create | ✅ | ✅ | ✅ | — | — |
| Customers: export | ✅ | ✅ | — | — | — |
| Expenses: create | ✅ | ✅ | ✅ | — | — |
| Expenses: edit / delete | ✅ | ✅ | — | — | — |
| Labour: attendance | ✅ | ✅ | ✅ | — | — |
| Labour: pay / edit workers | ✅ | ✅ | — | — | — |
| Borrowings | ✅ | ✅ | — | — | — |
| Cash in hand: view | ✅ | ✅ | today only | — | — |
| Day close (count cash) | ✅ | ✅ | ✅ (submits; manager confirms) | — | — |
| Reports & financial statements | ✅ | ✅ | own sales today | — | — |
| GST reports (GSTR-1/3B) | ✅ | ✅ | — | — | — |
| Goals: set | ✅ | ✅ | — | — | — |
| Goals: view | ✅ | ✅ | team goal only | — | — |
| AI manager | ✅ | ✅ | — | — | — |
| Shop settings (GSTIN, UPI, invoice series, printer defaults) | ✅ | ✅ (not GSTIN/UPI) | — | 👁 | 👁 |
| Staff: manage salespeople | ✅ | ✅ | — | — | — |
| Staff: manage managers | ✅ | — | — | — | — |
| Subscription: view status | ✅ | ✅ | banner only | ✅ | ✅ |
| Subscription: pay / cancel | ✅ | — | — | — | — |
| Delete shop | ✅ (type-to-confirm, 30-day undo) | — | — | ✅ | — |

### Platform

| Capability | admin | support |
|---|---|---|
| Shops list, health, detail | ✅ | ✅ |
| Create shop / owner, link owners | ✅ | ✅ |
| Reset user password (sends reset link; never shows the password) | ✅ | ✅ |
| Extend trial / comp subscription | ✅ | ✅ (≤ 30 days) |
| Customer directory & export | ✅ | — |
| AI conversations (abuse review) | ✅ | — |
| Broadcast notifications | ✅ | ✅ |
| Crash reports | ✅ | ✅ |
| Platform ledger (our revenue / expenses) | ✅ | 👁 |
| Feature flags, GST rate table, plan prices | ✅ | — |
| Impersonate ("view as shop", read-only, audited) | ✅ | ✅ |

## 3. Enforcement layers

1. **UI:** hide what the role can't do. This is a convenience, never security.
2. **API dependencies:** `require_roles("owner","manager")` and `require_shop_permission("invoice.cancel")`. Permissions are code constants in `app/permissions.py`, mapping permission → set of roles. This matrix is generated into a test that checks every route declares a permission.
3. **RLS:** tenant isolation (`02-architecture.md` §4). PII tables also exclude `support`.
4. **Approvals:** actions marked ⏳ create an `approval_requests` row (`kind`, `payload`, `requested_by`, `status`). The action runs only when a manager or owner approves. Alternatively, a manager can enter their **PIN** on the same device to approve on the spot: `users.pin_hash`, 4–6 digits, rate-limited.

## 4. Audit

Every create/update/delete on these tables writes `audit_log(shop_id, actor_id, actor_email, actor_role, entity, entity_id, action, before jsonb, after jsonb, at)`:
- invoices, payments, returns, expenses, labour payments, borrowings, stock adjustments, settings, staff

`audit_log` has no FK, so audit rows survive deletion of the record. Owners can see the log; managers can see their own shop's log.

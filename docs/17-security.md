# 17 · Security

Anylo holds money records, customer phone numbers and tax data for many businesses. Two bugs hurt most here: **cross-shop data leaks** and **money tampering by staff**. Defend in depth.

## 1. Threat model (top risks)

| # | Threat | Mitigation |
|---|---|---|
| T1 | Shop A reads or writes shop B's data | Postgres RLS on every tenant table (`FORCE`), app role `NOBYPASSRLS`, shop id from the token/`shop_owners` and never from the client body; RLS tests per table; `scripts/rls_check.py` in CI against a live DB |
| T2 | Salesperson fraud: deleting bills, changing UPI ID, big discounts, pocketing cash | No delete (only cancel by O/M, with audit); UPI/GSTIN editable by owner only; discount limit → approval; pending-approval collections; day-close differences flagged; staff performance report shows discounts and cancellations |
| T3 | Account takeover | argon2id; login throttling (5/15 min per account, nginx per-IP); short access tokens; rotating refresh with reuse detection; "log out all devices"; password change revokes sessions; optional email OTP for new device (later) |
| T4 | Stolen phone at the counter | Refresh tokens are revocable per device by the owner; manager PIN for sensitive actions; idle lock option (PIN to resume after N min) |
| T5 | Payment webhook forgery | HMAC verification on Razorpay and WhatsApp webhooks; event-id idempotency; the reconcile job uses the Razorpay API as the source of truth |
| T6 | Prompt injection via product names / notes into the AI | Tool output treated as data in the system prompt; read-only tools; RLS-scoped execution; output never rendered as HTML; eval cases for injection |
| T7 | Malicious uploads | Size limits; magic-byte check; images re-encoded with Pillow (drops metadata/scripts); CSV/XLSX parsed with limits (rows ≤ 20k, no formulas evaluated); ZIP bomb guard (max entries, max uncompressed size) |
| T8 | Public invoice link enumeration | Random 128-bit token, not the UUID; phone masked; regenerate to revoke; rate limited |
| T9 | Secrets leak | `.env` only on the server (0640); never logged; GitHub secret scanning + `gitleaks` in CI; rotate on staff change |
| T10 | Platform staff overreach | `support` role excludes PII via RLS; impersonation is read-only, time-boxed and audited; admin actions are audited |

## 2. Authentication details

- **Passwords:** argon2id (`argon2-cffi`, time_cost=3, memory_cost=64 MB). Minimum 8 characters, checked against a top-10k common list.
- **Access JWT:** HS256, 15 min. Claims: `sub`, `sid` (session), `role`, `shop` (nullable), `ver` (token_version), `exp`, `iat`. The role and shop in the token are hints; `get_actor` re-reads the user each request (cheap PK lookup) and rejects on a mismatch.
- **Refresh:** a 256-bit random value; the DB stores only its SHA-256.
  - Rotated on every use.
  - Reuse of an old token revokes the whole `family_id`.
  - 30-day sliding expiry, 90-day absolute.
- **Password reset:** a single-use token, 30 min, emailed. The response is always identical, to prevent enumeration.
- **Staff passwords set by managers:** temporary and shown once, with a forced change at first login.

## 3. Authorization

- Permission constants are in `app/permissions.py`. Every route declares exactly one permission dependency. A test walks the FastAPI router to ensure none are missing.
- Object-level checks: services verify that referenced ids (variant, customer, invoice) belong to the active shop, even though RLS would also block them. This gives clear 404s instead of FK errors.

## 4. Data protection

- TLS everywhere; HSTS. Mobile apps only allow HTTPS in release builds.
- PII: customer name/phone/GSTIN, staff Aadhaar (optional; stored **masked** except the last 4 digits; the full number is not needed).
- Logs never include tokens, passwords, OTPs, full phone numbers or request bodies of auth/payment routes.
- **DPDP Act 2023 alignment:**
  - privacy notice
  - purpose limitation (billing, legal tax records)
  - customer data export/delete on the shop's request

  Deletion keeps invoices, because tax law requires them for 6+ years from the FY end, but anonymises the customer profile.
- Backups are encrypted (`16` §7).

## 5. Application security checklist (per PR)

- [ ] New tenant table has RLS + test
- [ ] New route has a permission dependency
- [ ] Money changes are idempotent and audited
- [ ] No raw SQL string building (SQLAlchemy params only)
- [ ] User-supplied files go through `media.save_image()` / `imports.parse_sheet()`
- [ ] No secrets or PII in logs
- [ ] Error messages don't leak internals

## 6. Dependency and CI security

- `pip-audit`, `npm audit --omit=dev`, Gradle dependency check, Dependabot weekly.
- `gitleaks` on every push.
- CodeQL for Python/TS/Kotlin on PRs.
- Pin versions: `requirements.lock` (pip-tools), `package-lock.json`, Gradle catalog.

## 7. Incident basics

- Contact: security@anylo.in. Response target is 24 h.
- Runbook `docs/runbooks/incident.md` (to be written in M7):
  - revoke all sessions (bump all `token_version`)
  - rotate secrets
  - notify affected shops within 72 h when personal data is involved

# 18 · Testing

Money, tax and tenancy bugs are the expensive ones, so tests concentrate there.

## 1. Pyramid per layer

| Layer | Tool | What | Gate |
|---|---|---|---|
| Backend unit | pytest | GST engine, money, stock costing, wage engine, metrics functions, permissions map, Razorpay state machine, GSTIN checksum, amount-in-words | every push |
| Backend integration | pytest + real Postgres 16 (CI service, created per run; no Docker locally: tests use a `anylo_test` DB) | Routers end-to-end through FastAPI `TestClient`, RLS isolation, idempotency, numbering under concurrency, exports open in openpyxl | every push |
| Contract | `openapi.snapshot.json` diff + client DTO tests | API changes are intentional; Android/iOS/web decode every example | every push |
| Web unit | Vitest | `lib/money`, `lib/gst` (shared fixtures), cart store, receipt renderer, phonetic matcher, hooks | every push |
| Web e2e | Playwright (against staging-like local stack) | Signup → onboarding → product → bill (cash, split, due) → print preview → return → GSTR-1 export; subscription checkout in Razorpay test mode | PR to main |
| Android unit | JUnit5 + Turbine | Money, GstEngine (shared fixtures), ViewModels, token refresh, raster | every push |
| Android UI | Compose tests + MockWebServer, Robolectric | POS flow, receipt snapshots | PR to main |
| iOS | Swift Testing + snapshot | Same as Android once M8 starts | PR touching ios/ |
| AI evals | pytest + real OpenAI (nightly, budget-capped) | `11-ai-manager.md` §8 | nightly / prompt changes |

## 2. Shared fixtures (one truth for all platforms)

- `backend/tests/fixtures/gst_cases.json`: every example from `06-gst.md` §9, plus generated edge cases. Each case has inputs (lines, discount, scheme, states, round-off) and exact expected outputs.
- A script `scripts/sync_fixtures.sh` copies the file to:
  - `web/src/lib/__fixtures__/`
  - `android/app/src/test/resources/`
  - `ios/Packages/AnyloCore/Tests/Fixtures/`

  CI fails if any copy differs.
- `backend/tests/fixtures/shop_month.sql`: the golden month for finance and report assertions (`09` §6).

## 3. Must-have backend tests (definition of done for their milestone)

- **RLS:**
  - For each tenant table, a user of shop A gets 0 rows from shop B on select, and an error on insert/update with B's id.
  - Owners see only linked shops. Support can't read PII tables.
- **Idempotency:**
  - The same `Idempotency-Key` twice returns one invoice and one stock movement set.
  - Concurrent identical requests (threads) still produce exactly one invoice.
- **Numbering:**
  - 50 concurrent checkouts → numbers 1..50, no gaps, no duplicates.
  - The FY rollover on 1 April starts at 1.
- **GST:** all fixtures, plus property tests (Hypothesis):
  - Σ line totals = grand total − round-off
  - CGST = SGST per line
  - inclusive line total == net
  - |round-off| ≤ 0.50
- **Stock:** sale/return/cancel/edit sequences keep `stock_qty` == Σ movements. Weighted average matches a hand computation.
- **Subscription:** state machine table; 402 matrix; webhook signature and idempotency.
- **Permissions:** every route has a permission; a parametrized test hits each route with each role and expects allow/deny per `03` matrix.
- **Reports:** golden month numbers; Σ invariants across groupings; XLSX files open and the formulas compute.
- **Security:** upload magic-byte rejection; ZIP bomb guard; public invoice token can't be guessed from the id; login throttling.

## 4. Test data

- `app.scripts.seed_demo` creates a demo owner with two shops (regular GST in Kerala, composition in Karnataka), 300 products with variants, 90 days of invoices, returns, purchases, expenses, labour and goals. It is used for local dev, e2e, screenshots and AI evals.
- A factory module (`tests/factories.py`) builds valid objects quickly.

## 5. CI (GitHub Actions)

```
.github/workflows/
  backend.yml   ruff, mypy (services/ strict), pytest (+ postgres service), pip-audit, openapi snapshot diff
  web.yml       eslint, tsc, vitest, build, size-limit, playwright (on PR to main)
  android.yml   ktlint, detekt, unit tests, assembleDevDebug; on tag: bundleProdRelease + upload
  ios.yml       (M8) build + test on macos runner
  security.yml  gitleaks, CodeQL
  fixtures.yml  shared fixture copies identical
  ai-evals.yml  nightly
  deploy.yml    staging on main, production on v* tag (`16` §6)
```

Branch protection on `main`: all required checks green, linear history.

## 6. Manual QA before each release

- Print on two real printers: a 58 mm Bluetooth SPP printer and an 80 mm USB printer. Check all five scripts and the ₹ sign.
- Scan EAN-13, UPC-A and Code128 barcodes with the camera and with a HID scanner.
- A Hindi and a Malayalam UI pass on a small phone (360 dp) at 1.3× font scale.
- Dark mode pass.
- Razorpay test: subscribe, renew (test clock), fail, recover, cancel.
- A CA reviews a sample GSTR-1 export each release that touches tax code.

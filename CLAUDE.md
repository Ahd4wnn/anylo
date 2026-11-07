# Anylo — contributor & agent guide

> Bill anything. Sell anything. Run everything.

Read `docs/` before building a feature; the spec there is the source of truth. If code and docs disagree, fix one of them in the same change.

## Repo

```
backend/   FastAPI app (app/), Alembic migrations, worker, tests
web/       React + Vite + TS
android/   Kotlin + Compose
ios/       SwiftUI (later)
docs/      spec (00–19)
```

## Non-negotiable rules

### Money
- Money is `NUMERIC(12,2)` in Postgres, `Decimal` in Python, a 2-decimal **string** on the wire (`"1234.50"`).
- Round with `q2()` (ROUND_HALF_UP) only at defined points (line tax, line total, invoice round-off). See `docs/06-gst.md`.
- Web does arithmetic in integer paise (`lib/money.ts`); Android uses `Money` (BigDecimal value class); iOS uses `Decimal`. Never `float`/`Double` for money.
- **The server is authoritative.** Clients compute totals only for display; the API recomputes everything.
- Quantities are `NUMERIC(12,3)` (decimal units like 1.250 kg).

### Tenancy & security
- Every tenant table has `shop_id` and Postgres RLS (`ENABLE` + `FORCE`). The app connects as `anylo_app` (NOBYPASSRLS). Never bypass RLS in request handlers.
- `privileged_session()` is only for: login, signup, public receipt, webhooks, worker. Each use needs a one-line comment saying why.
- Role checks happen in FastAPI dependencies (`require_*`) **and** RLS. Never trust a role or shop id sent by the client.
- Secrets live in `.env` on the server only. Never commit `.env`, keystores, real passwords, or build artifacts (`.apk`, `.aab`).

### Time
- Store `timestamptz` in UTC. A shop's business day uses `shops.timezone` (default `Asia/Kolkata`). Financial year = 1 April – 31 March.

### API
- FastAPI's OpenAPI schema is the contract for web, Android and iOS. Change the schema → update clients in the same milestone.
- Writes that create money records (bills, payments, returns, purchases) take an `idempotency_key`.
- Errors: `{"detail": "<plain-language message>", "code": "<machine_code>"}`.

## Code style
- Python: ruff + ruff format, type hints, SQLAlchemy 2.0 style. Business logic in `app/services/`, not routers.
- TS: strict mode, ESLint + Prettier, no `any`. Colors only via design tokens (`docs/12-design-system.md`).
- Kotlin: ktlint, MVVM (`Screen` + `ViewModel` + `StateFlow<UiState>`), strings in resources.
- Comments explain *why*, not *what*.

## Tests
- Every money, tax, stock or permission rule gets a unit test. GST worked examples in `docs/06-gst.md` are test fixtures.
- New tenant tables get an RLS test (`tests/test_rls_*.py`).
- `pytest`, `npm test`, `./gradlew test` must pass before merging.

## Git
- Conventional Commits: `feat(api): …`, `fix(web): …`, `docs: …`, `test(api): …`, `chore: …`, `refactor(android): …`.
- **One logical change per commit.** Small commits are good; empty or padding commits are not.
- **No AI attribution**: no `Co-Authored-By` AI lines, no "Generated with …" footers in commits or PRs.
- Branch per milestone task when working in parallel; `main` must always build.

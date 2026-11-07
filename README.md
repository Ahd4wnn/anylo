# Anylo

> **Bill anything. Sell anything. Run everything.**

GST-ready billing, inventory and business intelligence for Indian retail shops.

Anylo is a point-of-sale and back-office platform for any retail shop: kirana, boutique, electronics, hardware, nursery, stationery and more. It covers fast counter billing, GST tax invoices, stock, staff, expenses, financial statements, goals, and an AI manager that answers questions about your own shop.

It is the successor to PlantBill (a nursery-only billing app) and rebuilds it for every kind of retail shop.

| Surface | Stack |
|---|---|
| Web app (POS + back office) | React 18, Vite, TypeScript, Tailwind, Radix, TanStack Query |
| API | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 (row-level security) |
| Android | Kotlin, Jetpack Compose, Hilt, Retrofit |
| iOS | Swift, SwiftUI (planned) |

**Pricing:** 30-day free trial, then **₹599 per shop per month, all-inclusive** (GST included, nothing more). Owners pay on the web via Razorpay.

## Repository layout

```
backend/   FastAPI service + background worker
web/       React web app (PWA)
android/   Kotlin Android app
ios/       SwiftUI iOS app (planned)
docs/      Product and engineering specification — start here
```

## Documentation

Read in order:

| # | Doc | What it covers |
|---|---|---|
| 00 | [Vision](docs/00-vision.md) | Product, users, scope, non-goals |
| 01 | [PlantBill study](docs/01-plantbill-study.md) | What we learned from the predecessor; port / fix / drop |
| 02 | [Architecture](docs/02-architecture.md) | System design, modules, request lifecycle |
| 03 | [Roles & permissions](docs/03-roles-permissions.md) | Every role and the permission matrix |
| 04 | [Data model](docs/04-data-model.md) | Every table, column and constraint |
| 05 | [API](docs/05-api.md) | Every endpoint |
| 06 | [GST](docs/06-gst.md) | Tax engine, invoices, returns, worked examples |
| 07 | [POS & billing](docs/07-pos-billing.md) | Checkout, payments, dues, returns, printing |
| 08 | [Inventory](docs/08-inventory.md) | Products, variants, stock, purchases, suppliers |
| 09 | [Finance, reports & goals](docs/09-finance-reports-goals.md) | P&L, cash flow, Excel exports, targets, dashboard |
| 10 | [Subscription](docs/10-subscription-razorpay.md) | Trial, Razorpay, enforcement |
| 11 | [AI manager](docs/11-ai-manager.md) | OpenAI tool-calling assistant |
| 12 | [Design system](docs/12-design-system.md) | Brand, tokens, components |
| 13 | [Web app](docs/13-web.md) | Routes, screens, state |
| 14 | [Android app](docs/14-android.md) | Architecture, screens, printing |
| 15 | [iOS app](docs/15-ios.md) | Architecture and build plan |
| 16 | [Deployment](docs/16-deployment-vps.md) | VPS, systemd, nginx (no Docker) |
| 17 | [Security](docs/17-security.md) | Auth, RLS, secrets, threat model |
| 18 | [Testing](docs/18-testing.md) | Strategy per layer, CI |
| 19 | [Roadmap](docs/19-roadmap.md) | Milestones and task checklists |

Contributor and agent rules live in [CLAUDE.md](CLAUDE.md).

## Quick start (development)

Prerequisites: Python 3.12, Node 20+, PostgreSQL 16, JDK 17 + Android Studio (for Android).

```bash
# API
cd backend
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                            # fill in values
alembic upgrade head
uvicorn app.main:app --reload

# Web
cd web
npm ci
cp .env.example .env.local
npm run dev
```

Full setup is in each folder's README and in [docs/16-deployment-vps.md](docs/16-deployment-vps.md).

## License

Proprietary. © Dofida Private Limited. All rights reserved.

# 00 · Vision

> **Bill anything. Sell anything. Run everything.**

## The problem

Small and mid-size Indian retailers run on paper bill books, WhatsApp, a calculator, and a notebook of dues. The software they can buy is either:
- **too simple**: billing only, no GST, no stock, no idea whether the shop made money; or
- **too heavy**: accounting software built for accountants, not for a counter with a queue.

PlantBill, our first product, proved shop owners will adopt a phone-first billing app when it is fast and simple. But it only fits nurseries, has no GST, and cannot tell an owner how the business is really doing.

## What Anylo is

A **counter-speed POS** plus a **back office** plus a **business brain**, for any retail shop:

1. **Bill anything:** fast billing by tap, search, voice or barcode. GST tax invoices (or bills of supply) are correct by construction. Cash, UPI, card, credit (due) and split payments. Thermal receipt, A4 PDF and WhatsApp.
2. **Sell anything:** any product type: pieces, kg, litres, metres; variants (size and colour); MRP and cost price; stock that updates itself; purchases from suppliers.
3. **Run everything:**
   - Money: expenses, staff and labour, borrowings, cash in hand.
   - Financial statements: P&L, cash flow, day book, receivables.
   - Goals with progress, a dashboard, and GSTR-ready exports.
   - An **AI manager** you can ask "How did we do this week vs last week?" or "Which items should I reorder?"

## Who uses it

| Persona | Device | Cares about |
|---|---|---|
| **Owner** (1–N shops) | Phone, laptop | Is the business growing? Who owes me? Profit, goals, staff honesty |
| **Manager** (runs one shop) | Laptop/tablet at counter, phone | Fast billing, stock, staff, daily close |
| **Salesperson** | Phone or counter PC | Make the bill fast, print it, collect payment |
| **Anylo admin / support** (us) | Laptop | Onboard shops, subscriptions, health, support |

Owners may be non-technical and older. The UI uses plain language, big touch targets and regional languages, and every dangerous action asks for confirmation.

## Pricing

- **30-day free trial**, no card needed. All features unlocked.
- Then **₹599 per shop per month, all-inclusive**: GST is included and there are no hidden charges. It auto-renews through Razorpay (UPI AutoPay or card), and **owners pay on the web**.
- If payment lapses: a grace period, then **read-only**. Data is never deleted for non-payment; owners can always see and export their records.

## Platforms

| Platform | v1 | Notes |
|---|---|---|
| Web (desktop POS + mobile PWA) | ✅ | Primary back office; subscription purchase happens here |
| Android | ✅ | Primary counter device for most shops; Bluetooth thermal printing |
| iOS | Later | Specified in `15-ios.md`; built after Android parity |

## Scope for v1

In:
- Retail billing, GST, inventory and purchases.
- Customers with khata (dues).
- Expenses, labour, borrowings, cash in hand.
- Financial statements, goals, dashboard, Excel exports, GSTR-1/3B summaries.
- Subscription, AI manager.
- English, Hindi, Malayalam, Tamil, Kannada.

Out (later):
- E-invoicing (IRN) and e-way bills.
- Restaurant/KOT features.
- Multi-warehouse transfers.
- Loyalty points.
- Full double-entry accounting.
- Offline-first sync (v1 has held bills and a resilient cart, not offline checkout).
- Marketplace integrations.

## Success measures

- A trained salesperson completes a 3-item cash bill in **under 10 seconds**.
- Every invoice passes the GST checks in `06-gst.md` (validated by tests and a CA review).
- Trial → paid conversion ≥ 30%; monthly churn < 4%.
- Owner opens the dashboard or AI manager at least 3× per week.

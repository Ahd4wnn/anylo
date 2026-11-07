# 09 · Finance, reports & goals

"Run everything": an owner should know, at any moment, **what came in, what went out, what is owed, and whether the shop is on track.**

Anylo is **not** full double-entry accounting in v1. It produces management statements from operational data, and gives a CA clean registers and GST exports.

## 1. Definitions (single source of truth: `services/finance/metrics.py`)

| Metric | Formula (for a date range, shop timezone, status = issued) |
|---|---|
| Gross sales | Σ invoice `grand_total` |
| Returns | Σ credit note `grand_total` |
| Net sales | Gross sales − returns |
| Output tax | Σ (cgst + sgst + igst + cess) on invoices − the same on credit notes |
| Net revenue (ex-tax) | Σ taxable on invoices − Σ taxable on credit notes (+ round-off) |
| COGS | Σ (line qty × line `cost_price`) − the same on restocked returns |
| Gross profit | Net revenue − COGS |
| Gross margin % | Gross profit / net revenue |
| Operating expenses | Σ expenses (ex-GST if the GST is claimable) + labour wages paid/accrued (setting: cash basis by default) |
| Net profit | Gross profit − operating expenses |
| Collections | Σ payments in (confirmed) |
| Receivables | Σ customer balances > 0 |
| Payables | Σ supplier balances > 0 |
| Cash in hand | Last confirmed day-close counted cash + today's cash in − today's cash out |
| Avg bill value | Net sales / invoice count |
| Footfall proxy | Invoice count; unique customers with a phone |

All reports, the dashboard, Excel exports and the AI manager call these same functions. **There is no second implementation.** This avoids PlantBill-style drift between the web and Android numbers.

## 2. Dashboard (`GET /dashboard`)

Range picker: Today · Yesterday · This week · This month · Last month · This FY · Custom. Every KPI is compared with the previous equal period (▲/▼ %).

**Tiles:**
- Net sales
- Gross profit (with margin %)
- Net profit
- Invoices count
- Avg bill value
- Collections
- Receivables
- Cash in hand
- Stock value

**Charts:**
- Sales and profit trend: daily bars plus a line; weekly bars when the range is over 62 days.
- Payment mix: cash / UPI / card / due, as a donut.
- Sales by hour of day, as a heat strip (staffing insight).
- Top 10 products by revenue and by profit.
- Category share.
- Staff leaderboard: sales, bills and avg bill.

**Goal panel:** active goals as progress bars, each showing:
- current vs target
- % elapsed vs % achieved
- required daily run-rate to hit the target
- status chip: *On track / Behind / Achieved*

**Alerts:**
- low stock
- negative stock
- large cash-close differences
- overdue receivables (> 30 days)
- subscription status
- pending approvals

**Owner multi-shop view:** consolidated tiles plus a per-shop comparison table (sortable), and a "best and worst shop this week" callout.

**Performance:** past days come from `daily_snapshots`; today is computed live. Dashboard p95 < 400 ms.

## 3. Financial statements

| Statement | Content |
|---|---|
| **Profit & Loss** | Net revenue → COGS → Gross profit → expenses by category → labour → Net profit. Columns: selected period, previous period, change %. Monthly columns for a FY view |
| **Cash flow (simple, direct)** | Opening cash + bank. Inflows: cash sales, UPI/card sales, collections, borrowings received. Outflows: supplier payments, expenses, wages, loan repayments, refunds. Closing. Split by cash vs bank/UPI |
| **Day book** | Every money event of a date in time order, with a running cash balance |
| **Receivables ageing** | Per customer: 0–30, 31–60, 61–90, 90+ days. Total. Last payment date. "Send reminder" action |
| **Payables ageing** | Per supplier, same buckets |
| **Expense analysis** | By category and month, % of revenue, top increases |
| **Staff performance** | Per user: invoices, net sales, avg bill, discounts given, returns, cancellations, cash-close differences |
| **Product performance** | Qty, revenue, profit, margin, stock left, days of cover |
| **GST** | GSTR-1, GSTR-3B, registers (`06-gst.md` §13) |

Every statement can be exported as XLSX, viewed as PDF (print layout), and shared on WhatsApp (as a PDF link).

## 4. Excel workbooks

Built with openpyxl, extending PlantBill's `report_xlsx.py` style with Anylo branding:
- brand header row with shop name, GSTIN, period and generated time
- frozen header rows, auto-filter, column widths
- Indian number format `#,##,##0.00`
- totals rows using real formulas, so accountants can audit
- a print layout that fits the page width

**"Business workbook"** (`/reports/export?kind=full`) has these sheets:

1. **Summary**: KPIs + goal status
2. **P&L**: monthly columns
3. **Cash Flow**
4. **Sales Register**: one row per invoice with all tax columns
5. **Sales Lines**: one row per line, with HSN, rate, taxes, cost and margin
6. **Returns**: credit notes
7. **Payments**: all money in and out, by method
8. **Customers**: balance, purchases, last visit
9. **Receivables Ageing**
10. **Products**: stock, value, margin, sales qty
11. **Stock Movements**
12. **Purchases** (register) + **Suppliers**
13. **Expenses**
14. **Labour** (payments + attendance register pivot; ported)
15. **Staff**
16. **Day Closes**
17. **Goals**: target, actual, % and status per goal, with a progress data bar (conditional formatting)
18. **Audit Log**

**"Goal tracker" workbook** (`/reports/export?kind=goals`):
- one sheet per active goal with a daily cumulative actual vs linear target line chart (an openpyxl `LineChart`)
- a run-rate table
- a forecast: the linear projection of the current pace

Large exports (> 5,000 rows in total) run as a job (`export.report_xlsx`). The user gets a notification with a signed download link valid for 24 h.

## 5. Goals

- **Created by O/M.** Fields:
  - metric (`sales`, `gross_profit`, `net_profit`, `invoices_count`, `avg_bill_value`, `new_customers`, `collections`)
  - period (month / quarter / year / custom)
  - target
  - optional staff member
  - optional shop (owner goals can span all shops)
- **Templates:** "Grow sales 10% over last month" pre-fills the target from history.
- **Progress:** `actual` uses the §1 functions for the elapsed part of the period. Each goal also reports:
  - `expected_by_now = target × elapsed_days / total_days`
  - `run_rate_needed = (target − actual) / remaining_days`
  - `projection = actual / elapsed_days × total_days`
- **Status:**
  - **Achieved:** actual ≥ target.
  - **On track:** projection ≥ target.
  - **At risk:** projection ≥ 90% of target.
  - **Behind:** otherwise.
- **Notifications:**
  - when 50% / 100% of the target is reached
  - a weekly digest on Monday morning (goal status + AI summary, see `11-ai-manager.md`)
- **Salespeople** see their own target and the shop's team target on the POS home ("₹12,400 to go today").

## 6. Accuracy and testing

- Golden-data tests: `tests/fixtures/shop_month.sql` holds a seeded month with known invoices, returns, purchases and expenses. Expected P&L, cash flow, GSTR-1 and dashboard numbers are asserted exactly.
- A property test: Σ by-day = Σ by-category = Σ by-staff = total, for random ranges.
- `daily_snapshots` are re-verified against live computation by a nightly job; a mismatch raises an alert.

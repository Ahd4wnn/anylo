"""Excel workbooks for owners and accountants (docs/09-finance-reports-goals.md §4).

ponytail: built synchronously in the request; move to the export job (spec: > 5,000 rows) when a shop gets that big.
"""

import io
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy.orm import Session

from app.database import Actor
from app.services.finance import gst_returns, reports
from app.services.finance.metrics import balances, bounds
from app.services.sales import _q, shop_ctx

# Anylo "Mist" palette (design/tokens.json), so the workbook looks like the app.
PRIMARY, PRIMARY_DARK, TINT, SOFT = "4A5AE0", "3D4CCB", "F4F6FD", "E3E7FC"
GREEN, GREEN_SOFT, AMBER, AMBER_SOFT, RED, RED_SOFT, GREY = (
    "2F8466",
    "DDF1E7",
    "9A6B12",
    "FBEFD3",
    "C0444A",
    "FBE3E3",
    "8A8FA3",
)
INR = "#,##,##0.00;[Red]-#,##,##0.00"
WHITE = Font(bold=True, color="FFFFFF")
LINE = Side(style="thin", color="DDE1EE")
TAB = {
    "summary": PRIMARY,
    "sales": GREEN,
    "money": AMBER,
    "buy": "6E7FF3",
    "people": "B07AE0",
    "gst": RED,
    "stock": "3FA7B5",
}


TAB_OF = {
    "Summary": "summary",
    "P&L": "summary",
    "Goals": "summary",
    "Audit Log": "summary",
    "Daily Sales": "sales",
    "Sales Register": "sales",
    "Sales Lines": "sales",
    "Returns": "sales",
    "Cash Flow": "money",
    "Payments": "money",
    "Expenses": "money",
    "Day Closes": "money",
    "Customers": "people",
    "Receivables Ageing": "people",
    "Staff": "people",
    "Labour Payments": "people",
    "Attendance": "people",
    "Products": "stock",
    "Stock Movements": "stock",
    "Purchases": "buy",
    "Suppliers": "buy",
}


def fill(hex_: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_)


# Column kinds: "m" money (Indian format, summed), "q" quantity, "d" date, "t" text.
Cols = list[tuple[str, str]]
# Optional per-cell colour: (column name, value) -> (background, text colour) or None.
Paint = Callable[[str, Any], tuple[str, str] | None]


def _sheet(
    wb: Workbook,
    title: str,
    brand: list[str],
    cols: Cols,
    rows: list[list[Any]],
    totals: bool = True,
    paint: Paint | None = None,
) -> Worksheet:
    ws = wb.create_sheet(title[:31])
    ws.sheet_properties.tabColor = TAB[TAB_OF.get(title, "gst")]
    paint = paint or _status
    width = max(len(cols), 4)
    for i, line in enumerate(brand, start=1):
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=width)
        cell = ws.cell(i, 1, line)
        if i == 1:
            cell.font, cell.fill = Font(bold=True, size=14, color="FFFFFF"), fill(PRIMARY)
            ws.row_dimensions[1].height = 26
        else:
            cell.font, cell.fill = Font(size=10, color="5A6075", italic=i > 2), fill(TINT)
        cell.alignment = Alignment(vertical="center", indent=1)
    top = len(brand) + 2
    ws.row_dimensions[top].height = 30
    for c, (name, kind) in enumerate(cols, start=1):
        cell = ws.cell(top, c, name)
        cell.font, cell.fill, cell.border = WHITE, fill(PRIMARY_DARK), Border(bottom=LINE)
        cell.alignment = Alignment(
            wrap_text=True, vertical="center", horizontal="right" if kind in "mq" else "left"
        )
    for r, row in enumerate(rows, start=top + 1):
        band = fill(TINT) if (r - top) % 2 == 0 else None
        for c, v in enumerate(row, start=1):
            if isinstance(v, datetime):
                v = v.replace(tzinfo=None)
            cell = ws.cell(r, c, float(v) if isinstance(v, Decimal) else v)
            name, kind = cols[c - 1]
            cell.number_format = (
                INR
                if kind == "m"
                else "0.###"
                if kind == "q"
                else "dd-mm-yyyy"
                if kind == "d"
                else "General"
            )
            cell.border = Border(bottom=LINE)
            tone = paint(name, v)
            if tone:
                cell.fill, cell.font = fill(tone[0]), Font(bold=True, color=tone[1])
            elif band:
                cell.fill = band
    last = top + len(rows)
    if totals and rows:  # real formulas, so an accountant can audit the sums
        ws.cell(last + 1, 1, "Total")
        for c, (_, kind) in enumerate(cols, start=1):
            cell = ws.cell(last + 1, c)
            cell.font, cell.fill, cell.border = (
                Font(bold=True),
                fill(SOFT),
                Border(top=Side(style="double", color=PRIMARY)),
            )
            if kind == "m" and c > 1:
                col = get_column_letter(c)
                cell.value, cell.number_format = f"=SUM({col}{top + 1}:{col}{last})", INR
    ws.freeze_panes = ws.cell(top + 1, 2 if len(cols) > 6 else 1)
    if rows:
        ws.auto_filter.ref = f"A{top}:{get_column_letter(len(cols))}{last}"
    for c, (name, kind) in enumerate(cols, start=1):
        ws.column_dimensions[get_column_letter(c)].width = (
            max(12, min(40, len(name) + 4)) if kind != "t" else 26
        )
    ws.page_setup.orientation = "landscape" if len(cols) > 7 else "portrait"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{top}:{top}"
    return ws


def _brand(ctx: Any, title: str, period: str) -> list[str]:
    return [
        f"{ctx.name} · {title}",
        f"GSTIN {ctx.gstin or 'not registered'} · {period} · generated {datetime.now(ctx.tz):%d %b %Y %H:%M} by Anylo",
    ]


def _status(name: str, v: Any) -> tuple[str, str] | None:
    """Shared colours for status-like cells across sheets."""
    if name in ("Status",) and isinstance(v, str):
        return {
            "cancelled": (RED_SOFT, RED),
            "draft": (AMBER_SOFT, AMBER),
            "pending": (AMBER_SOFT, AMBER),
            "rejected": (RED_SOFT, RED),
            "achieved": (GREEN_SOFT, GREEN),
            "on track": (GREEN_SOFT, GREEN),
            "at risk": (AMBER_SOFT, AMBER),
            "behind": (RED_SOFT, RED),
            "missed": (RED_SOFT, RED),
        }.get(v)
    if (
        name in ("Due", "Over 90", "Difference", "You owe", "Balance")
        and isinstance(v, Decimal)
        and v != 0
    ):
        return (AMBER_SOFT, AMBER) if v > 0 and name != "Difference" else (RED_SOFT, RED)
    if name in ("Margin", "Margin %") and isinstance(v, Decimal) and v < 0:
        return (RED_SOFT, RED)
    return None


def _rows(db: Session, sql: str, **p: Any) -> list[list[Any]]:
    return [list(r) for r in _q(db, sql, **p)]


def business(db: Session, actor: Actor, start: date, end: date) -> bytes:
    ctx = shop_ctx(db, actor)
    a, b = bounds(ctx, start, end)
    period = f"{start:%d %b %Y} to {end:%d %b %Y}"
    p = {"s": ctx.id, "a": a, "b": b, "d1": start, "d2": end, "tz": str(ctx.tz)}
    wb = Workbook()
    wb.remove(wb.active)
    brand = lambda t: _brand(ctx, t, period)  # noqa: E731

    pl = reports.pnl(db, actor, start, end)
    t = pl["total"]
    lines = [
        ("Gross sales", "gross_sales"),
        ("Returns", "returns"),
        ("Net sales", "net_sales"),
        ("GST collected", "output_tax"),
        ("Net revenue (without GST)", "net_revenue"),
        ("Cost of goods sold", "cogs"),
        ("Gross profit", "gross_profit"),
        ("Expenses", "expenses"),
        ("Wages", "labour"),
        ("Net profit", "net_profit"),
        ("Collections", "collections"),
    ]
    bal = balances(db, ctx)
    summary = _sheet(
        wb,
        "Summary",
        brand("Summary"),
        [("Figure", "t"), ("Amount", "m")],
        [[label, t[k]] for label, k in lines]
        + [
            ["Gross margin %", t["gross_margin_pct"]],
            ["Bills", t["invoices_count"]],
            ["Average bill", t["avg_bill_value"]],
            ["New customers", t["new_customers"]],
            ["Customers owe you (today)", bal["receivables"]],
            ["You owe suppliers (today)", bal["payables"]],
            ["Stock value at cost (today)", bal["stock_value"]],
        ],
        totals=False,
        paint=lambda name, v: None,
    )
    for r in range(5, 5 + len(lines) + 7):  # highlight the lines owners look at first
        label = summary.cell(r, 1).value
        if label in ("Net sales", "Gross profit", "Net profit"):
            good = (summary.cell(r, 2).value or 0) >= 0
            for c in (1, 2):
                summary.cell(r, c).font = Font(bold=True, size=12, color=GREEN if good else RED)
                summary.cell(r, c).fill = fill(GREEN_SOFT if good else RED_SOFT)
    summary.column_dimensions["A"].width, summary.column_dimensions["B"].width = 34, 18
    plws = _sheet(
        wb,
        "P&L",
        brand("Profit & loss"),
        [("Line", "t")] + [(f"{m['from']:%b %Y}", "m") for m in pl["months"]] + [("Total", "m")],
        [[label] + [m[k] for m in pl["months"]] + [t[k]] for label, k in lines],
        totals=False,
    )
    for r in range(5, 5 + len(lines)):
        if plws.cell(r, 1).value in ("Net sales", "Gross profit", "Net profit"):
            for c in range(1, len(pl["months"]) + 3):
                plws.cell(r, c).font = Font(bold=True)
    months = len(pl["months"])
    chart = BarChart()
    chart.title, chart.y_axis.title, chart.height, chart.width = (
        "Sales and profit by month",
        "₹",
        8,
        16,
    )
    for label in ("Net sales", "Gross profit", "Net profit"):
        row = 5 + [x for x, _ in lines].index(label)
        chart.add_data(
            Reference(plws, min_col=1, max_col=1 + months, min_row=row, max_row=row),
            from_rows=True,
            titles_from_data=True,
        )
    chart.set_categories(Reference(plws, min_col=2, max_col=1 + months, min_row=4, max_row=4))
    for series, colour in zip(chart.series, (PRIMARY, GREEN, AMBER), strict=True):
        series.graphicalProperties.solidFill = colour
    summary.add_chart(chart, "D4")

    trend = reports.dashboard(db, actor, start, end)["trend"]
    daily = _sheet(
        wb,
        "Daily Sales",
        brand("Sales by day" if (end - start).days <= 62 else "Sales by week"),
        [("Day", "d"), ("Net sales", "m"), ("Gross profit", "m")],
        [[x["date"], x["sales"], x["profit"]] for x in trend],
    )
    if trend:
        line = LineChart()
        line.title, line.height, line.width = "Daily sales", 8, 18
        line.add_data(
            Reference(daily, min_col=2, max_col=3, min_row=4, max_row=4 + len(trend)),
            titles_from_data=True,
        )
        line.set_categories(Reference(daily, min_col=1, min_row=5, max_row=4 + len(trend)))
        for series, colour in zip(line.series, (PRIMARY, GREEN), strict=True):
            series.graphicalProperties.line.solidFill = colour
            series.graphicalProperties.line.width = 22000
        daily.add_chart(line, "E4")
    cf = reports.cash_flow(db, actor, start, end)
    _sheet(
        wb,
        "Cash Flow",
        brand("Cash flow"),
        [("Line", "t"), ("In / out", "t"), ("Cash", "m"), ("Bank / UPI / card", "m")],
        [["Opening cash", "", cf["opening_cash"], None]]
        + [
            [
                x["label"],
                x["direction"],
                x["cash"] if x["direction"] == "in" else -x["cash"],
                x["bank"] if x["direction"] == "in" else -x["bank"],
            ]
            for x in cf["lines"]
        ]
        + [["Closing cash", "", cf["closing_cash"], None]],
        totals=False,
    )
    _sheet(
        wb,
        "Sales Register",
        brand("Sales register"),
        [
            ("Bill no.", "t"),
            ("Date", "d"),
            ("Customer", "t"),
            ("GSTIN", "t"),
            ("Place of supply", "t"),
            ("Taxable", "m"),
            ("CGST", "m"),
            ("SGST", "m"),
            ("IGST", "m"),
            ("Cess", "m"),
            ("Round off", "m"),
            ("Total", "m"),
            ("Paid", "m"),
            ("Due", "m"),
            ("Status", "t"),
            ("Billed by", "t"),
        ],
        _rows(
            db,
            "SELECT number, (issued_at AT TIME ZONE :tz)::date, coalesce(buyer_name, buyer_phone), buyer_gstin, place_of_supply,"
            " taxable_total, cgst_total, sgst_total, igst_total, cess_total, round_off, CASE WHEN status = 'issued' THEN grand_total ELSE 0 END,"
            " paid_total, due_total, status, created_by_name FROM invoices WHERE shop_id = :s AND issued_at >= :a AND issued_at < :b ORDER BY issued_at",
            **p,
        ),
    )
    _sheet(
        wb,
        "Sales Lines",
        brand("Sales lines"),
        [
            ("Bill no.", "t"),
            ("Date", "d"),
            ("Item", "t"),
            ("HSN", "t"),
            ("Qty", "q"),
            ("Unit", "t"),
            ("Rate", "m"),
            ("Taxable", "m"),
            ("GST %", "q"),
            ("Tax", "m"),
            ("Total", "m"),
            ("Cost", "m"),
            ("Margin", "m"),
        ],
        _rows(
            db,
            "SELECT i.number, (i.issued_at AT TIME ZONE :tz)::date, l.name, l.hsn_code, l.qty, l.unit_code, l.unit_price, l.taxable,"
            " l.tax_rate, l.cgst + l.sgst + l.igst + l.cess, l.line_total, round(l.qty * l.cost_price, 2), round(l.taxable - l.qty * l.cost_price, 2)"
            " FROM invoice_lines l JOIN invoices i ON i.id = l.invoice_id WHERE i.shop_id = :s AND i.status = 'issued'"
            " AND i.issued_at >= :a AND i.issued_at < :b ORDER BY i.issued_at, l.line_no",
            **p,
        ),
    )
    _sheet(
        wb,
        "Returns",
        brand("Returns (credit notes)"),
        [
            ("Note no.", "t"),
            ("Date", "d"),
            ("Against bill", "t"),
            ("Taxable", "m"),
            ("Tax", "m"),
            ("Total", "m"),
            ("Refund", "t"),
            ("Refunded", "m"),
        ],
        _rows(
            db,
            "SELECT n.number, (n.issued_at AT TIME ZONE :tz)::date, i.number, n.taxable_total, n.cgst_total + n.sgst_total + n.igst_total + n.cess_total,"
            " n.grand_total, n.refund_method, n.refunded FROM credit_notes n LEFT JOIN invoices i ON i.id = n.original_invoice_id"
            " WHERE n.shop_id = :s AND n.issued_at >= :a AND n.issued_at < :b ORDER BY n.issued_at",
            **p,
        ),
    )
    _sheet(
        wb,
        "Payments",
        brand("Payments in and out"),
        [
            ("Date", "d"),
            ("In / out", "t"),
            ("Method", "t"),
            ("For", "t"),
            ("Receipt", "t"),
            ("Reference", "t"),
            ("Amount", "m"),
        ],
        _rows(
            db,
            "SELECT (occurred_at AT TIME ZONE :tz)::date, direction, method, coalesce(applies_to_type, party_type), receipt_no, reference,"
            " CASE WHEN direction = 'in' THEN amount ELSE -amount END FROM payments WHERE shop_id = :s AND status = 'confirmed'"
            " AND occurred_at >= :a AND occurred_at < :b ORDER BY occurred_at",
            **p,
        ),
    )
    _sheet(
        wb,
        "Customers",
        brand("Customers"),
        [
            ("Name", "t"),
            ("Mobile", "t"),
            ("GSTIN", "t"),
            ("Balance", "m"),
            ("Bills", "q"),
            ("Bought", "m"),
            ("Last visit", "d"),
        ],
        _rows(
            db,
            "SELECT c.name, c.phone, c.gstin, b.balance, (SELECT count(*) FROM invoices i WHERE i.customer_id = c.id AND i.status = 'issued'),"
            " (SELECT coalesce(sum(grand_total), 0) FROM invoices i WHERE i.customer_id = c.id AND i.status = 'issued'),"
            " (SELECT (max(issued_at) AT TIME ZONE :tz)::date FROM invoices i WHERE i.customer_id = c.id)"
            " FROM customers c JOIN customer_balances b ON b.customer_id = c.id WHERE c.shop_id = :s AND c.deleted_at IS NULL ORDER BY b.balance DESC",
            **p,
        ),
    )
    ar = reports.receivables(db, actor)
    _sheet(
        wb,
        "Receivables Ageing",
        brand("Who owes you"),
        [
            ("Customer", "t"),
            ("Mobile", "t"),
            ("0-30 days", "m"),
            ("31-60", "m"),
            ("61-90", "m"),
            ("Over 90", "m"),
            ("Total", "m"),
        ],
        [
            [r["name"], r["phone"], r["0_30"], r["31_60"], r["61_90"], r["over_90"], r["balance"]]
            for r in ar["items"]
        ],
    )
    _sheet(
        wb,
        "Products",
        brand("Products"),
        [
            ("Item", "t"),
            ("Variant", "t"),
            ("SKU", "t"),
            ("Stock", "q"),
            ("Cost", "m"),
            ("Price", "m"),
            ("Stock value", "m"),
            ("Margin %", "q"),
            ("Sold qty", "q"),
        ],
        _rows(
            db,
            "SELECT p.name, v.name, v.sku, v.stock_qty, v.cost_price, v.sale_price, round(greatest(v.stock_qty, 0) * v.cost_price, 2),"
            " CASE WHEN v.sale_price > 0 THEN round((v.sale_price - v.cost_price) * 100 / v.sale_price, 1) END,"
            " (SELECT coalesce(sum(l.qty), 0) FROM invoice_lines l JOIN invoices i ON i.id = l.invoice_id WHERE l.variant_id = v.id"
            "   AND i.status = 'issued' AND i.issued_at >= :a AND i.issued_at < :b)"
            " FROM product_variants v JOIN products p ON p.id = v.product_id WHERE v.shop_id = :s AND p.deleted_at IS NULL ORDER BY p.name, v.name",
            **p,
        ),
    )
    _sheet(
        wb,
        "Purchases",
        brand("Purchase register"),
        [
            ("Supplier", "t"),
            ("GSTIN", "t"),
            ("Their bill", "t"),
            ("Bill date", "d"),
            ("Taxable", "m"),
            ("CGST", "m"),
            ("SGST", "m"),
            ("IGST", "m"),
            ("Cess", "m"),
            ("Total", "m"),
            ("ITC", "t"),
            ("Status", "t"),
        ],
        _rows(
            db,
            "SELECT s.name, s.gstin, p.supplier_invoice_no, p.supplier_invoice_date, p.taxable_total, p.cgst_total, p.sgst_total, p.igst_total,"
            " p.cess_total, p.grand_total, CASE WHEN p.itc_eligible THEN 'Yes' ELSE 'No' END, p.status FROM purchases p JOIN suppliers s ON s.id = p.supplier_id"
            " WHERE p.shop_id = :s AND p.created_at >= :a AND p.created_at < :b ORDER BY p.created_at",
            **p,
        ),
    )
    _sheet(
        wb,
        "Suppliers",
        brand("Suppliers"),
        [("Supplier", "t"), ("GSTIN", "t"), ("Mobile", "t"), ("You owe", "m")],
        _rows(
            db,
            "SELECT s.name, s.gstin, s.phone, b.balance FROM suppliers s JOIN supplier_balances b ON b.supplier_id = s.id"
            " WHERE s.shop_id = :s AND s.deleted_at IS NULL ORDER BY b.balance DESC",
            **p,
        ),
    )
    _sheet(
        wb,
        "Expenses",
        brand("Expenses"),
        [
            ("Date", "d"),
            ("Category", "t"),
            ("Paid by", "t"),
            ("Note", "t"),
            ("GST", "m"),
            ("Amount", "m"),
        ],
        _rows(
            db,
            "SELECT occurred_on, category_name, method, note, gst_amount, amount FROM expenses WHERE shop_id = :s AND deleted_at IS NULL"
            " AND occurred_on BETWEEN :d1 AND :d2 ORDER BY occurred_on",
            **p,
        ),
    )
    _sheet(
        wb,
        "Day Closes",
        brand("Day closes"),
        [
            ("Date", "d"),
            ("Opening", "m"),
            ("Cash in", "m"),
            ("Cash out", "m"),
            ("Expected", "m"),
            ("Counted", "m"),
            ("Difference", "m"),
            ("Status", "t"),
            ("By", "t"),
        ],
        _rows(
            db,
            "SELECT business_date, opening_cash, cash_in, cash_out, expected_cash, counted_cash, difference, status, closed_by_name"
            " FROM day_closes WHERE shop_id = :s AND business_date BETWEEN :d1 AND :d2 ORDER BY business_date",
            **p,
        ),
        totals=False,
    )
    _sheet(
        wb,
        "Staff",
        brand("Staff performance"),
        [
            ("Name", "t"),
            ("Bills", "q"),
            ("Sales", "m"),
            ("Average bill", "m"),
            ("Discounts given", "m"),
            ("Cancelled bills", "q"),
        ],
        _rows(
            db,
            "SELECT coalesce(created_by_name, 'Someone'), count(*) FILTER (WHERE status = 'issued'),"
            " coalesce(sum(grand_total) FILTER (WHERE status = 'issued'), 0), round(avg(grand_total) FILTER (WHERE status = 'issued'), 2),"
            " coalesce(sum(discount_total) FILTER (WHERE status = 'issued'), 0), count(*) FILTER (WHERE status = 'cancelled')"
            " FROM invoices WHERE shop_id = :s AND issued_at >= :a AND issued_at < :b GROUP BY 1 ORDER BY 3 DESC",
            **p,
        ),
    )
    _sheet(
        wb,
        "Labour Payments",
        brand("Wages and advances paid"),
        [
            ("Date", "d"),
            ("Worker", "t"),
            ("Type", "t"),
            ("Days", "q"),
            ("Amount", "m"),
            ("Note", "t"),
            ("Paid by", "t"),
        ],
        _rows(
            db,
            "SELECT lp.paid_on, w.name, lp.kind, lp.days, lp.amount, lp.note, lp.created_by_name FROM labour_payments lp"
            " JOIN labourers w ON w.id = lp.labourer_id WHERE lp.shop_id = :s AND lp.deleted_at IS NULL"
            " AND lp.paid_on BETWEEN :d1 AND :d2 ORDER BY lp.paid_on",
            **p,
        ),
    )
    _attendance(wb, db, p, start, end, brand)
    _sheet(
        wb,
        "Stock Movements",
        brand("Stock in and out"),
        [
            ("Date", "d"),
            ("Item", "t"),
            ("Variant", "t"),
            ("Type", "t"),
            ("Qty", "q"),
            ("Unit cost", "m"),
            ("Value", "m"),
            ("Reference", "t"),
            ("By", "t"),
        ],
        _rows(
            db,
            "SELECT (m.created_at AT TIME ZONE :tz)::date, p.name, v.name, replace(m.kind, '_', ' '), m.qty, m.unit_cost,"
            " round(m.qty * m.unit_cost, 2), m.reason, u.full_name FROM stock_movements m JOIN product_variants v ON v.id = m.variant_id"
            " JOIN products p ON p.id = v.product_id LEFT JOIN users u ON u.id = m.created_by"
            " WHERE m.shop_id = :s AND m.created_at >= :a AND m.created_at < :b ORDER BY m.created_at",
            **p,
        ),
        paint=lambda name, v: (
            ((GREEN_SOFT, GREEN) if v > 0 else (RED_SOFT, RED))
            if name == "Qty" and isinstance(v, Decimal) and v
            else None
        ),
    )
    goals = reports.list_goals(db, actor)
    ws = _sheet(
        wb,
        "Goals",
        brand("Goals"),
        [
            ("Goal", "t"),
            ("From", "d"),
            ("To", "d"),
            ("Target", "m"),
            ("Actual", "m"),
            ("% achieved", "q"),
            ("Status", "t"),
        ],
        [
            [
                g["title"],
                g["period_start"],
                g["period_end"],
                g["target"],
                g["actual"],
                g["percent"],
                g["status"].replace("_", " "),
            ]
            for g in goals
        ],
        totals=False,
    )
    if goals:
        ws.conditional_formatting.add(
            f"F5:F{4 + len(goals)}",
            DataBarRule(
                start_type="num", start_value=0, end_type="num", end_value=100, color="6E7FF3"
            ),
        )
    _sheet(
        wb,
        "Audit Log",
        brand("Who changed what"),
        [
            ("When", "d"),
            ("Who", "t"),
            ("Role", "t"),
            ("What", "t"),
            ("Action", "t"),
            ("Before", "t"),
            ("After", "t"),
        ],
        _rows(
            db,
            "SELECT (at AT TIME ZONE :tz)::date, actor_email, actor_role, entity, action, before::text, after::text"
            " FROM audit_log WHERE shop_id = :s AND at >= :a AND at < :b ORDER BY at",
            **p,
        ),
        totals=False,
    )
    # keep the overview sheets together up front
    wb.move_sheet("Daily Sales", offset=2 - wb.sheetnames.index("Daily Sales"))
    return _save(wb)


MARK = {
    "present": ("P", GREEN_SOFT, GREEN),
    "half_day": ("½", AMBER_SOFT, AMBER),
    "absent": ("A", RED_SOFT, RED),
}


def _attendance(
    wb: Workbook,
    db: Session,
    p: dict[str, Any],
    start: date,
    end: date,
    brand: Callable[[str], list[str]],
) -> None:
    """Muster roll: one row per worker, one column per day, P / ½ / A in green, amber and red."""
    first = max(
        start, end - timedelta(days=61)
    )  # ponytail: wide ranges show the last 62 days; a sheet per month if asked
    days = [first + timedelta(days=i) for i in range((end - first).days + 1)]
    marks: dict[Any, dict[date, str]] = {}
    workers = list(
        _q(
            db,
            "SELECT id, name, joined_on FROM labourers WHERE shop_id = :s AND deleted_at IS NULL ORDER BY name",
            s=p["s"],
        )
    )
    for r in _q(
        db,
        "SELECT labourer_id, day, status FROM labour_attendance WHERE shop_id = :s AND day BETWEEN :a AND :b",
        s=p["s"],
        a=first,
        b=end,
    ):
        marks.setdefault(r.labourer_id, {})[r.day] = r.status
    cols: Cols = [
        ("Worker", "t"),
        ("Present", "q"),
        ("Half days", "q"),
        ("Absent", "q"),
        ("Days worked", "q"),
    ] + [(f"{d:%d %a}", "t") for d in days]
    rows = []
    for w in workers:
        m = marks.get(w.id, {})
        n = {k: sum(1 for v in m.values() if v == k) for k in MARK}
        rows.append(
            [w.name, n["present"], n["half_day"], n["absent"], n["present"] + n["half_day"] / 2]
            + [MARK[m[d]][0] if d in m else ("" if d >= w.joined_on else "—") for d in days]
        )
    tone = {v[0]: (v[1], v[2]) for v in MARK.values()}
    ws = _sheet(
        wb,
        "Attendance",
        [
            *brand("Attendance register"),
            "P = present (green) · ½ = half day (amber) · A = absent (red) · — = not joined yet",
        ],
        cols,
        rows,
        totals=False,
        paint=lambda name, v: tone.get(v) if isinstance(v, str) else None,
    )
    for c in range(6, 6 + len(days)):
        letter = get_column_letter(c)
        ws.column_dimensions[letter].width = 6
        for r in range(6, 6 + len(rows)):
            ws.cell(r, c).alignment = Alignment(horizontal="center")
        if days[c - 6].weekday() == 6:  # Sundays stand out in the header
            ws.cell(5, c).fill = fill(AMBER)
    ws.column_dimensions["A"].width = 22


def gstr1(db: Session, actor: Actor, period: str) -> bytes:
    ctx = shop_ctx(db, actor)
    g = gst_returns.gstr1(db, actor, period)
    brand = lambda t: [*_brand(ctx, t, f"Return period {period}"), gst_returns.DISCLAIMER]  # noqa: E731
    tax = [("Taxable value", "m"), ("IGST", "m"), ("CGST", "m"), ("SGST", "m"), ("Cess", "m")]
    taxv = lambda r: [r["taxable"], r["igst"], r["cgst"], r["sgst"], r["cess"]]  # noqa: E731
    wb = Workbook()
    wb.remove(wb.active)
    _sheet(
        wb,
        "b2b",
        brand("B2B invoices (4A)"),
        [
            ("GSTIN of recipient", "t"),
            ("Receiver name", "t"),
            ("Invoice no.", "t"),
            ("Invoice date", "d"),
            ("Invoice value", "m"),
            ("Place of supply", "t"),
            ("Reverse charge", "t"),
            ("Rate", "q"),
            *tax,
        ],
        [
            [
                r["gstin"],
                r["buyer_name"],
                r["number"],
                r["date"],
                r["value"],
                gst_returns._pos(r["pos"]),
                "N",
                r["rate"],
                *taxv(r),
            ]
            for r in g["b2b"]
        ],
    )
    _sheet(
        wb,
        "b2cl",
        brand("B2C large invoices (5)"),
        [
            ("Invoice no.", "t"),
            ("Invoice date", "d"),
            ("Invoice value", "m"),
            ("Place of supply", "t"),
            ("Rate", "q"),
            *tax,
        ],
        [
            [r["number"], r["date"], r["value"], gst_returns._pos(r["pos"]), r["rate"], *taxv(r)]
            for r in g["b2cl"]
        ],
    )
    _sheet(
        wb,
        "b2cs",
        brand("B2C small (7)"),
        [("Type", "t"), ("Place of supply", "t"), ("Rate", "q"), *tax],
        [["OE", gst_returns._pos(r["pos"]), r["rate"], *taxv(r)] for r in g["b2cs"]],
    )
    note_cols: Cols = [
        ("Note no.", "t"),
        ("Note date", "d"),
        ("Against invoice", "t"),
        ("Invoice date", "d"),
        ("Note type", "t"),
        ("Note value", "m"),
        ("Place of supply", "t"),
        ("Rate", "q"),
        *tax,
    ]
    _sheet(
        wb,
        "cdnr",
        brand("Credit notes, registered (9B)"),
        [("GSTIN of recipient", "t"), *note_cols],
        [
            [
                r["gstin"],
                r["number"],
                r["date"],
                r["invoice_number"],
                r["invoice_date"],
                "C",
                r["value"],
                gst_returns._pos(r["pos"]),
                r["rate"],
                *taxv(r),
            ]
            for r in g["cdnr"]
        ],
    )
    _sheet(
        wb,
        "cdnur",
        brand("Credit notes, unregistered (9B)"),
        [("UR type", "t"), *note_cols],
        [
            [
                "B2CL",
                r["number"],
                r["date"],
                r["invoice_number"],
                r["invoice_date"],
                "C",
                r["value"],
                gst_returns._pos(r["pos"]),
                r["rate"],
                *taxv(r),
            ]
            for r in g["cdnur"]
        ],
    )
    hsn_cols: Cols = [("HSN", "t"), ("UQC", "t"), ("Total quantity", "q"), ("Rate", "q"), *tax]
    for part in ("b2b", "b2c"):
        _sheet(
            wb,
            f"hsn({part})",
            brand(f"HSN summary, {part.upper()} (12)"),
            hsn_cols,
            [[r["hsn"], r["uqc"], r["qty"], r["rate"], *taxv(r)] for r in g["hsn"][part]],
        )
    _sheet(
        wb,
        "docs",
        brand("Documents issued (13)"),
        [
            ("Nature of document", "t"),
            ("Sr. no. from", "t"),
            ("Sr. no. to", "t"),
            ("Total", "q"),
            ("Cancelled", "q"),
        ],
        [[d["nature"], d["sr_from"], d["sr_to"], d["total"], d["cancelled"]] for d in g["docs"]],
        totals=False,
    )
    _sheet(
        wb,
        "exemp",
        brand("Nil rated / exempt (8)"),
        [("Description", "t"), ("Nil rated / exempt supplies", "m")],
        [
            [
                k.replace("_", " ")
                .replace("inter", "Inter-state supplies to")
                .replace("intra", "Intra-state supplies to")
                + " persons",
                v,
            ]
            for k, v in g["nil"].items()
        ],
    )
    g3 = gst_returns.gstr3b(db, actor, period)
    o, itc, pay = g3["outward_taxable"], g3["itc"], g3["payable"]
    _sheet(
        wb,
        "GSTR-3B",
        brand("GSTR-3B summary"),
        [
            ("Table", "t"),
            ("Taxable value", "m"),
            ("IGST", "m"),
            ("CGST", "m"),
            ("SGST", "m"),
            ("Cess", "m"),
        ],
        [
            ["3.1(a) Outward taxable supplies", *taxv(o)],
            ["3.1(c) Nil rated / exempt", g3["nil_exempt"], None, None, None, None],
            [
                "4(A)(5) ITC, all other (estimate)",
                None,
                itc["igst"],
                itc["cgst"],
                itc["sgst"],
                itc["cess"],
            ],
            [
                "Net tax payable (before set-off)",
                None,
                pay["igst"],
                pay["cgst"],
                pay["sgst"],
                pay["cess"],
            ],
        ]
        + [
            [
                f"3.2 To unregistered persons, {gst_returns._pos(r['pos'])}",
                r["taxable"],
                r["igst"],
                None,
                None,
                None,
            ]
            for r in g3["inter_state_unregistered"]
        ],
        totals=False,
    )
    return _save(wb)


def _save(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

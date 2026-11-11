"""Excel workbooks for owners and accountants (docs/09-finance-reports-goals.md §4).

ponytail: built synchronously in the request; move to the export job (spec: > 5,000 rows) when a shop gets that big.
"""

import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.formatting.rule import DataBarRule
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy.orm import Session

from app.database import Actor
from app.services.finance import gst_returns, reports
from app.services.finance.metrics import bounds
from app.services.sales import _q, shop_ctx

INR = "#,##,##0.00"
HEAD = PatternFill("solid", fgColor="E8EBFA")
# Column kinds: "m" money (Indian format, summed), "q" quantity, "d" date, "t" text.
Cols = list[tuple[str, str]]


def _sheet(
    wb: Workbook,
    title: str,
    brand: list[str],
    cols: Cols,
    rows: list[list[Any]],
    totals: bool = True,
) -> Worksheet:
    ws = wb.create_sheet(title[:31])
    for i, line in enumerate(brand, start=1):
        ws.cell(i, 1, line).font = Font(
            bold=i == 1, size=13 if i == 1 else 10, color=None if i == 1 else "666666"
        )
    top = len(brand) + 2
    for c, (name, _) in enumerate(cols, start=1):
        cell = ws.cell(top, c, name)
        cell.font, cell.fill = Font(bold=True), HEAD
    for r, row in enumerate(rows, start=top + 1):
        for c, v in enumerate(row, start=1):
            if isinstance(v, datetime):
                v = v.replace(tzinfo=None)
            cell = ws.cell(r, c, float(v) if isinstance(v, Decimal) else v)
            kind = cols[c - 1][1]
            cell.number_format = (
                INR
                if kind == "m"
                else "0.###"
                if kind == "q"
                else "dd-mm-yyyy"
                if kind == "d"
                else "General"
            )
    last = top + len(rows)
    if totals and rows:  # real formulas, so an accountant can audit the sums
        ws.cell(last + 1, 1, "Total").font = Font(bold=True)
        for c, (_, kind) in enumerate(cols, start=1):
            if kind == "m" and c > 1:
                col = get_column_letter(c)
                cell = ws.cell(last + 1, c, f"=SUM({col}{top + 1}:{col}{last})")
                cell.number_format, cell.font = INR, Font(bold=True)
    ws.freeze_panes = ws.cell(top + 1, 1)
    if rows:
        ws.auto_filter.ref = f"A{top}:{get_column_letter(len(cols))}{last}"
    for c, (name, kind) in enumerate(cols, start=1):
        ws.column_dimensions[get_column_letter(c)].width = (
            max(12, min(40, len(name) + 4)) if kind != "t" else 28
        )
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return ws


def _brand(ctx: Any, title: str, period: str) -> list[str]:
    return [
        f"{ctx.name} · {title}",
        f"GSTIN {ctx.gstin or 'not registered'} · {period} · generated {datetime.now(ctx.tz):%d %b %Y %H:%M}",
    ]


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
    _sheet(
        wb,
        "Summary",
        brand("Summary"),
        [("Figure", "t"), ("Amount", "m")],
        [[label, t[k]] for label, k in lines]
        + [["Bills", t["invoices_count"]], ["Average bill", t["avg_bill_value"]]],
        totals=False,
    )
    _sheet(
        wb,
        "P&L",
        brand("Profit & loss"),
        [("Line", "t")] + [(f"{m['from']:%b %Y}", "m") for m in pl["months"]] + [("Total", "m")],
        [[label] + [m[k] for m in pl["months"]] + [t[k]] for label, k in lines],
        totals=False,
    )
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
    return _save(wb)


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

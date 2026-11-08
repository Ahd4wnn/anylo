"""A4 GST invoice PDF from the receipt model (Rule 46 particulars, docs/06-gst.md §7)."""

import io
from decimal import Decimal
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.catalogue_io import _font

INK = colors.HexColor("#1F2433")
MUTED = colors.HexColor("#5D6478")
LINE = colors.HexColor("#CDD2E0")
TINT = colors.HexColor("#EEF1FB")


def _m(v: Any, rupee: str) -> str:
    return f"{rupee}{Decimal(v):,.2f}"


def render(r: dict[str, Any]) -> bytes:
    font = _font()
    rupee = "₹" if font != "Helvetica" else "Rs."
    base = ParagraphStyle("b", fontName=font, fontSize=9, leading=12, textColor=INK)
    small = ParagraphStyle("s", parent=base, fontSize=8, leading=10, textColor=MUTED)
    title = ParagraphStyle("t", parent=base, fontSize=16, leading=20)
    right = ParagraphStyle("r", parent=base, alignment=2)
    P = lambda t, s=base: Paragraph(str(t).replace("&", "&amp;").replace("<", "&lt;"), s)  # noqa: E731

    shop, buyer, t = r["shop"], r["buyer"], r["totals"]
    story: list[Any] = []
    head_left = [
        P(shop["name"], title),
        P(shop["legal_name"] or "", small),
        P(shop["address"], small),
        P(
            f"State: {shop['state']}" + (f"   Phone: {shop['phone']}" if shop["phone"] else ""),
            small,
        ),
    ]
    if shop["gstin"]:
        head_left.append(P(f"GSTIN: {shop['gstin']}", base))
    head_right = [
        P(r["title"], ParagraphStyle("h", parent=title, alignment=2)),
        P(f"No: <b>{r['number']}</b>".replace("<b>", "").replace("</b>", ""), right),
        P(f"Date: {r['issued_at']:%d %b %Y, %I:%M %p}", right),
    ]
    if r["status"] == "cancelled":
        head_right.append(
            P("CANCELLED", ParagraphStyle("c", parent=right, textColor=colors.HexColor("#C0444A")))
        )
    story.append(
        Table(
            [[head_left, head_right]],
            colWidths=[110 * mm, 70 * mm],
            style=[("VALIGN", (0, 0), (-1, -1), "TOP")],
        )
    )
    if r["composition_note"]:
        story += [Spacer(0, 3 * mm), P(r["composition_note"], small)]
    story.append(Spacer(0, 5 * mm))

    bill_to = [P("Bill to", small)]
    if buyer:
        bill_to += [P(buyer["name"] or "Customer")] + (
            [P(buyer["address"], small)] if buyer["address"] else []
        )
        bill_to += [
            P(x, small)
            for x in (
                f"GSTIN: {buyer['gstin']}" if buyer["gstin"] else "",
                f"Phone: {buyer['phone']}" if buyer["phone"] else "",
            )
            if x
        ]
    else:
        bill_to.append(P("Walk-in customer"))
    supply = [
        P("Place of supply", small),
        P(r["place_of_supply"]),
        P(f"Reverse charge: {r['reverse_charge']}", small),
    ]
    if r["delivery_address"]:
        supply.append(P(f"Ship to: {r['delivery_address']}", small))
    story.append(
        Table(
            [[bill_to, supply]],
            colWidths=[110 * mm, 70 * mm],
            style=[
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ],
        )
    )
    story.append(Spacer(0, 5 * mm))

    inter = r["supply_type"] == "inter"
    regular = bool(r["tax_summary"])
    header = (
        ["#", "Item", "HSN", "Qty", "Rate", "Disc.", "Taxable"]
        + (["GST %"] if regular else [])
        + ["Amount"]
    )
    rows = [header]
    for i, ln in enumerate(r["lines"], 1):
        name = ln["name"] + (f" ({ln['variant_name']})" if ln["variant_name"] else "")
        row = [
            str(i),
            P(name),
            ln["hsn"] or "",
            f"{Decimal(ln['qty']).normalize():f} {ln['unit']}",
            _m(ln["unit_price"], ""),
            _m(ln["discount"], "") if Decimal(ln["discount"]) else "",
            _m(ln["taxable"], ""),
        ]
        rows.append(
            row
            + ([f"{Decimal(ln['tax_rate']).normalize():f}"] if regular else [])
            + [_m(ln["line_total"], "")]
        )
    widths = [7, 58, 16, 20, 20, 16, 22] + ([13] if regular else []) + [24]
    story.append(
        Table(
            rows,
            colWidths=[w * mm for w in widths],
            repeatRows=1,
            style=TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("BACKGROUND", (0, 0), (-1, 0), TINT),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
                    ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            ),
        )
    )
    story.append(Spacer(0, 4 * mm))

    tax_rows: list[list[Any]] = []
    if regular:
        tax_rows.append(
            ["GST %", "Taxable", *(["IGST"] if inter else ["CGST", r["state_tax_label"]]), "Cess"]
        )
        for s in r["tax_summary"]:
            tax_rows.append(
                [
                    f"{Decimal(s['rate']).normalize():f}%",
                    _m(s["taxable"], ""),
                    *([_m(s["igst"], "")] if inter else [_m(s["cgst"], ""), _m(s["sgst"], "")]),
                    _m(s["cess"], ""),
                ]
            )
    totals = [["Taxable value", _m(t["taxable_total"], rupee)]]
    if regular:
        totals += (
            [["IGST", _m(t["igst_total"], rupee)]]
            if inter
            else [
                ["CGST", _m(t["cgst_total"], rupee)],
                [r["state_tax_label"], _m(t["sgst_total"], rupee)],
            ]
        )
        if Decimal(t["cess_total"]):
            totals.append(["Cess", _m(t["cess_total"], rupee)])
    if Decimal(t["round_off"]):
        totals.append(["Round off", _m(t["round_off"], rupee)])
    totals.append(["TOTAL", _m(t["grand_total"], rupee)])
    if Decimal(t["due_total"]):
        totals += [["Paid", _m(t["paid_total"], rupee)], ["Balance due", _m(t["due_total"], rupee)]]
    tax_tbl = (
        Table(
            tax_rows,
            style=[
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), TINT),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ],
        )
        if tax_rows
        else ""
    )
    tot_tbl = Table(
        totals,
        colWidths=[35 * mm, 35 * mm],
        style=[
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            (
                "FONTSIZE",
                (0, len(totals) - 1 - (2 if Decimal(t["due_total"]) else 0)),
                (-1, len(totals) - 1 - (2 if Decimal(t["due_total"]) else 0)),
                11,
            ),
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, LINE),
        ],
    )
    story.append(
        Table(
            [[tax_tbl, tot_tbl]],
            colWidths=[110 * mm, 70 * mm],
            style=[("VALIGN", (0, 0), (-1, -1), "TOP")],
        )
    )
    story += [Spacer(0, 3 * mm), P(r["amount_in_words"], base)]
    if r["payments"]:
        story.append(
            P(
                "Paid by "
                + ", ".join(
                    f"{p['method'].upper()} {_m(p['amount'], rupee)}" for p in r["payments"]
                ),
                small,
            )
        )
    if r["remarks"]:
        story.append(P(f"Note: {r['remarks']}", small))
    story += [
        Spacer(0, 10 * mm),
        P(r["footer"], small),
        P(f"This is a computer-generated document. Authorised signatory: {shop['name']}", small),
    ]

    buf = io.BytesIO()
    SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"{r['title']} {r['number']}",
    ).build(story)
    return buf.getvalue()

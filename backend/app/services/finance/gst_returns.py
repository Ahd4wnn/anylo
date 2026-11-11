"""GSTR-1, GSTR-3B and CMP-08 figures for a month or quarter (docs/06-gst.md §13).

GSTR-3B Table 3 is built from exactly the GSTR-1 data (hard-locked on the portal since the July 2025 period).
ponytail: the portal JSON export isn't produced yet; the Excel sheets follow the offline-tool layout for upload help.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.database import Actor
from app.errors import AppError
from app.schemas.money import q2
from app.services.finance.metrics import ZERO, bounds
from app.services.gst.india import STATES
from app.services.sales import ShopCtx, _q, shop_ctx

TAX = ("taxable", "igst", "cgst", "sgst", "cess")
B2CL_LIMIT = Decimal("100000")
DISCLAIMER = "Prepared by Anylo for filing assistance. Verify before filing."


def month_range(period: str) -> tuple[date, date]:
    try:
        y, m = (int(x) for x in period.split("-"))
        start = date(y, m, 1)
    except (ValueError, TypeError):
        raise AppError("gst.bad_period", "Use a month like 2026-10.", 422) from None
    return start, (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def _sum(rows: list[dict[str, Any]], keys: tuple[str, ...] = TAX) -> dict[str, Decimal]:
    return {k: sum((r[k] for r in rows), ZERO) for k in keys}


def _pos(code: str) -> str:
    return f"{code}-{STATES.get(code, code)}"


# Section of an invoice: registered buyer, large inter-state B2C, or everything else B2C.
SECTION = (
    "CASE WHEN i.buyer_gstin IS NOT NULL THEN 'b2b'"
    f" WHEN i.supply_type = 'inter' AND i.grand_total > {B2CL_LIMIT} THEN 'b2cl' ELSE 'b2cs' END"
)
SUMS = "sum(l.taxable) AS taxable, sum(l.igst) AS igst, sum(l.cgst) AS cgst, sum(l.sgst) AS sgst, sum(l.cess) AS cess"


def gstr1(db: Session, actor: Actor, period: str) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    if ctx.scheme != "regular":
        raise AppError(
            "gst.not_regular",
            "GSTR-1 is for regular GST shops. Composition shops file CMP-08.",
            409,
        )
    start, end = month_range(period)
    a, b = bounds(ctx, start, end)
    inv_rows = [
        dict(r)
        for r in _q(
            db,
            f"SELECT {SECTION} AS sec, i.number, (i.issued_at AT TIME ZONE :tz)::date AS date, i.buyer_gstin AS gstin,"
            f" i.buyer_name, i.grand_total AS value, i.place_of_supply AS pos, i.supply_type, l.tax_rate AS rate, {SUMS}"
            " FROM invoices i JOIN invoice_lines l ON l.invoice_id = i.id"
            " WHERE i.shop_id = :s AND i.status = 'issued' AND i.issued_at >= :a AND i.issued_at < :b"
            " GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9 ORDER BY 3, 2",
            s=ctx.id,
            a=a,
            b=b,
            tz=str(ctx.tz),
        ).mappings()
    ]
    cn_rows = [
        dict(r)
        for r in _q(
            db,
            f"SELECT {SECTION} AS sec, n.number, (n.issued_at AT TIME ZONE :tz)::date AS date, i.number AS invoice_number,"
            " (i.issued_at AT TIME ZONE :tz)::date AS invoice_date, i.buyer_gstin AS gstin, n.grand_total AS value,"
            f" n.place_of_supply AS pos, n.supply_type, l.tax_rate AS rate, {SUMS}"
            " FROM credit_notes n JOIN credit_note_lines l ON l.credit_note_id = n.id JOIN invoices i ON i.id = n.original_invoice_id"
            " WHERE n.shop_id = :s AND n.issued_at >= :a AND n.issued_at < :b GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 ORDER BY 3, 2",
            s=ctx.id,
            a=a,
            b=b,
            tz=str(ctx.tz),
        ).mappings()
    ]
    rated = [r for r in inv_rows if r["rate"] > 0]
    rated_cn = [r for r in cn_rows if r["rate"] > 0]

    # B2CS: grouped by place of supply + rate, with notes against B2CS invoices netted in (Table 7).
    b2cs: dict[tuple[str, Decimal], dict[str, Any]] = {}
    for r, sign in [(r, 1) for r in rated if r["sec"] == "b2cs"] + [
        (r, -1) for r in rated_cn if r["sec"] == "b2cs"
    ]:
        row = b2cs.setdefault(
            (r["pos"], r["rate"]),
            {"pos": r["pos"], "supply_type": r["supply_type"], "rate": r["rate"]}
            | dict.fromkeys(TAX, ZERO),
        )
        for k in TAX:
            row[k] += sign * r[k]

    # Nil / exempt (Table 8): zero-rated lines, by inter/intra and registered/unregistered.
    nil: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for r, sign in [(r, 1) for r in inv_rows if r["rate"] == 0] + [
        (r, -1) for r in cn_rows if r["rate"] == 0
    ]:
        nil[f"{r['supply_type']}_{'registered' if r['gstin'] else 'unregistered'}"] += (
            sign * r["taxable"]
        )

    hsn = _hsn(db, ctx, a, b)
    docs = [
        dict(r)
        for r in _q(
            db,
            "SELECT 'Invoices for outward supply' AS nature, min(number) AS sr_from, max(number) AS sr_to, count(*) AS total,"
            " count(*) FILTER (WHERE status = 'cancelled') AS cancelled FROM invoices WHERE shop_id = :s AND issued_at >= :a AND issued_at < :b"
            " HAVING count(*) > 0"
            " UNION ALL SELECT 'Credit notes', min(number), max(number), count(*), 0 FROM credit_notes WHERE shop_id = :s"
            " AND issued_at >= :a AND issued_at < :b HAVING count(*) > 0",
            s=ctx.id,
            a=a,
            b=b,
        ).mappings()
    ]
    sections = {
        "b2b": [r for r in rated if r["sec"] == "b2b"],
        "b2cl": [r for r in rated if r["sec"] == "b2cl"],
        "b2cs": sorted(b2cs.values(), key=lambda r: (r["pos"], r["rate"])),
        "cdnr": [r for r in rated_cn if r["sec"] == "b2b"],
        "cdnur": [r for r in rated_cn if r["sec"] == "b2cl"],
    }
    return {
        "period": period,
        "gstin": ctx.gstin,
        "disclaimer": DISCLAIMER,
        **sections,
        "nil": {
            k: nil[k]
            for k in (
                "inter_registered",
                "intra_registered",
                "inter_unregistered",
                "intra_unregistered",
            )
        },
        "hsn": hsn,
        "docs": docs,
        "totals": {k: _sum(v) for k, v in sections.items()},
    }


def _hsn(db: Session, ctx: ShopCtx, a: Any, b: Any) -> dict[str, list[dict[str, Any]]]:
    """Table 12, split B2B / B2C, net of credit notes."""
    out: dict[tuple[bool, str, str, Decimal], dict[str, Any]] = {}
    for sql, sign in (
        (
            "SELECT i.buyer_gstin IS NOT NULL AS b2b, coalesce(l.hsn_code, '') AS hsn, l.unit_code AS uqc, l.tax_rate AS rate,"
            f" sum(l.qty) AS qty, {SUMS} FROM invoice_lines l JOIN invoices i ON i.id = l.invoice_id"
            " WHERE i.shop_id = :s AND i.status = 'issued' AND i.issued_at >= :a AND i.issued_at < :b GROUP BY 1, 2, 3, 4",
            1,
        ),
        (
            "SELECT i.buyer_gstin IS NOT NULL AS b2b, coalesce(l.hsn_code, '') AS hsn, l.unit_code AS uqc, l.tax_rate AS rate,"
            f" sum(l.qty) AS qty, {SUMS} FROM credit_note_lines l JOIN credit_notes n ON n.id = l.credit_note_id"
            " JOIN invoices i ON i.id = n.original_invoice_id WHERE n.shop_id = :s AND n.issued_at >= :a AND n.issued_at < :b"
            " GROUP BY 1, 2, 3, 4",
            -1,
        ),
    ):
        for r in _q(db, sql, s=ctx.id, a=a, b=b):
            row = out.setdefault(
                (r.b2b, r.hsn, r.uqc, r.rate),
                {"hsn": r.hsn, "uqc": r.uqc, "rate": r.rate, "qty": ZERO}
                | dict.fromkeys(TAX, ZERO),
            )
            row["qty"] += sign * r.qty
            for k in TAX:
                row[k] += sign * getattr(r, k)
    return {
        "b2b": [v for (b2b, *_), v in sorted(out.items(), key=lambda kv: kv[0][1:]) if b2b],
        "b2c": [v for (b2b, *_), v in sorted(out.items(), key=lambda kv: kv[0][1:]) if not b2b],
    }


def gstr3b(db: Session, actor: Actor, period: str) -> dict[str, Any]:
    g1 = gstr1(db, actor, period)
    ctx = shop_ctx(db, actor)
    t = g1["totals"]
    outward = {
        k: t["b2b"][k] + t["b2cl"][k] + t["b2cs"][k] - t["cdnr"][k] - t["cdnur"][k] for k in TAX
    }
    unreg: dict[str, dict[str, Decimal]] = {}
    for r, sign in (
        [(r, 1) for r in g1["b2cl"]] + [(r, -1) for r in g1["cdnur"]] + [(r, 1) for r in g1["b2cs"]]
    ):
        if r["supply_type"] == "inter":
            row = unreg.setdefault(r["pos"], {"taxable": ZERO, "igst": ZERO})
            row["taxable"] += sign * r["taxable"]
            row["igst"] += sign * r["igst"]
    # ITC belongs to the month on the supplier's bill (what GSTR-2B uses), not the day it was entered here.
    start, end = month_range(period)
    itc = dict(
        _q(
            db,
            "SELECT coalesce(sum(igst_total), 0) AS igst, coalesce(sum(cgst_total), 0) AS cgst, coalesce(sum(sgst_total), 0) AS sgst,"
            " coalesce(sum(cess_total), 0) AS cess FROM purchases WHERE shop_id = :s AND status = 'posted' AND itc_eligible"
            " AND coalesce(supplier_invoice_date, (posted_at AT TIME ZONE :tz)::date) BETWEEN :d1 AND :d2",
            s=ctx.id,
            d1=start,
            d2=end,
            tz=str(ctx.tz),
        )
        .one()
        ._mapping
    )
    # Expenses: GST paid on a supplier bill (intra-state, split CGST/SGST), and reverse charge the shop pays itself.
    e = _q(
        db,
        "SELECT coalesce(sum(gst_amount) FILTER (WHERE itc_eligible AND NOT reverse_charge), 0) AS itc,"
        " coalesce(sum(round(amount * rcm_rate / 100, 2)) FILTER (WHERE reverse_charge), 0) AS rcm"
        " FROM expenses WHERE shop_id = :s AND deleted_at IS NULL AND occurred_on BETWEEN :d1 AND :d2",
        s=ctx.id,
        d1=start,
        d2=end,
    ).one()
    rcm_half = q2(e.rcm / 2)
    rcm = {"taxable": ZERO, "igst": ZERO, "cgst": rcm_half, "sgst": e.rcm - rcm_half, "cess": ZERO}
    eh = q2(e.itc / 2)
    # RCM tax paid in cash is claimable as ITC the same month (regular shops).
    claim_rcm = ctx.scheme == "regular"
    itc = {
        "igst": itc["igst"],
        "cgst": itc["cgst"] + eh + (rcm["cgst"] if claim_rcm else ZERO),
        "sgst": itc["sgst"] + (e.itc - eh) + (rcm["sgst"] if claim_rcm else ZERO),
        "cess": itc["cess"],
    }
    # ponytail: shown per tax head without the IGST/CGST/SGST cross set-off order; the portal applies that when filing.
    payable = {k: outward[k] + rcm[k] - itc[k] for k in ("igst", "cgst", "sgst", "cess")}
    return {
        "period": period,
        "gstin": g1["gstin"],
        "disclaimer": DISCLAIMER,
        "outward_taxable": outward,  # 3.1(a)
        "nil_exempt": sum(g1["nil"].values(), ZERO),  # 3.1(c)
        "inter_state_unregistered": [{"pos": k} | v for k, v in sorted(unreg.items())],  # 3.2
        "inward_rcm": rcm,  # 3.1(d)
        "itc": itc,  # 4(A)(3) + 4(A)(5)
        "payable": payable,
        "itc_note": "Estimate from purchases you entered. Check it against GSTR-2B before filing.",
    }


def cmp08(db: Session, actor: Actor, start: date, end: date) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    if ctx.scheme != "composition":
        raise AppError("gst.not_composition", "CMP-08 is only for composition shops.", 409)
    rate = _q(
        db,
        "SELECT coalesce(composition_rate, 1) FROM shop_tax_profiles WHERE shop_id = :s",
        s=ctx.id,
    ).scalar()
    a, b = bounds(ctx, start, end)
    turnover = _q(
        db,
        # Composition tax is on taxable turnover only; exempt / nil / non-GST lines stay out.
        "SELECT (SELECT coalesce(sum(l.line_total), 0) FROM invoice_lines l JOIN invoices i ON i.id = l.invoice_id"
        "  WHERE i.shop_id = :s AND i.status = 'issued' AND i.issued_at >= :a AND i.issued_at < :b AND l.rate_kind = 'taxable')"
        " - (SELECT coalesce(sum(cl.line_total), 0) FROM credit_note_lines cl JOIN credit_notes c ON c.id = cl.credit_note_id"
        "  JOIN invoice_lines l ON l.id = cl.invoice_line_id"
        "  WHERE c.shop_id = :s AND c.issued_at >= :a AND c.issued_at < :b AND l.rate_kind = 'taxable')",
        s=ctx.id,
        a=a,
        b=b,
    ).scalar()
    tax = (turnover * rate / 100).quantize(Decimal("0.01"))
    return {
        "from": start,
        "to": end,
        "turnover": turnover,
        "rate": rate,
        "cgst": (tax / 2).quantize(Decimal("0.01")),
        "sgst": tax - (tax / 2).quantize(Decimal("0.01")),
        "total": tax,
        "disclaimer": DISCLAIMER,
    }

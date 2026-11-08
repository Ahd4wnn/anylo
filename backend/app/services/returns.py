"""Sales returns as GST credit notes (docs/06-gst.md §11, §11a)."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.database import Actor
from app.errors import AppError
from app.schemas.backoffice import CreditNoteIn
from app.services import audit
from app.services.catalogue import _move
from app.services.customers import balance_of
from app.services.gst.india import fy_label
from app.services.sales import _invoice_row, _pin_ok, _q, _today, next_number, shop_ctx
from app.services.shop import shop_id_of

ZERO = Decimal("0")
FIELDS = ("taxable", "cgst", "sgst", "igst", "cess", "line_total")


def q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def deadline(issued: date) -> date:
    """30 November after the end of the invoice's financial year."""
    fy_start = issued.year if issued.month >= 4 else issued.year - 1
    return date(fy_start + 1, 11, 30)


def _price_lines(db: Session, inv: Any, body: CreditNoteIn) -> list[dict[str, Any]]:
    lines = {
        r.id: r
        for r in _q(
            db,
            "SELECT l.*, p.track_stock FROM invoice_lines l LEFT JOIN product_variants v ON v.id = l.variant_id"
            " LEFT JOIN products p ON p.id = v.product_id WHERE l.invoice_id = :i FOR UPDATE OF l",
            i=inv.id,
        )
    }
    out = []
    seen: set[UUID] = set()
    for req in body.lines:
        ln = lines.get(req.invoice_line_id)
        if not ln or req.invoice_line_id in seen:
            raise AppError("credit_note.bad_line", "One of the items isn't on this bill.", 422)
        seen.add(req.invoice_line_id)
        left = ln.qty - ln.returned_qty
        if req.qty > left:
            raise AppError(
                "credit_note.too_many",
                f"Only {left.normalize()} of {ln.name} can still be returned.",
                422,
            )
        if req.qty == left:
            # Returning everything that's left: take the remainder so pro-rata rounding never drifts from the bill.
            done = _q(
                db,
                "SELECT "
                + ", ".join(f"coalesce(sum({f}), 0) AS {f}" for f in FIELDS)
                + " FROM credit_note_lines WHERE invoice_line_id = :l",
                l=ln.id,
            ).one()
            vals = {f: getattr(ln, f) - getattr(done, f) for f in FIELDS}
        else:
            vals = {f: q2(getattr(ln, f) * req.qty / ln.qty) for f in FIELDS[:-1]}
            vals["line_total"] = sum((vals[f] for f in FIELDS[:-1]), ZERO)
        out.append({"line": ln, "qty": req.qty, **vals})
    return out


def create(db: Session, actor: Actor, body: CreditNoteIn) -> tuple[dict[str, Any], int]:
    """Returns (credit note | approval request, status code)."""
    ctx = shop_ctx(db, actor)
    dup = _q(
        db,
        "SELECT id FROM credit_notes WHERE shop_id = :s AND idempotency_key = :k",
        s=ctx.id,
        k=body.idempotency_key,
    ).scalar()
    if dup:
        return get(db, actor, dup), 200
    inv = _invoice_row(db, actor, body.invoice_id)
    _check(ctx, inv, body)
    priced = _price_lines(db, inv, body)
    if actor.role == "salesperson" and not _pin_ok(db, ctx, body.approval_pin):
        from app.services import approvals

        total = sum((p["line_total"] for p in priced), ZERO)
        rid = approvals.request(
            db,
            actor,
            "return",
            inv.id,
            f"Return of ₹{total:,.2f} on {inv.number}",
            total,
            body.model_dump(mode="json", exclude={"approval_pin"}),
        )
        return {"approval_required": True, "approval_id": rid}, 202
    return _write(db, actor, ctx, inv, body, priced, actor.user_id), 201


def create_from_payload(
    db: Session, actor: Actor, payload: dict[str, Any], requested_by: UUID | None
) -> dict[str, Any]:
    body = CreditNoteIn.model_validate(payload)
    ctx = shop_ctx(db, actor)
    inv = _invoice_row(db, actor, body.invoice_id)
    _check(ctx, inv, body)  # the bill may have changed while the request waited
    return _write(
        db, actor, ctx, inv, body, _price_lines(db, inv, body), requested_by or actor.user_id
    )


def _check(ctx: Any, inv: Any, body: CreditNoteIn) -> None:
    if inv.status != "issued":
        raise AppError(
            "credit_note.cancelled_bill", "This bill was cancelled, so it can't be returned.", 409
        )
    if _today(ctx) > deadline(_today(ctx, inv.issued_at)):
        raise AppError(
            "credit_note.too_late",
            "The GST time limit for returns on this bill has passed (30 November after its financial year).",
            409,
        )
    if body.refund_method == "store_credit" and not inv.customer_id:
        raise AppError(
            "credit_note.needs_customer",
            "Store credit needs a customer on the bill. Refund in cash or UPI.",
            422,
        )


def _write(
    db: Session,
    actor: Actor,
    ctx: Any,
    inv: Any,
    body: CreditNoteIn,
    priced: list[dict[str, Any]],
    created_by: UUID | None,
) -> dict[str, Any]:
    tot = {f: sum((p[f] for p in priced), ZERO) for f in FIELDS}
    grand = (
        tot["line_total"].quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if ctx.round_off
        else tot["line_total"]
    )
    if grand <= 0:
        raise AppError("credit_note.zero", "Nothing to refund on these items.", 422)
    # The return first clears what is still owed on the bill; only the rest goes back to the customer.
    due_adjusted = min(inv.due_total, grand)
    refund = grand - due_adjusted
    refunded = refund if body.refund_method != "store_credit" else ZERO
    number, seq, series_key = next_number(db, ctx, fy_label(_today(ctx)), "credit_note", "CN")
    cn_id: UUID = _q(
        db,
        """INSERT INTO credit_notes (shop_id, series_key, fy, seq, number, original_invoice_id, customer_id, reason,
             refund_method, restock, place_of_supply, supply_type, taxable_total, cgst_total, sgst_total, igst_total,
             cess_total, round_off, grand_total, due_adjusted, refunded, note, idempotency_key, created_by, created_by_name)
           VALUES (:s, :sk, :fy, :seq, :num, :inv, :c, 'return', :rm, :rs, :pos, :st, :t, :cg, :sg, :ig, :ce, :ro, :gt,
             :da, :rf, :no, :k, :u, (SELECT full_name FROM users WHERE id = :u)) RETURNING id""",
        s=ctx.id,
        sk=series_key,
        fy=fy_label(_today(ctx)),
        seq=seq,
        num=number,
        inv=inv.id,
        c=inv.customer_id,
        rm=body.refund_method,
        rs=body.restock,
        pos=inv.place_of_supply,
        st=inv.supply_type,
        t=tot["taxable"],
        cg=tot["cgst"],
        sg=tot["sgst"],
        ig=tot["igst"],
        ce=tot["cess"],
        ro=grand - tot["line_total"],
        gt=grand,
        da=due_adjusted,
        rf=refunded,
        no=body.note,
        k=body.idempotency_key,
        u=created_by,
    ).scalar_one()
    for p in priced:
        ln = p["line"]
        _q(
            db,
            "INSERT INTO credit_note_lines (shop_id, credit_note_id, invoice_line_id, variant_id, name, hsn_code, unit_code,"
            " qty, taxable, tax_rate, cgst, sgst, igst, cess, line_total, cost_price)"
            " VALUES (:s, :cn, :l, :v, :n, :h, :u, :q, :t, :r, :cg, :sg, :ig, :ce, :lt, :cost)",
            s=ctx.id,
            cn=cn_id,
            l=ln.id,
            v=ln.variant_id,
            n=ln.name + (f" {ln.variant_name}" if ln.variant_name else ""),
            h=ln.hsn_code,
            u=ln.unit_code,
            q=p["qty"],
            t=p["taxable"],
            r=ln.tax_rate,
            cg=p["cgst"],
            sg=p["sgst"],
            ig=p["igst"],
            ce=p["cess"],
            lt=p["line_total"],
            cost=ln.cost_price,
        )
        _q(
            db,
            "UPDATE invoice_lines SET returned_qty = returned_qty + :q WHERE id = :l",
            q=p["qty"],
            l=ln.id,
        )
        if body.restock and ln.variant_id and ln.track_stock:
            _move(
                db,
                actor,
                ln.variant_id,
                "sale_return",
                p["qty"],
                ln.cost_price,
                number,
                ("credit_note", str(cn_id)),
            )
    if due_adjusted:
        _q(
            db,
            "UPDATE invoices SET due_total = due_total - :d WHERE id = :i",
            d=due_adjusted,
            i=inv.id,
        )
    if refunded:
        _q(
            db,
            "INSERT INTO payments (shop_id, direction, method, amount, party_type, party_id, applies_to_type, applies_to_id,"
            " received_by) VALUES (:s, 'out', :m, :a, 'customer', :c, 'credit_note', :cn, :u)",
            s=ctx.id,
            m=body.refund_method,
            a=refunded,
            c=inv.customer_id,
            cn=cn_id,
            u=actor.user_id,
        )
    audit.record(
        db,
        actor,
        "credit_note",
        cn_id,
        "create",
        None,
        {"number": number, "invoice": inv.number, "total": str(grand)},
    )
    return get(db, actor, cn_id)


def get(db: Session, actor: Actor, cn_id: UUID) -> dict[str, Any]:
    cn = _q(
        db,
        "SELECT n.*, i.number AS invoice_number, i.issued_at AS invoice_date, i.buyer_name, i.buyer_phone, i.buyer_gstin"
        " FROM credit_notes n LEFT JOIN invoices i ON i.id = n.original_invoice_id WHERE n.id = :i AND n.shop_id = :s",
        i=cn_id,
        s=shop_id_of(actor),
    ).first()
    if not cn:
        raise AppError("credit_note.not_found", "This credit note was not found.", 404)
    lines = _q(
        db, "SELECT * FROM credit_note_lines WHERE credit_note_id = :i ORDER BY name", i=cn_id
    ).mappings()
    out = dict(cn._mapping) | {"lines": [dict(r) for r in lines]}
    if cn.customer_id:
        out["customer_balance"] = balance_of(db, cn.customer_id)
    return out


def list_notes(
    db: Session, actor: Actor, invoice_id: UUID | None, limit: int, offset: int
) -> dict[str, Any]:
    p: dict[str, Any] = {"s": shop_id_of(actor), "lim": limit, "off": offset}
    where = "n.shop_id = :s"
    if invoice_id:
        where += " AND n.original_invoice_id = :inv"
        p["inv"] = invoice_id
    rows = _q(
        db,
        "SELECT n.id, n.number, n.issued_at, n.grand_total, n.refund_method, n.refunded, n.due_adjusted,"
        " i.number AS invoice_number, i.buyer_name, i.buyer_phone, n.created_by_name"
        f" FROM credit_notes n LEFT JOIN invoices i ON i.id = n.original_invoice_id WHERE {where}"
        " ORDER BY n.issued_at DESC LIMIT :lim OFFSET :off",
        **p,
    ).mappings()
    return {"items": [dict(r) for r in rows]}

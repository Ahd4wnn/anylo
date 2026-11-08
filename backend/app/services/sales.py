"""Checkout, invoices, payments, cancel/edit, receipts and held bills (docs/06-gst.md, docs/07-pos-billing.md)."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import media
from app.config import get_settings
from app.database import Actor, privileged_session
from app.errors import AppError
from app.schemas.sales import CartIn, CheckoutIn
from app.security import verify_password
from app.services import audit
from app.services.catalogue import _move
from app.services.gst import engine
from app.services.gst.india import STATES, UTGST_STATES, amount_in_words, fy_label
from app.services.shop import shop_id_of

ZERO = Decimal("0")
DOC_TITLES = {
    "tax_invoice": "TAX INVOICE",
    "bill_of_supply": "BILL OF SUPPLY",
    "cash_memo": "CASH MEMO",
}
COMPOSITION_NOTE = "Composition taxable person, not eligible to collect tax on supplies"


def _q(db: Session, sql: str, **p: Any) -> Any:
    return db.execute(text(sql), p)


@dataclass
class ShopCtx:
    id: UUID
    name: str
    state_code: str
    tz: ZoneInfo
    settings: dict[str, Any]
    scheme: str
    gstin: str | None
    round_off: bool
    default_inclusive: bool
    einvoice: bool


def shop_ctx(db: Session, actor: Actor) -> ShopCtx:
    r = _q(
        db,
        "SELECT s.id, s.name, s.state_code, s.timezone, s.settings, t.gst_scheme, t.gstin, t.invoice_round_off,"
        " t.prices_include_tax, t.einvoice_applicable FROM shops s JOIN shop_tax_profiles t ON t.shop_id = s.id"
        " WHERE s.id = :s",
        s=shop_id_of(actor),
    ).one()
    return ShopCtx(
        r.id,
        r.name,
        r.state_code,
        ZoneInfo(r.timezone),
        r.settings or {},
        r.gst_scheme,
        r.gstin,
        r.invoice_round_off,
        r.prices_include_tax,
        r.einvoice_applicable,
    )


def _today(ctx: ShopCtx, ts: datetime | None = None) -> Any:
    return (ts or datetime.now(UTC)).astimezone(ctx.tz).date()


# --- pricing ---


@dataclass
class Resolved:
    variant_id: UUID | None
    name: str
    variant_name: str | None
    hsn: str | None
    unit: str
    qty: Decimal
    unit_price: Decimal
    inclusive: bool
    rate: Decimal
    cess: Decimal
    cost: Decimal
    line_discount: Decimal
    track_stock: bool


def _resolve(db: Session, actor: Actor, ctx: ShopCtx, cart: CartIn) -> list[Resolved]:
    staff = actor.role == "salesperson"
    can_edit_price = bool(ctx.settings.get("staff_can_edit_price", False))
    ids = [ln.variant_id for ln in cart.lines if ln.variant_id]
    rows = (
        {
            r.id: r
            for r in _q(
                db,
                """
        SELECT v.id, v.name AS vname, v.sale_price, v.mrp, v.cost_price, v.is_active, p.name, p.hsn_code, p.unit_code,
          p.price_includes_tax, p.cess_rate, p.track_stock, p.deleted_at, r.rate
        FROM product_variants v JOIN products p ON p.id = v.product_id LEFT JOIN gst_rates r ON r.id = p.tax_rate_id
        WHERE v.id = ANY(:ids) AND v.shop_id = :s""",
                ids=ids,
                s=ctx.id,
            )
        }
        if ids
        else {}
    )
    out: list[Resolved] = []
    for ln in cart.lines:
        if ln.variant_id:
            v = rows.get(ln.variant_id)
            if not v or not v.is_active or v.deleted_at:
                raise AppError(
                    "invoice.item_unavailable", "An item in the bill is no longer available.", 422
                )
            price = ln.unit_price if ln.unit_price is not None else v.sale_price
            if staff and price != v.sale_price and not can_edit_price:
                raise AppError(
                    "invoice.price_locked", f"Only a manager can change the price of {v.name}.", 403
                )
            if staff and v.cost_price > 0 and price < v.cost_price:
                raise AppError(
                    "invoice.price_below_cost", f"{v.name} can't be sold below cost.", 403
                )
            if v.mrp is not None and price > v.mrp:
                raise AppError(
                    "invoice.above_mrp", f"{v.name} can't be sold above its MRP ₹{v.mrp}.", 422
                )
            if ctx.scheme == "regular" and v.rate is None:
                raise AppError(
                    "invoice.missing_rate", f"Set a GST rate for {v.name} in Items first.", 422
                )
            out.append(
                Resolved(
                    v.id,
                    v.name,
                    v.vname,
                    v.hsn_code,
                    v.unit_code,
                    ln.qty,
                    price,
                    v.price_includes_tax,
                    v.rate or ZERO,
                    v.cess_rate,
                    v.cost_price,
                    ln.line_discount,
                    v.track_stock,
                )
            )
        else:
            c = ln.custom
            assert c is not None and ln.unit_price is not None
            rate = ZERO
            if c.tax_rate_id:
                rate = _q(
                    db, "SELECT rate FROM gst_rates WHERE id = :r AND is_active", r=c.tax_rate_id
                ).scalar()
                if rate is None:
                    raise AppError("invoice.bad_rate", "Choose a current GST rate.", 422)
            elif ctx.scheme == "regular":
                raise AppError("invoice.missing_rate", f"Choose a GST rate for {c.name}.", 422)
            out.append(
                Resolved(
                    None,
                    c.name.strip(),
                    None,
                    c.hsn_code,
                    c.unit_code,
                    ln.qty,
                    ln.unit_price,
                    c.price_includes_tax
                    if c.price_includes_tax is not None
                    else ctx.default_inclusive,
                    rate,
                    ZERO,
                    ZERO,
                    ln.line_discount,
                    False,
                )
            )
    return out


@dataclass
class Priced:
    lines: list[Resolved]
    out: engine.InvoiceOut
    doc_type: str
    supply_type: str
    place_of_supply: str
    buyer_state: str | None


def price_cart(db: Session, actor: Actor, ctx: ShopCtx, cart: CartIn) -> Priced:
    lines = _resolve(db, actor, ctx, cart)
    buyer_gstin = cart.customer.gstin if cart.customer else None
    buyer_state = buyer_gstin[:2] if buyer_gstin else None
    if buyer_gstin and ctx.einvoice:
        raise AppError(
            "invoice.einvoice_required",
            "B2B invoices for your shop need an IRN from the e-invoice portal. "
            "Anylo can't generate IRNs yet.",
            422,
        )
    # Place of supply: counter sale = shop's state, even for buyers registered elsewhere (CA finding F2).
    if cart.delivery_mode == "dispatched":
        pos = cart.delivery_state_code or buyer_state
        if not pos:
            raise AppError(
                "invoice.delivery_state", "Choose the state the goods are going to.", 422
            )
    else:
        pos = ctx.state_code
    supply = "intra" if pos == ctx.state_code else "inter"
    out = engine.compute(
        engine.InvoiceIn(
            lines=[
                engine.LineIn(r.qty, r.unit_price, r.rate, r.cess, r.inclusive, r.line_discount)
                for r in lines
            ],
            supply_type=supply,  # type: ignore[arg-type]
            scheme=ctx.scheme,  # type: ignore[arg-type]
            discount_type=cart.discount_type,
            discount_value=cart.discount_value,
            round_off=ctx.round_off,
        )
    )
    if ctx.scheme == "regular":
        doc_type = "tax_invoice" if any(r.rate > 0 for r in lines) else "bill_of_supply"
    else:
        doc_type = "bill_of_supply" if ctx.scheme == "composition" else "cash_memo"
    return Priced(lines, out, doc_type, supply, pos, buyer_state)


def needs_approval(actor: Actor, ctx: ShopCtx, priced: Priced) -> bool:
    if actor.role != "salesperson" or priced.out.subtotal_gross == 0:
        return False
    limit = Decimal(str(ctx.settings.get("max_discount_pct", 10)))
    return priced.out.discount_total * 100 / priced.out.subtotal_gross > limit


def _pin_ok(db: Session, ctx: ShopCtx, pin: str | None) -> bool:
    if not pin:
        return False
    # privileged: a salesperson's RLS view can't see the owner's row, but any approver of this shop may approve.
    with privileged_session() as sys_db:
        hashes = list(
            sys_db.execute(
                text(
                    "SELECT u.pin_hash FROM users u WHERE u.is_active AND u.pin_hash IS NOT NULL AND"
                    " (u.shop_id = :s AND u.role = 'manager' OR u.id IN (SELECT owner_id FROM shop_owners WHERE shop_id = :s))"
                ),
                {"s": ctx.id},
            ).scalars()
        )
    return any(verify_password(pin, h) for h in hashes)


def preview(db: Session, actor: Actor, cart: CartIn) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    p = price_cart(db, actor, ctx, cart)
    o = p.out
    return {
        "doc_type": p.doc_type,
        "supply_type": p.supply_type,
        "place_of_supply": p.place_of_supply,
        "lines": [
            {
                "name": r.name + (f" {r.variant_name}" if r.variant_name else ""),
                "qty": r.qty,
                "unit_price": r.unit_price,
                "taxable": x.taxable,
                "tax_rate": x.rate,
                "cgst": x.cgst,
                "sgst": x.sgst,
                "igst": x.igst,
                "line_total": x.total,
            }
            for r, x in zip(p.lines, o.lines, strict=True)
        ],
        **{
            k: getattr(o, k)
            for k in (
                "subtotal_gross",
                "discount_total",
                "taxable_total",
                "cgst_total",
                "sgst_total",
                "igst_total",
                "cess_total",
                "round_off",
                "grand_total",
            )
        },
        "needs_approval": needs_approval(actor, ctx, p),
    }


# --- writing ---


def _customer(db: Session, ctx: ShopCtx, cart: CartIn, buyer_state: str | None) -> UUID | None:
    c = cart.customer
    if not c or not (c.phone or c.gstin or c.name):
        return None
    if c.phone:
        row = _q(
            db,
            "INSERT INTO customers (shop_id, name, phone, gstin, billing_address, state_code) VALUES (:s, :n, :p, :g, :a, :st)"
            " ON CONFLICT (shop_id, phone) WHERE phone IS NOT NULL DO UPDATE SET"
            " name = coalesce(EXCLUDED.name, customers.name), gstin = coalesce(EXCLUDED.gstin, customers.gstin),"
            " billing_address = coalesce(EXCLUDED.billing_address, customers.billing_address),"
            " state_code = coalesce(EXCLUDED.state_code, customers.state_code) RETURNING id",
            s=ctx.id,
            n=c.name,
            p=c.phone,
            g=c.gstin,
            a=c.address,
            st=buyer_state,
        ).scalar_one()
        return row  # type: ignore[no-any-return]
    new_id: UUID = _q(
        db,
        "INSERT INTO customers (shop_id, name, gstin, billing_address, state_code) VALUES (:s, :n, :g, :a, :st)"
        " RETURNING id",
        s=ctx.id,
        n=c.name,
        g=c.gstin,
        a=c.address,
        st=buyer_state,
    ).scalar_one()
    return new_id


def _write_lines_stock(
    db: Session, actor: Actor, ctx: ShopCtx, invoice_id: UUID, number: str, p: Priced
) -> None:
    allow_negative = bool(ctx.settings.get("allow_negative_stock", True))
    for i, (r, x) in enumerate(zip(p.lines, p.out.lines, strict=True), start=1):
        _q(
            db,
            """INSERT INTO invoice_lines (shop_id, invoice_id, line_no, variant_id, name, variant_name, hsn_code, unit_code,
                  qty, unit_price, price_includes_tax, gross, line_discount, invoice_discount_share, taxable, tax_rate, cess_rate,
                  cgst, sgst, igst, cess, line_total, cost_price)
                  VALUES (:s, :inv, :no, :v, :n, :vn, :h, :u, :q, :up, :inc, :g, :ld, :ids, :t, :rate, :cr, :c, :sg, :ig, :ce, :lt, :cost)""",
            s=ctx.id,
            inv=invoice_id,
            no=i,
            v=r.variant_id,
            n=r.name,
            vn=r.variant_name,
            h=r.hsn,
            u=r.unit,
            q=r.qty,
            up=r.unit_price,
            inc=r.inclusive,
            g=x.gross,
            ld=x.line_discount,
            ids=x.invoice_discount_share,
            t=x.taxable,
            rate=x.rate,
            cr=r.cess,
            c=x.cgst,
            sg=x.sgst,
            ig=x.igst,
            ce=x.cess,
            lt=x.total,
            cost=r.cost,
        )
        if r.track_stock and r.variant_id:
            if not allow_negative:
                have = _q(
                    db,
                    "SELECT stock_qty FROM product_variants WHERE id = :v FOR UPDATE",
                    v=r.variant_id,
                ).scalar()
                if have is not None and have < r.qty:
                    raise AppError(
                        "invoice.out_of_stock",
                        f"Only {have.normalize()} of {r.name} left in stock.",
                        409,
                    )
            _move(
                db,
                actor,
                r.variant_id,
                "sale",
                -r.qty,
                r.cost,
                number,
                ("invoice", str(invoice_id)),
            )


def _write_payments(
    db: Session,
    actor: Actor,
    ctx: ShopCtx,
    invoice_id: UUID,
    customer_id: UUID | None,
    payments: list[Any],
    grand: Decimal,
) -> tuple[Decimal, Decimal]:
    paid = sum((pm.amount for pm in payments), ZERO)
    if paid > grand:
        raise AppError(
            "invoice.overpaid",
            "Payments are more than the bill total. Enter the bill amount; change is shown separately.",
            422,
        )
    for pm in payments:
        _q(
            db,
            "INSERT INTO payments (shop_id, direction, method, amount, reference, party_type, party_id, applies_to_type,"
            " applies_to_id, received_by) VALUES (:s, 'in', :m, :a, :r, 'customer', :c, 'invoice', :i, :u)",
            s=ctx.id,
            m=pm.method,
            a=pm.amount,
            r=pm.reference,
            c=customer_id,
            i=invoice_id,
            u=actor.user_id,
        )
    return paid, grand - paid


def next_number(
    db: Session, ctx: ShopCtx, fy: str, kind: str = "sale", default_prefix: str = "INV"
) -> tuple[str, int, str]:
    """Gapless number for a sale, credit note or receipt series."""
    series_key = ctx.gstin or str(ctx.id)  # uniqueness is per GSTIN per FY (CA finding F10)
    prefix = (
        default_prefix
        if kind != "sale"
        else str(ctx.settings.get("invoice_prefix", default_prefix))
    )
    _q(
        db,
        "INSERT INTO doc_series (shop_id, kind, fy, prefix) VALUES (:s, :k, :fy, :p) ON CONFLICT DO NOTHING",
        s=ctx.id,
        k=kind,
        fy=fy,
        p=prefix[:4],
    )
    # Row lock serialises concurrent writers; a rolled-back transaction returns its number (gapless).
    row = _q(
        db,
        "UPDATE doc_series SET next_seq = next_seq + 1 WHERE shop_id = :s AND kind = :k AND fy = :fy"
        " RETURNING next_seq - 1 AS seq, prefix",
        s=ctx.id,
        k=kind,
        fy=fy,
    ).one()
    return f"{row.prefix}/{fy}/{row.seq:05d}", row.seq, series_key


def _credit_limit(db: Session, ctx: ShopCtx, phone: str, new_due: Decimal) -> None:
    """A salesperson can't push a customer past the credit limit the owner set; owners and managers decide themselves."""
    c = _q(
        db,
        "SELECT c.credit_limit, b.balance FROM customers c JOIN customer_balances b ON b.customer_id = c.id"
        " WHERE c.shop_id = :s AND c.phone = :p AND c.deleted_at IS NULL",
        s=ctx.id,
        p=phone,
    ).first()
    if c and c.credit_limit is not None and c.balance + new_due > c.credit_limit:
        raise AppError(
            "invoice.credit_limit",
            f"This would take the customer's dues past their limit of ₹{c.credit_limit:,.2f}. Ask the owner or manager.",
            422,
        )


def checkout(db: Session, actor: Actor, body: CheckoutIn) -> tuple[dict[str, Any], bool]:
    """Returns (invoice receipt model, replayed). Same idempotency key → same invoice, never a duplicate."""
    ctx = shop_ctx(db, actor)
    existing = _q(
        db,
        "SELECT id FROM invoices WHERE shop_id = :s AND idempotency_key = :k",
        s=ctx.id,
        k=body.idempotency_key,
    ).scalar()
    if existing:
        return receipt(db, actor, existing), True
    p = price_cart(db, actor, ctx, body)
    if needs_approval(actor, ctx, p) and not _pin_ok(db, ctx, body.approval_pin):
        raise AppError("invoice.approval_required", "This discount needs a manager's PIN.", 403)
    paid = sum((pm.amount for pm in body.payments), ZERO)
    has_phone = bool(body.customer and body.customer.phone)
    if paid < p.out.grand_total and not has_phone:
        raise AppError(
            "invoice.due_needs_customer", "Add the customer's mobile number to keep money due.", 422
        )
    if paid < p.out.grand_total and actor.role == "salesperson":
        _credit_limit(db, ctx, str(body.customer and body.customer.phone), p.out.grand_total - paid)
    try:
        with db.begin_nested():
            customer_id = _customer(db, ctx, body, p.buyer_state)
            fy = fy_label(_today(ctx))
            number, seq, series_key = next_number(db, ctx, fy)
            c = body.customer
            o = p.out
            inv_id: UUID = _q(
                db,
                """
                INSERT INTO invoices (shop_id, series_key, fy, seq, number, doc_type, customer_id, buyer_name, buyer_phone,
                  buyer_gstin, buyer_address, buyer_state_code, place_of_supply, supply_type, delivery_mode, delivery_address,
                  is_b2b, scheme, subtotal_gross, discount_type, discount_value, discount_total, taxable_total, cgst_total,
                  sgst_total, igst_total, cess_total, round_off, grand_total, remarks, idempotency_key, public_token,
                  created_by, created_by_name)
                VALUES (:s, :sk, :fy, :seq, :num, :dt, :cid, :bn, :bp, :bg, :ba, :bs, :pos, :st, :dm, :da, :b2b, :scheme,
                  :sub, :dtype, :dval, :dtot, :tax, :cg, :sg, :ig, :ce, :ro, :gt, :rem, :key, :tok, :u,
                  (SELECT full_name FROM users WHERE id = :u)) RETURNING id""",
                s=ctx.id,
                sk=series_key,
                fy=fy,
                seq=seq,
                num=number,
                dt=p.doc_type,
                cid=customer_id,
                bn=c.name if c else None,
                bp=c.phone if c else None,
                bg=c.gstin if c else None,
                ba=c.address if c else None,
                bs=p.buyer_state,
                pos=p.place_of_supply,
                st=p.supply_type,
                dm=body.delivery_mode,
                da=body.delivery_address,
                b2b=bool(c and c.gstin),
                scheme=ctx.scheme,
                sub=o.subtotal_gross,
                dtype=body.discount_type,
                dval=body.discount_value,
                dtot=o.discount_total,
                tax=o.taxable_total,
                cg=o.cgst_total,
                sg=o.sgst_total,
                ig=o.igst_total,
                ce=o.cess_total,
                ro=o.round_off,
                gt=o.grand_total,
                rem=body.remarks,
                key=body.idempotency_key,
                tok=secrets.token_urlsafe(16),
                u=actor.user_id,
            ).scalar_one()
            _write_lines_stock(db, actor, ctx, inv_id, number, p)
            paid, due = _write_payments(
                db, actor, ctx, inv_id, customer_id, body.payments, o.grand_total
            )
            _q(
                db,
                "UPDATE invoices SET paid_total = :p, due_total = :d WHERE id = :i",
                p=paid,
                d=due,
                i=inv_id,
            )
    except IntegrityError as e:
        if "invoices_idem" in str(e.orig):  # a concurrent retry with the same key won the race
            winner = _q(
                db,
                "SELECT id FROM invoices WHERE shop_id = :s AND idempotency_key = :k",
                s=ctx.id,
                k=body.idempotency_key,
            ).scalar_one()
            return receipt(db, actor, winner), True
        raise
    audit.record(
        db,
        actor,
        "invoice",
        inv_id,
        "create",
        None,
        {"number": number, "total": str(p.out.grand_total)},
    )
    return receipt(db, actor, inv_id), False


def _invoice_row(db: Session, actor: Actor, invoice_id: UUID) -> Any:
    row = _q(
        db,
        "SELECT * FROM invoices WHERE id = :i AND shop_id = :s",
        i=invoice_id,
        s=shop_id_of(actor),
    ).first()
    if not row:
        raise AppError("invoice.not_found", "This bill was not found.", 404)
    if actor.role == "salesperson" and row.created_by != actor.user_id:
        raise AppError("invoice.not_found", "This bill was not found.", 404)
    return row


def _reverse(db: Session, actor: Actor, inv: Any, reason: str) -> None:
    """Undo a bill's stock and payments (cancel, or before rewriting lines on edit)."""
    for ln in _q(
        db,
        "SELECT l.variant_id, l.qty, l.cost_price, p.track_stock FROM invoice_lines l"
        " LEFT JOIN product_variants v ON v.id = l.variant_id LEFT JOIN products p ON p.id = v.product_id"
        " WHERE l.invoice_id = :i",
        i=inv.id,
    ):
        if ln.variant_id and ln.track_stock:
            _move(
                db,
                actor,
                ln.variant_id,
                "sale",
                ln.qty,
                ln.cost_price,
                reason,
                ("invoice", str(inv.id)),
            )
    _q(
        db,
        "UPDATE payments SET status = 'reversed' WHERE applies_to_type = 'invoice' AND applies_to_id = :i AND status = 'confirmed'",
        i=inv.id,
    )


def _guard_change(actor: Actor, ctx: ShopCtx, inv: Any, *, editing: bool) -> None:
    if actor.role not in ("owner", "manager"):
        raise AppError("auth.forbidden", "Only an owner or manager can change a bill.", 403)
    if inv.status != "issued":
        raise AppError("invoice.cancelled", "This bill is already cancelled.", 409)
    if _today(ctx, inv.issued_at) != _today(ctx):
        raise AppError(
            "invoice.too_late",
            "Bills can only be changed on the day they were made. Use a return (credit note) instead.",
            409,
        )
    if editing and inv.handed_over_at:
        raise AppError(
            "invoice.handed_over",
            "This bill was already printed or shared. Cancel and make a new one instead.",
            409,
        )


def _no_returns(db: Session, inv: Any) -> None:
    if _q(
        db, "SELECT 1 FROM credit_notes WHERE original_invoice_id = :i LIMIT 1", i=inv.id
    ).first():
        raise AppError(
            "invoice.has_returns",
            "Items on this bill were returned, so it can't be changed or cancelled.",
            409,
        )


def cancel(db: Session, actor: Actor, invoice_id: UUID, reason: str) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    inv = _invoice_row(db, actor, invoice_id)
    _guard_change(actor, ctx, inv, editing=False)
    _no_returns(db, inv)
    _reverse(db, actor, inv, f"Cancelled {inv.number}")
    _q(
        db,
        "UPDATE invoices SET status = 'cancelled', cancel_reason = :r, cancelled_at = now(), cancelled_by = :u, due_total = 0"
        " WHERE id = :i",
        r=reason,
        u=actor.user_id,
        i=inv.id,
    )
    audit.record(
        db,
        actor,
        "invoice",
        inv.id,
        "cancel",
        {"number": inv.number, "total": str(inv.grand_total)},
        {"reason": reason},
    )
    return receipt(db, actor, inv.id)


def edit(db: Session, actor: Actor, invoice_id: UUID, body: CheckoutIn) -> dict[str, Any]:
    """Rewrite a bill that nobody has seen yet. Keeps its number and time; stock and payments are re-posted."""
    ctx = shop_ctx(db, actor)
    inv = _invoice_row(db, actor, invoice_id)
    _guard_change(actor, ctx, inv, editing=True)
    _no_returns(db, inv)
    p = price_cart(db, actor, ctx, body)
    paid = sum((pm.amount for pm in body.payments), ZERO)
    if paid < p.out.grand_total and not (body.customer and body.customer.phone):
        raise AppError(
            "invoice.due_needs_customer", "Add the customer's mobile number to keep money due.", 422
        )
    before = {"total": str(inv.grand_total)}
    _reverse(db, actor, inv, f"Edited {inv.number}")
    _q(db, "DELETE FROM invoice_lines WHERE invoice_id = :i", i=inv.id)
    customer_id = _customer(db, ctx, body, p.buyer_state)
    c = body.customer
    o = p.out
    _q(
        db,
        """UPDATE invoices SET doc_type = :dt, customer_id = :cid, buyer_name = :bn, buyer_phone = :bp, buyer_gstin = :bg,
              buyer_address = :ba, buyer_state_code = :bs, place_of_supply = :pos, supply_type = :st, delivery_mode = :dm,
              delivery_address = :da, is_b2b = :b2b, subtotal_gross = :sub, discount_type = :dtype, discount_value = :dval,
              discount_total = :dtot, taxable_total = :tax, cgst_total = :cg, sgst_total = :sg, igst_total = :ig,
              cess_total = :ce, round_off = :ro, grand_total = :gt, remarks = :rem, is_edited = true WHERE id = :i""",
        dt=p.doc_type,
        cid=customer_id,
        bn=c.name if c else None,
        bp=c.phone if c else None,
        bg=c.gstin if c else None,
        ba=c.address if c else None,
        bs=p.buyer_state,
        pos=p.place_of_supply,
        st=p.supply_type,
        dm=body.delivery_mode,
        da=body.delivery_address,
        b2b=bool(c and c.gstin),
        sub=o.subtotal_gross,
        dtype=body.discount_type,
        dval=body.discount_value,
        dtot=o.discount_total,
        tax=o.taxable_total,
        cg=o.cgst_total,
        sg=o.sgst_total,
        ig=o.igst_total,
        ce=o.cess_total,
        ro=o.round_off,
        gt=o.grand_total,
        rem=body.remarks,
        i=inv.id,
    )
    _write_lines_stock(db, actor, ctx, inv.id, inv.number, p)
    paid, due = _write_payments(db, actor, ctx, inv.id, customer_id, body.payments, o.grand_total)
    _q(
        db,
        "UPDATE invoices SET paid_total = :p, due_total = :d WHERE id = :i",
        p=paid,
        d=due,
        i=inv.id,
    )
    audit.record(db, actor, "invoice", inv.id, "edit", before, {"total": str(o.grand_total)})
    return receipt(db, actor, inv.id)


def mark_handed_over(db: Session, actor: Actor, invoice_id: UUID) -> None:
    inv = _invoice_row(db, actor, invoice_id)
    _q(
        db,
        "UPDATE invoices SET handed_over_at = coalesce(handed_over_at, now()) WHERE id = :i",
        i=inv.id,
    )


# --- reading ---


def _mask(phone: str | None) -> str | None:
    return f"{phone[:2]}xxxxx{phone[-3:]}" if phone else None


def receipt(
    db: Session, actor: Actor | None, invoice_id: UUID, *, public: bool = False
) -> dict[str, Any]:
    """Structured receipt every client lays out the same way (docs/07-pos-billing.md §7)."""
    inv = (
        _invoice_row(db, actor, invoice_id)
        if actor
        else _q(db, "SELECT * FROM invoices WHERE id = :i", i=invoice_id).one()
    )
    shop = _q(
        db,
        "SELECT s.*, t.gst_scheme, t.gstin, t.legal_name, t.trade_name FROM shops s"
        " JOIN shop_tax_profiles t ON t.shop_id = s.id WHERE s.id = :s",
        s=inv.shop_id,
    ).one()
    lines = _q(
        db, "SELECT * FROM invoice_lines WHERE invoice_id = :i ORDER BY line_no", i=inv.id
    ).all()
    pays = _q(
        db,
        "SELECT method, amount, reference, status FROM payments WHERE applies_to_type = 'invoice' AND applies_to_id = :i"
        " ORDER BY occurred_at",
        i=inv.id,
    ).all()
    summary: dict[Decimal, dict[str, Decimal]] = {}
    for ln in lines:
        s = summary.setdefault(
            ln.tax_rate, {"taxable": ZERO, "cgst": ZERO, "sgst": ZERO, "igst": ZERO, "cess": ZERO}
        )
        for k, v in (
            ("taxable", ln.taxable),
            ("cgst", ln.cgst),
            ("sgst", ln.sgst),
            ("igst", ln.igst),
            ("cess", ln.cess),
        ):
            s[k] += v
    address = ", ".join(
        x for x in (shop.address_line1, shop.address_line2, shop.city, shop.pincode) if x
    )
    upi_due = None
    if shop.upi_vpa and inv.due_total > 0 and inv.status == "issued":
        upi_due = f"upi://pay?pa={shop.upi_vpa}&pn={(shop.upi_payee_name or shop.name).replace(' ', '%20')}&am={inv.due_total}&tn={inv.number}&cu=INR"
    return {
        "id": inv.id,
        "number": inv.number,
        "doc_type": inv.doc_type,
        "title": DOC_TITLES[inv.doc_type],
        "composition_note": COMPOSITION_NOTE if inv.scheme == "composition" else None,
        "status": inv.status,
        "cancel_reason": inv.cancel_reason,
        "is_edited": inv.is_edited,
        "issued_at": inv.issued_at,
        "handed_over": inv.handed_over_at is not None,
        "customer_id": None if public else inv.customer_id,
        "shop": {
            "name": shop.trade_name or shop.name,
            "legal_name": shop.legal_name,
            "address": address,
            "state": f"{STATES[shop.state_code]} ({shop.state_code})",
            "phone": shop.phone,
            "gstin": shop.gstin,
            "logo_url": media.url(shop.logo_path),
            "upi": shop.upi_vpa,
        },
        "buyer": {
            "name": inv.buyer_name,
            "phone": _mask(inv.buyer_phone) if public else inv.buyer_phone,
            "gstin": inv.buyer_gstin,
            "address": inv.buyer_address,
        }
        if (inv.buyer_name or inv.buyer_phone or inv.buyer_gstin)
        else None,
        "place_of_supply": f"{STATES[inv.place_of_supply]} ({inv.place_of_supply})",
        "supply_type": inv.supply_type,
        "state_tax_label": "UTGST" if shop.state_code in UTGST_STATES else "SGST",
        "reverse_charge": "No",
        "delivery_address": inv.delivery_address,
        "lines": [
            {
                "id": ln.id,
                "returned_qty": ln.returned_qty,
                "name": ln.name,
                "variant_name": ln.variant_name,
                "hsn": ln.hsn_code,
                "qty": ln.qty,
                "unit": ln.unit_code,
                "unit_price": ln.unit_price,
                "discount": ln.line_discount + ln.invoice_discount_share,
                "taxable": ln.taxable,
                "tax_rate": ln.tax_rate,
                "line_total": ln.line_total,
            }
            for ln in lines
        ],
        "tax_summary": [
            {"rate": r, **v} for r, v in sorted(summary.items()) if inv.scheme == "regular"
        ],
        "totals": {
            k: getattr(inv, k)
            for k in (
                "subtotal_gross",
                "discount_total",
                "taxable_total",
                "cgst_total",
                "sgst_total",
                "igst_total",
                "cess_total",
                "round_off",
                "grand_total",
                "paid_total",
                "due_total",
            )
        },
        "amount_in_words": amount_in_words(inv.grand_total),
        "payments": [
            {"method": p.method, "amount": p.amount, "reference": p.reference}
            for p in pays
            if p.status == "confirmed"
        ],
        "remarks": inv.remarks,
        "created_by_name": inv.created_by_name,
        "footer": shop.settings.get("receipt_footer") or "Thank you! Visit again.",
        "public_url": f"{get_settings().public_web_url}/i/{inv.public_token}",
        "upi_due_uri": upi_due,
    }


def list_invoices(
    db: Session,
    actor: Actor,
    *,
    frm: Any,
    to: Any,
    status: str | None,
    q: str | None,
    has_due: bool,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    where = ["i.shop_id = :s"]
    params: dict[str, Any] = {"s": ctx.id, "tz": str(ctx.tz), "lim": limit, "off": offset}
    if actor.role == "salesperson":  # own bills, today only
        where.append(
            "i.created_by = :u AND (i.issued_at AT TIME ZONE :tz)::date = (now() AT TIME ZONE :tz)::date"
        )
        params["u"] = actor.user_id
    if frm:
        where.append("(i.issued_at AT TIME ZONE :tz)::date >= :frm")
        params["frm"] = frm
    if to:
        where.append("(i.issued_at AT TIME ZONE :tz)::date <= :to")
        params["to"] = to
    if status:
        where.append("i.status = :st")
        params["st"] = status
    if has_due:
        where.append("i.due_total > 0 AND i.status = 'issued'")
    if q:
        where.append("(i.number ILIKE :q OR i.buyer_name ILIKE :q OR i.buyer_phone LIKE :q)")
        params["q"] = f"%{q.strip()}%"
    cond = " AND ".join(where)
    agg = _q(
        db,
        f"SELECT count(*) AS n, coalesce(sum(grand_total) FILTER (WHERE status = 'issued'), 0) AS total FROM invoices i WHERE {cond}",
        **params,
    ).one()
    rows = _q(
        db,
        f"""
        SELECT i.id, i.number, i.doc_type, i.issued_at, i.buyer_name, i.buyer_phone, i.grand_total, i.paid_total, i.due_total,
          i.status, i.created_by_name,
          coalesce((SELECT array_agg(DISTINCT p.method) FROM payments p WHERE p.applies_to_type = 'invoice'
                    AND p.applies_to_id = i.id AND p.status = 'confirmed'), '{{}}') AS methods
        FROM invoices i WHERE {cond} ORDER BY i.issued_at DESC LIMIT :lim OFFSET :off""",
        **params,
    ).all()
    nxt = offset + limit
    return {
        "items": [r._asdict() for r in rows],
        "total": agg.n,
        "sales_total": agg.total,
        "next_cursor": str(nxt) if nxt < agg.n else None,
    }


def public_receipt(db: Session, token: str) -> dict[str, Any]:
    inv = _q(db, "SELECT id FROM invoices WHERE public_token = :t", t=token).scalar()
    if not inv:
        raise AppError("invoice.not_found", "This bill link is not valid.", 404)
    return receipt(db, None, inv, public=True)


# --- held bills ---


def list_held(db: Session, actor: Actor) -> list[Any]:
    return list(
        _q(
            db,
            "SELECT id, label, payload, created_by_name, created_at FROM held_bills WHERE shop_id = :s"
            " ORDER BY created_at DESC",
            s=shop_id_of(actor),
        )
    )


def hold(db: Session, actor: Actor, label: str, payload: dict[str, Any]) -> Any:
    import json

    return _q(
        db,
        "INSERT INTO held_bills (shop_id, created_by, created_by_name, label, payload) VALUES (:s, :u,"
        " (SELECT full_name FROM users WHERE id = :u), :l, CAST(:p AS jsonb))"
        " RETURNING id, label, payload, created_by_name, created_at",
        s=shop_id_of(actor),
        u=actor.user_id,
        l=label,
        p=json.dumps(payload),
    ).one()


def unhold(db: Session, actor: Actor, held_id: UUID) -> None:
    _q(db, "DELETE FROM held_bills WHERE id = :i AND shop_id = :s", i=held_id, s=shop_id_of(actor))

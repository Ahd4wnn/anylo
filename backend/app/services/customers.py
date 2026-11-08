"""Customer profiles, the khata ledger and due collections (docs/04-data-model.md §4, docs/07-pos-billing.md §5)."""

import uuid
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Actor
from app.errors import AppError
from app.schemas.backoffice import CollectIn, CustomerIn
from app.services import audit
from app.services.gst.india import fy_label
from app.services.sales import _pin_ok, _q, _today, next_number, shop_ctx
from app.services.shop import shop_id_of

ZERO = Decimal("0")
COLS = "c.id, c.name, c.phone, c.email, c.gstin, c.billing_address, c.state_code, c.credit_limit, c.opening_balance, c.notes, c.tags"


def _row(db: Session, actor: Actor, customer_id: UUID) -> Any:
    row = _q(
        db,
        f"SELECT {COLS}, b.balance FROM customers c JOIN customer_balances b ON b.customer_id = c.id"
        " WHERE c.id = :i AND c.shop_id = :s AND c.deleted_at IS NULL",
        i=customer_id,
        s=shop_id_of(actor),
    ).first()
    if not row:
        raise AppError("customer.not_found", "This customer was not found.", 404)
    return row


def balance_of(db: Session, customer_id: UUID) -> Decimal:
    b = _q(
        db, "SELECT balance FROM customer_balances WHERE customer_id = :i", i=customer_id
    ).scalar()
    return b if b is not None else ZERO


def list_customers(
    db: Session, actor: Actor, q: str | None, has_due: bool, limit: int, offset: int
) -> dict[str, Any]:
    where = "c.shop_id = :s AND c.deleted_at IS NULL"
    p: dict[str, Any] = {"s": shop_id_of(actor), "lim": limit, "off": offset}
    if q:
        where += " AND (c.name ILIKE :like OR c.phone LIKE :pre OR c.gstin ILIKE :like)"
        p |= {"like": f"%{q.strip()}%", "pre": f"{q.strip()}%"}
    if has_due:
        where += " AND b.balance > 0"
    base = f"FROM customers c JOIN customer_balances b ON b.customer_id = c.id WHERE {where}"
    rows = _q(
        db,
        f"SELECT {COLS}, b.balance,"
        " (SELECT max(issued_at) FROM invoices i WHERE i.customer_id = c.id AND i.status = 'issued') AS last_visit,"
        " (SELECT count(*) FROM invoices i WHERE i.customer_id = c.id AND i.status = 'issued') AS bills"
        f" {base} ORDER BY b.balance DESC, last_visit DESC NULLS LAST LIMIT :lim OFFSET :off",
        **p,
    ).mappings()
    agg = _q(
        db,
        f"SELECT count(*) AS n, coalesce(sum(greatest(b.balance, 0)), 0) AS due {base}",
        **{k: v for k, v in p.items() if k not in ("lim", "off")},
    ).one()
    return {
        "items": [dict(r) for r in rows],
        "total": agg.n,
        "due_total": agg.due,
        "next_cursor": str(offset + limit) if offset + limit < agg.n else None,
    }


def lookup(db: Session, actor: Actor, phone: str) -> list[dict[str, Any]]:
    """Returning customers by the first digits of their mobile, so nobody is asked for the full number twice."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 5:
        return []
    rows = _q(
        db,
        f"SELECT {COLS}, b.balance FROM customers c JOIN customer_balances b ON b.customer_id = c.id"
        " WHERE c.shop_id = :s AND c.deleted_at IS NULL AND c.phone LIKE :pre"
        " ORDER BY (SELECT max(issued_at) FROM invoices i WHERE i.customer_id = c.id) DESC NULLS LAST LIMIT 8",
        s=shop_id_of(actor),
        pre=f"{digits}%",
    ).mappings()
    return [dict(r) for r in rows]


def get(db: Session, actor: Actor, customer_id: UUID) -> dict[str, Any]:
    r = _row(db, actor, customer_id)
    stats = _q(
        db,
        "SELECT count(*) AS bills, coalesce(sum(grand_total), 0) AS spent, max(issued_at) AS last_visit,"
        " min(issued_at) AS first_visit FROM invoices WHERE customer_id = :i AND status = 'issued'",
        i=customer_id,
    ).one()
    return dict(r._mapping) | dict(stats._mapping)


def _fields(data: CustomerIn) -> dict[str, Any]:
    return {
        "n": data.name,
        "p": data.phone,
        "e": data.email,
        "g": data.gstin,
        "a": data.billing_address,
        "st": data.state_code,
        "cl": data.credit_limit,
        "ob": data.opening_balance,
        "no": data.notes,
        "t": data.tags,
    }


def create(db: Session, actor: Actor, data: CustomerIn) -> dict[str, Any]:
    if not (data.name or data.phone):
        raise AppError("customer.empty", "Add a name or a mobile number.", 422)
    sid = shop_id_of(actor)
    if data.phone:
        old = _q(
            db,
            "SELECT id, deleted_at FROM customers WHERE shop_id = :s AND phone = :p",
            s=sid,
            p=data.phone,
        ).first()
        if old and old.deleted_at is None:
            raise AppError(
                "customer.phone_taken", "A customer with this mobile number already exists.", 409
            )
        if (
            old
        ):  # same person coming back after being removed: restore rather than collide on the phone
            _q(db, "UPDATE customers SET deleted_at = NULL WHERE id = :i", i=old.id)
            return update(db, actor, old.id, data)
    try:
        cid = _q(
            db,
            "INSERT INTO customers (shop_id, name, phone, email, gstin, billing_address, state_code, credit_limit,"
            " opening_balance, notes, tags) VALUES (:s, :n, :p, :e, :g, :a, :st, :cl, :ob, :no, :t) RETURNING id",
            s=sid,
            **_fields(data),
        ).scalar_one()
    except IntegrityError:
        raise AppError(
            "customer.phone_taken", "A customer with this mobile number already exists.", 409
        ) from None
    audit.record(
        db, actor, "customer", cid, "create", None, {"name": data.name, "phone": data.phone}
    )
    return get(db, actor, cid)


def update(db: Session, actor: Actor, customer_id: UUID, data: CustomerIn) -> dict[str, Any]:
    before = _row(db, actor, customer_id)
    try:
        _q(
            db,
            "UPDATE customers SET name = :n, phone = :p, email = :e, gstin = :g, billing_address = :a, state_code = :st,"
            " credit_limit = :cl, opening_balance = :ob, notes = :no, tags = :t WHERE id = :i",
            i=customer_id,
            **_fields(data),
        )
    except IntegrityError:
        raise AppError(
            "customer.phone_taken", "A customer with this mobile number already exists.", 409
        ) from None
    if before.opening_balance != data.opening_balance or before.credit_limit != data.credit_limit:
        audit.record(
            db,
            actor,
            "customer",
            customer_id,
            "update",
            {"opening_balance": before.opening_balance, "credit_limit": before.credit_limit},
            {"opening_balance": data.opening_balance, "credit_limit": data.credit_limit},
        )
    return get(db, actor, customer_id)


def delete(db: Session, actor: Actor, customer_id: UUID) -> None:
    r = _row(db, actor, customer_id)
    if r.balance != 0:
        raise AppError(
            "customer.has_balance", "Settle this customer's balance before removing them.", 409
        )
    _q(db, "UPDATE customers SET deleted_at = now() WHERE id = :i", i=customer_id)
    audit.record(
        db, actor, "customer", customer_id, "delete", {"name": r.name, "phone": r.phone}, None
    )


def ledger(db: Session, actor: Actor, customer_id: UUID) -> dict[str, Any]:
    """Statement: every bill (debit), payment and return (credit) and refund (debit), with a running balance."""
    c = _row(db, actor, customer_id)
    rows = _q(
        db,
        """
        SELECT issued_at AS at, 'bill' AS kind, number AS ref, id AS ref_id, grand_total AS debit, 0 AS credit
          FROM invoices WHERE customer_id = :c AND status = 'issued'
        UNION ALL
        SELECT p.occurred_at, CASE WHEN p.batch_id IS NULL THEN 'paid_at_bill' ELSE 'payment' END,
               coalesce(p.receipt_no, i.number), p.applies_to_id, 0, p.amount
          FROM payments p LEFT JOIN invoices i ON i.id = p.applies_to_id AND p.applies_to_type = 'invoice'
          WHERE p.party_type = 'customer' AND p.party_id = :c AND p.direction = 'in' AND p.status = 'confirmed'
            AND p.method <> 'store_credit'
        UNION ALL
        SELECT issued_at, 'return', number, id, 0, grand_total FROM credit_notes WHERE customer_id = :c
        UNION ALL
        SELECT p.occurred_at, 'refund', n.number, p.applies_to_id, p.amount, 0
          FROM payments p LEFT JOIN credit_notes n ON n.id = p.applies_to_id
          WHERE p.party_type = 'customer' AND p.party_id = :c AND p.direction = 'out' AND p.status = 'confirmed'
        ORDER BY 1, 2""",
        c=customer_id,
    ).mappings()
    running = c.opening_balance
    entries = []
    for r in rows:
        running += r["debit"] - r["credit"]
        entries.append(dict(r) | {"balance": running})
    return {
        "customer": dict(c._mapping),
        "opening_balance": c.opening_balance,
        "entries": entries,
        "balance": c.balance,
    }


def apply_to_invoice(db: Session, invoice_id: UUID, amount: Decimal) -> None:
    _q(
        db,
        "UPDATE invoices SET paid_total = paid_total + :a, due_total = greatest(due_total - :a, 0) WHERE id = :i",
        a=amount,
        i=invoice_id,
    )


def _receipt(db: Session, actor: Actor, batch_id: UUID) -> dict[str, Any]:
    rows = _q(
        db,
        "SELECT p.amount, p.method, p.status, p.receipt_no, p.occurred_at, p.party_id, p.reference, i.number"
        " FROM payments p LEFT JOIN invoices i ON i.id = p.applies_to_id AND p.applies_to_type = 'invoice'"
        " WHERE p.batch_id = :b ORDER BY i.issued_at NULLS LAST",
        b=batch_id,
    ).all()
    first = rows[0]
    return {
        "batch_id": batch_id,
        "receipt_no": first.receipt_no,
        "amount": sum((r.amount for r in rows), ZERO),
        "method": first.method,
        "reference": first.reference,
        "status": first.status,
        "occurred_at": first.occurred_at,
        "allocations": [{"invoice": r.number, "amount": r.amount} for r in rows],
        "customer_id": first.party_id,
        "balance_after": balance_of(db, first.party_id),
    }


def collect(
    db: Session, actor: Actor, customer_id: UUID, body: CollectIn
) -> tuple[dict[str, Any], bool]:
    """Collect against the oldest dues first (FIFO). A salesperson's collection waits for a manager (or their PIN)."""
    ctx = shop_ctx(db, actor)
    dup = _q(
        db,
        "SELECT batch_id FROM payments WHERE shop_id = :s AND idempotency_key = :k",
        s=ctx.id,
        k=body.idempotency_key,
    ).scalar()
    if dup:
        return _receipt(db, actor, dup), True
    c = _row(db, actor, customer_id)
    if body.amount > c.balance:
        raise AppError(
            "collection.more_than_due",
            f"This customer owes ₹{max(c.balance, ZERO):,.2f}. Collect that amount or less.",
            422,
        )
    confirmed = actor.role in ("owner", "manager") or _pin_ok(db, ctx, body.approval_pin)
    status = "confirmed" if confirmed else "pending_approval"
    receipt_no, _, _ = next_number(db, ctx, fy_label(_today(ctx)), "receipt", "RCPT")
    batch = uuid.uuid4()
    left = body.amount
    allocations: list[tuple[UUID | None, Decimal]] = []
    for inv in _q(
        db,
        "SELECT id, due_total FROM invoices WHERE customer_id = :c AND status = 'issued' AND due_total > 0"
        " ORDER BY issued_at FOR UPDATE",
        c=customer_id,
    ):
        if left <= 0:
            break
        part = min(left, inv.due_total)
        allocations.append((inv.id, part))
        left -= part
    if left > 0:  # opening balance or older dues without a bill
        allocations.append((None, left))
    for i, (inv_id, amount) in enumerate(allocations):
        _q(
            db,
            "INSERT INTO payments (shop_id, direction, method, amount, reference, party_type, party_id, applies_to_type,"
            " applies_to_id, status, received_by, batch_id, receipt_no, note, idempotency_key, approved_by, approved_at)"
            " VALUES (:s, 'in', :m, :a, :r, 'customer', :c, :at, :ai, :st, :u, :b, :rn, :no, :k, :ab,"
            " CASE WHEN CAST(:ab AS uuid) IS NULL THEN NULL ELSE now() END)",
            s=ctx.id,
            m=body.method,
            a=amount,
            r=body.reference,
            c=customer_id,
            at="invoice" if inv_id else None,
            ai=inv_id,
            st=status,
            u=actor.user_id,
            b=batch,
            rn=receipt_no,
            no=body.note,
            k=body.idempotency_key if i == 0 else None,
            ab=actor.user_id if confirmed else None,
        )
        if confirmed and inv_id:
            apply_to_invoice(db, inv_id, amount)
    if not confirmed:
        from app.services import (
            approvals,  # local import: approvals dispatches back into this module
        )

        approvals.request(
            db,
            actor,
            "collection",
            batch,
            f"Collected ₹{body.amount:,.2f} ({body.method.upper()}) from {c.name or c.phone}",
            body.amount,
        )
    audit.record(
        db, actor, "payment", batch, "collect", None, {"amount": str(body.amount), "status": status}
    )
    return _receipt(db, actor, batch), False


def decide_collection(db: Session, actor: Actor, batch_id: UUID, approve: bool) -> None:
    rows = _q(
        db,
        "UPDATE payments SET status = :st, approved_by = :u, approved_at = now()"
        " WHERE batch_id = :b AND status = 'pending_approval' RETURNING applies_to_id, amount",
        st="confirmed" if approve else "rejected",
        u=actor.user_id,
        b=batch_id,
    ).all()
    if approve:
        for r in rows:
            if r.applies_to_id:
                apply_to_invoice(db, r.applies_to_id, r.amount)

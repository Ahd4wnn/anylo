"""Money out and cash: expenses, borrowings, cash today, day close and the day book (docs/04 §6, docs/07 §8).

Every rupee that moves is a `payments` row, so cash figures come from one table and can't drift.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.database import Actor
from app.errors import AppError
from app.schemas.backoffice import BorrowingIn, CloseIn, ExpenseIn, RepayIn
from app.services import audit
from app.services.sales import ShopCtx, _q, _today, shop_ctx
from app.services.shop import shop_id_of

ZERO = Decimal("0")
SYSTEM_CATEGORIES = (
    "Rent",
    "Electricity",
    "Salaries",
    "Transport",
    "Repairs",
    "Packaging",
    "Marketing",
    "Misc",
)


def _at(ctx: ShopCtx, day: date) -> datetime:
    """When a back-dated money row happened: now if today, else midday of that day in the shop's timezone."""
    if day == _today(ctx):
        return datetime.now(UTC)
    return datetime.combine(day, time(12), ctx.tz)


def _bounds(ctx: ShopCtx, start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time(0), ctx.tz), datetime.combine(
        end + timedelta(days=1), time(0), ctx.tz
    )


def _pay(
    db: Session,
    actor: Actor,
    ctx: ShopCtx,
    direction: str,
    method: str,
    amount: Decimal,
    applies: tuple[str, UUID],
    at: datetime,
    party: tuple[str, UUID] | None = None,
    note: str | None = None,
) -> None:
    _q(
        db,
        "INSERT INTO payments (shop_id, direction, method, amount, party_type, party_id, applies_to_type, applies_to_id,"
        " received_by, occurred_at, note) VALUES (:s, :d, :m, :a, :pt, :pi, :at, :ai, :u, :o, :n)",
        s=ctx.id,
        d=direction,
        m=method,
        a=amount,
        pt=party[0] if party else None,
        pi=party[1] if party else None,
        at=applies[0],
        ai=applies[1],
        u=actor.user_id,
        o=at,
        n=note,
    )


def _reverse(db: Session, kind: str, ref_id: UUID) -> None:
    _q(
        db,
        "UPDATE payments SET status = 'reversed' WHERE applies_to_type = :k AND applies_to_id = :i AND status = 'confirmed'",
        k=kind,
        i=ref_id,
    )


# --- expenses ---


def categories(db: Session, actor: Actor) -> list[dict[str, Any]]:
    sid = shop_id_of(actor)
    for name in SYSTEM_CATEGORIES:
        _q(
            db,
            "INSERT INTO expense_categories (shop_id, name, is_system) VALUES (:s, :n, true) ON CONFLICT DO NOTHING",
            s=sid,
            n=name,
        )
    rows = _q(
        db,
        "SELECT id, name, is_system FROM expense_categories WHERE shop_id = :s ORDER BY is_system DESC, name",
        s=sid,
    )
    return [dict(r) for r in rows.mappings()]


def _category(db: Session, actor: Actor, data: ExpenseIn) -> tuple[UUID, str]:
    sid = shop_id_of(actor)
    if data.category_id:
        r = _q(
            db,
            "SELECT id, name FROM expense_categories WHERE id = :i AND shop_id = :s",
            i=data.category_id,
            s=sid,
        ).first()
        if r:
            return r.id, r.name
    name = (data.category_name or "Misc").strip() or "Misc"
    r = _q(
        db,
        "INSERT INTO expense_categories (shop_id, name) VALUES (:s, :n)"
        " ON CONFLICT (shop_id, lower(name)) DO UPDATE SET name = expense_categories.name RETURNING id, name",
        s=sid,
        n=name,
    ).one()
    return r.id, r.name


def list_expenses(
    db: Session, actor: Actor, start: date | None, end: date | None, category_id: UUID | None
) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    end = end or _today(ctx)
    start = start or end.replace(day=1)
    p: dict[str, Any] = {"s": ctx.id, "a": start, "b": end}
    where = "shop_id = :s AND deleted_at IS NULL AND occurred_on BETWEEN :a AND :b"
    if category_id:
        where += " AND category_id = :c"
        p["c"] = category_id
    rows = _q(
        db,
        "SELECT id, category_id, category_name, amount, method, gst_amount, note, occurred_on, created_by_name, created_at"
        f" FROM expenses WHERE {where} ORDER BY occurred_on DESC, created_at DESC",
        **p,
    ).mappings()
    items = [dict(r) for r in rows]
    by_cat: dict[str, Decimal] = {}
    for e in items:
        by_cat[e["category_name"]] = by_cat.get(e["category_name"], ZERO) + e["amount"]
    return {
        "items": items,
        "total": sum((e["amount"] for e in items), ZERO),
        "by_category": [
            {"name": k, "amount": v} for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])
        ],
        "from": start,
        "to": end,
    }


def create_expense(db: Session, actor: Actor, data: ExpenseIn) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    day = data.occurred_on or _today(ctx)
    if day > _today(ctx):
        raise AppError("expense.future", "An expense can't be dated in the future.", 422)
    cat_id, cat_name = _category(db, actor, data)
    eid: UUID = _q(
        db,
        "INSERT INTO expenses (shop_id, category_id, category_name, amount, method, gst_amount, note, occurred_on, created_by,"
        " created_by_name) VALUES (:s, :c, :cn, :a, :m, :g, :n, :d, :u, (SELECT full_name FROM users WHERE id = :u)) RETURNING id",
        s=ctx.id,
        c=cat_id,
        cn=cat_name,
        a=data.amount,
        m=data.method,
        g=data.gst_amount,
        n=data.note,
        d=day,
        u=actor.user_id,
    ).scalar_one()
    _pay(
        db,
        actor,
        ctx,
        "out",
        data.method,
        data.amount,
        ("expense", eid),
        _at(ctx, day),
        note=cat_name,
    )
    audit.record(
        db,
        actor,
        "expense",
        eid,
        "create",
        None,
        {"amount": str(data.amount), "category": cat_name},
    )
    return _expense(db, eid)


def _expense(db: Session, eid: UUID) -> dict[str, Any]:
    return dict(_q(db, "SELECT * FROM expenses WHERE id = :i", i=eid).mappings().one())


def update_expense(db: Session, actor: Actor, eid: UUID, data: ExpenseIn) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    before = _q(
        db,
        "SELECT * FROM expenses WHERE id = :i AND shop_id = :s AND deleted_at IS NULL",
        i=eid,
        s=ctx.id,
    ).first()
    if not before:
        raise AppError("expense.not_found", "This expense was not found.", 404)
    day = data.occurred_on or before.occurred_on
    cat_id, cat_name = _category(db, actor, data)
    _q(
        db,
        "UPDATE expenses SET category_id = :c, category_name = :cn, amount = :a, method = :m, gst_amount = :g, note = :n,"
        " occurred_on = :d WHERE id = :i",
        c=cat_id,
        cn=cat_name,
        a=data.amount,
        m=data.method,
        g=data.gst_amount,
        n=data.note,
        d=day,
        i=eid,
    )
    _reverse(db, "expense", eid)
    _pay(
        db,
        actor,
        ctx,
        "out",
        data.method,
        data.amount,
        ("expense", eid),
        _at(ctx, day),
        note=cat_name,
    )
    audit.record(
        db,
        actor,
        "expense",
        eid,
        "update",
        {"amount": str(before.amount), "method": before.method, "category": before.category_name},
        {"amount": str(data.amount), "method": data.method, "category": cat_name},
    )
    return _expense(db, eid)


def delete_expense(db: Session, actor: Actor, eid: UUID) -> None:
    r = _q(
        db,
        "UPDATE expenses SET deleted_at = now() WHERE id = :i AND shop_id = :s AND deleted_at IS NULL RETURNING amount, category_name",
        i=eid,
        s=shop_id_of(actor),
    ).first()
    if not r:
        raise AppError("expense.not_found", "This expense was not found.", 404)
    _reverse(db, "expense", eid)
    audit.record(
        db,
        actor,
        "expense",
        eid,
        "delete",
        {"amount": str(r.amount), "category": r.category_name},
        None,
    )


# --- borrowings ---

BORROW_COLS = """b.id, b.lender_name, b.lender_phone, b.principal, b.received_method, b.interest_note, b.borrowed_on, b.status,
  coalesce((SELECT sum(p.amount) FROM payments p WHERE p.applies_to_type = 'borrowing' AND p.applies_to_id = b.id
            AND p.direction = 'out' AND p.status = 'confirmed'), 0) AS repaid"""


def list_borrowings(db: Session, actor: Actor) -> dict[str, Any]:
    rows = [
        dict(r) | {"outstanding": r["principal"] - r["repaid"]}
        for r in _q(
            db,
            f"SELECT {BORROW_COLS} FROM borrowings b WHERE b.shop_id = :s AND b.deleted_at IS NULL"
            " ORDER BY b.status, b.borrowed_on DESC",
            s=shop_id_of(actor),
        ).mappings()
    ]
    return {"items": rows, "outstanding": sum((r["outstanding"] for r in rows), ZERO)}


def _borrowing(db: Session, actor: Actor, bid: UUID) -> dict[str, Any]:
    r = (
        _q(
            db,
            f"SELECT {BORROW_COLS} FROM borrowings b WHERE b.id = :i AND b.shop_id = :s AND b.deleted_at IS NULL",
            i=bid,
            s=shop_id_of(actor),
        )
        .mappings()
        .first()
    )
    if not r:
        raise AppError("borrowing.not_found", "This loan was not found.", 404)
    return dict(r) | {"outstanding": r["principal"] - r["repaid"]}


def create_borrowing(db: Session, actor: Actor, data: BorrowingIn) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    day = data.borrowed_on or _today(ctx)
    bid: UUID = _q(
        db,
        "INSERT INTO borrowings (shop_id, lender_name, lender_phone, principal, received_method, interest_note, borrowed_on,"
        " created_by) VALUES (:s, :n, :p, :a, :m, :i, :d, :u) RETURNING id",
        s=ctx.id,
        n=data.lender_name,
        p=data.lender_phone,
        a=data.principal,
        m=data.received_method,
        i=data.interest_note,
        d=day,
        u=actor.user_id,
    ).scalar_one()
    _pay(
        db,
        actor,
        ctx,
        "in",
        data.received_method,
        data.principal,
        ("borrowing", bid),
        _at(ctx, day),
        ("lender", bid),
    )
    audit.record(
        db,
        actor,
        "borrowing",
        bid,
        "create",
        None,
        {"lender": data.lender_name, "amount": str(data.principal)},
    )
    return _borrowing(db, actor, bid)


def repay(db: Session, actor: Actor, bid: UUID, data: RepayIn) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    b = _borrowing(db, actor, bid)
    if data.amount > b["outstanding"]:
        raise AppError("borrowing.overpay", f"Only ₹{b['outstanding']:,.2f} is left to repay.", 422)
    _pay(
        db,
        actor,
        ctx,
        "out",
        data.method,
        data.amount,
        ("borrowing", bid),
        datetime.now(UTC),
        ("lender", bid),
        data.note,
    )
    if data.amount == b["outstanding"]:
        _q(db, "UPDATE borrowings SET status = 'closed' WHERE id = :i", i=bid)
    audit.record(db, actor, "borrowing", bid, "repay", None, {"amount": str(data.amount)})
    return _borrowing(db, actor, bid)


def delete_borrowing(db: Session, actor: Actor, bid: UUID) -> None:
    b = _borrowing(db, actor, bid)
    _q(db, "UPDATE borrowings SET deleted_at = now() WHERE id = :i", i=bid)
    _reverse(db, "borrowing", bid)
    audit.record(
        db,
        actor,
        "borrowing",
        bid,
        "delete",
        {"lender": b["lender_name"], "principal": str(b["principal"])},
        None,
    )


# --- cash ---

LABELS = {
    ("in", "invoice"): "Sales and collections",
    ("in", None): "Due collections",
    ("in", "borrowing"): "Money borrowed",
    ("out", "expense"): "Expenses",
    ("out", "labour_payment"): "Wages",
    ("out", "borrowing"): "Loan repayments",
    ("out", "credit_note"): "Refunds",
}


def _net_cash(db: Session, ctx: ShopCtx, start: datetime, end: datetime) -> list[Any]:
    return list(
        _q(
            db,
            "SELECT direction, applies_to_type, sum(amount) AS amount FROM payments WHERE shop_id = :s AND method = 'cash'"
            " AND status = 'confirmed' AND occurred_at >= :a AND occurred_at < :b GROUP BY 1, 2",
            s=ctx.id,
            a=start,
            b=end,
        )
    )


def _sum(rows: list[Any], direction: str) -> Decimal:
    return sum((r.amount for r in rows if r.direction == direction), ZERO)


def _opening(db: Session, ctx: ShopCtx, day: date) -> Decimal:
    """Last counted cash before `day`, plus any cash that moved on unclosed days since then."""
    last = _q(
        db,
        "SELECT business_date, counted_cash FROM day_closes WHERE shop_id = :s AND status <> 'rejected' AND business_date < :d"
        " ORDER BY business_date DESC LIMIT 1",
        s=ctx.id,
        d=day,
    ).first()
    since = (
        datetime.combine(last.business_date + timedelta(days=1), time(0), ctx.tz)
        if last
        else datetime(2000, 1, 1, tzinfo=UTC)
    )
    rows = _net_cash(db, ctx, since, datetime.combine(day, time(0), ctx.tz))
    return (last.counted_cash if last else ZERO) + _sum(rows, "in") - _sum(rows, "out")


def cash_day(db: Session, actor: Actor, day: date | None = None) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    day = day or _today(ctx)
    rows = _net_cash(db, ctx, *_bounds(ctx, day, day))
    opening = _opening(db, ctx, day)
    cash_in, cash_out = _sum(rows, "in"), _sum(rows, "out")
    close = (
        _q(
            db,
            "SELECT id, counted_cash, difference, status, note, closed_by_name, created_at FROM day_closes"
            " WHERE shop_id = :s AND business_date = :d AND status <> 'rejected'",
            s=ctx.id,
            d=day,
        )
        .mappings()
        .first()
    )
    pending = _q(
        db,
        "SELECT coalesce(sum(amount), 0) FROM payments WHERE shop_id = :s AND method = 'cash' AND status = 'pending_approval'",
        s=ctx.id,
    ).scalar()
    return {
        "date": day,
        "opening_cash": opening,
        "cash_in": cash_in,
        "cash_out": cash_out,
        "expected_cash": opening + cash_in - cash_out,
        "breakdown": [
            {
                "direction": r.direction,
                "label": LABELS.get((r.direction, r.applies_to_type), "Other"),
                "amount": r.amount,
            }
            for r in sorted(rows, key=lambda r: (r.direction, -r.amount))
        ],
        "pending_cash": pending,
        "close": dict(close) if close else None,
    }


def close_day(db: Session, actor: Actor, data: CloseIn) -> dict[str, Any]:
    t = cash_day(db, actor)
    if t["close"]:
        raise AppError("cash.already_closed", "Today is already closed.", 409)
    confirmed = actor.role in ("owner", "manager")
    cid: UUID = _q(
        db,
        "INSERT INTO day_closes (shop_id, business_date, opening_cash, cash_in, cash_out, expected_cash, counted_cash,"
        " difference, note, status, closed_by, closed_by_name, confirmed_by)"
        " VALUES (:s, :d, :o, :i, :out, :e, :c, :diff, :n, :st, :u, (SELECT full_name FROM users WHERE id = :u), :cb) RETURNING id",
        s=shop_id_of(actor),
        d=t["date"],
        o=t["opening_cash"],
        i=t["cash_in"],
        out=t["cash_out"],
        e=t["expected_cash"],
        c=data.counted_cash,
        diff=data.counted_cash - t["expected_cash"],
        n=data.note,
        st="confirmed" if confirmed else "pending",
        u=actor.user_id,
        cb=actor.user_id if confirmed else None,
    ).scalar_one()
    if not confirmed:
        from app.services import approvals

        diff = data.counted_cash - t["expected_cash"]
        approvals.request(
            db,
            actor,
            "cash_close",
            cid,
            f"Day close: counted ₹{data.counted_cash:,.2f}"
            + (
                f", short by ₹{-diff:,.2f}"
                if diff < 0
                else f", over by ₹{diff:,.2f}"
                if diff > 0
                else ", matches"
            ),
            data.counted_cash,
        )
    audit.record(
        db,
        actor,
        "day_close",
        cid,
        "create",
        None,
        {"counted": str(data.counted_cash), "expected": str(t["expected_cash"])},
    )
    return cash_day(db, actor)


def decide_close(db: Session, actor: Actor, close_id: UUID, approve: bool) -> None:
    _q(
        db,
        "UPDATE day_closes SET status = :st, confirmed_by = :u WHERE id = :i AND status = 'pending'",
        st="confirmed" if approve else "rejected",
        u=actor.user_id,
        i=close_id,
    )


def closes(db: Session, actor: Actor, limit: int = 60) -> list[dict[str, Any]]:
    rows = _q(
        db,
        "SELECT id, business_date, opening_cash, cash_in, cash_out, expected_cash, counted_cash, difference, note, status,"
        " closed_by_name, created_at FROM day_closes WHERE shop_id = :s ORDER BY business_date DESC, created_at DESC LIMIT :l",
        s=shop_id_of(actor),
        l=limit,
    ).mappings()
    return [dict(r) for r in rows]


def day_book(db: Session, actor: Actor, start: date | None, end: date | None) -> dict[str, Any]:
    """Every confirmed money movement in time order, with a running cash balance."""
    ctx = shop_ctx(db, actor)
    end = end or _today(ctx)
    start = start or end
    a, b = _bounds(ctx, start, end)
    rows = _q(
        db,
        """SELECT p.id, p.occurred_at, p.direction, p.method, p.amount, p.applies_to_type, p.reference, p.receipt_no, p.note,
             i.number AS invoice_number, i.buyer_name, e.category_name, n.number AS credit_note_number,
             w.name AS worker_name, bo.lender_name, c.name AS customer_name
           FROM payments p
           LEFT JOIN invoices i ON p.applies_to_type = 'invoice' AND i.id = p.applies_to_id
           LEFT JOIN expenses e ON p.applies_to_type = 'expense' AND e.id = p.applies_to_id
           LEFT JOIN credit_notes n ON p.applies_to_type = 'credit_note' AND n.id = p.applies_to_id
           LEFT JOIN labour_payments lp ON p.applies_to_type = 'labour_payment' AND lp.id = p.applies_to_id
           LEFT JOIN labourers w ON w.id = lp.labourer_id
           LEFT JOIN borrowings bo ON p.applies_to_type = 'borrowing' AND bo.id = p.applies_to_id
           LEFT JOIN customers c ON p.party_type = 'customer' AND c.id = p.party_id
           WHERE p.shop_id = :s AND p.status = 'confirmed' AND p.occurred_at >= :a AND p.occurred_at < :b
           ORDER BY p.occurred_at""",
        s=ctx.id,
        a=a,
        b=b,
    ).mappings()
    cash = _opening(db, ctx, start)
    opening = cash
    entries = []
    for r in rows:
        if r["method"] == "cash":
            cash += r["amount"] if r["direction"] == "in" else -r["amount"]
        entries.append(
            {
                "id": r["id"],
                "at": r["occurred_at"],
                "direction": r["direction"],
                "method": r["method"],
                "amount": r["amount"],
                "label": _label(r),
                "cash_balance": cash,
            }
        )
    return {
        "from": start,
        "to": end,
        "opening_cash": opening,
        "closing_cash": cash,
        "entries": entries,
    }


def _label(r: Any) -> str:
    k = r["applies_to_type"]
    if k == "invoice" or (k is None and r["receipt_no"]):
        who = r["customer_name"] or r["buyer_name"]
        doc = r["receipt_no"] or r["invoice_number"]
        return f"{'Collection' if r['receipt_no'] else 'Sale'} {doc}" + (f" · {who}" if who else "")
    if k == "expense":
        return f"Expense · {r['category_name']}"
    if k == "credit_note":
        return f"Refund {r['credit_note_number']}"
    if k == "labour_payment":
        return f"Wages · {r['worker_name']}"
    if k == "borrowing":
        return f"{'Borrowed from' if r['direction'] == 'in' else 'Repaid'} {r['lender_name']}"
    return r["note"] or "Other"

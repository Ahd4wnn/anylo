"""Workers, attendance and wage payments. All wage arithmetic is in labour_wages (ported from PlantBill)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.database import Actor
from app.errors import AppError
from app.schemas.backoffice import AttendanceIn, LabourPayIn, WorkerIn
from app.services import audit
from app.services.backoffice import _at, _pay, _reverse
from app.services.labour_wages import (
    STATUS_DAYS,
    STATUS_LEAVES,
    daily_earnings,
    month_start,
    monthly_earnings,
    unpaid_leaves_in_month,
)
from app.services.sales import _q, _today, shop_ctx
from app.services.shop import shop_id_of

ZERO = Decimal("0")


def _ledger(w: Any, marks: list[Any], paid: Decimal, today: date) -> dict[str, Any]:
    """Earned, paid and balance for one worker from their attendance rows (day, status)."""
    marks = [m for m in marks if w.joined_on <= m.day <= today]
    days = sum((STATUS_DAYS[m.status] for m in marks), ZERO)
    leaves: dict[date, Decimal] = {}
    for m in marks:
        k = month_start(m.day)
        leaves[k] = leaves.get(k, ZERO) + STATUS_LEAVES[m.status]
    this_month = month_start(today)
    marked_now = [m.day for m in marks if m.day >= this_month]
    last_marked = max(marked_now) if marked_now else None
    if w.wage_type == "monthly":
        earned = monthly_earnings(
            w.monthly_wage, w.paid_leaves_per_month, w.joined_on, today, leaves, last_marked
        )
    else:
        earned = daily_earnings(w.daily_wage, days)
    month_leaves = leaves.get(this_month, ZERO)
    return {
        "days_worked": days,
        "earned": earned,
        "total_paid": paid,
        "balance_to_pay": earned - paid,
        "leaves_this_month": month_leaves,
        "unpaid_leaves_this_month": unpaid_leaves_in_month(month_leaves, w.paid_leaves_per_month)
        if w.wage_type == "monthly"
        else ZERO,
        "accrued_through": last_marked if w.wage_type == "monthly" else None,
    }


def _shape(w: Any, marks: list[Any], paid: Decimal, today: date) -> dict[str, Any]:
    base = {
        k: getattr(w, k)
        for k in (
            "id",
            "name",
            "phone",
            "aadhaar_last4",
            "gender",
            "wage_type",
            "daily_wage",
            "monthly_wage",
            "paid_leaves_per_month",
            "joined_on",
            "is_active",
        )
    }
    return base | _ledger(w, marks, paid, today)


def list_workers(db: Session, actor: Actor, include_inactive: bool) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    today = _today(ctx)
    workers = list(
        _q(
            db,
            "SELECT * FROM labourers WHERE shop_id = :s AND deleted_at IS NULL"
            + ("" if include_inactive else " AND is_active")
            + " ORDER BY is_active DESC, name",
            s=ctx.id,
        )
    )
    marks: dict[UUID, list[Any]] = {}
    for m in _q(
        db, "SELECT labourer_id, day, status FROM labour_attendance WHERE shop_id = :s", s=ctx.id
    ):
        marks.setdefault(m.labourer_id, []).append(m)
    paid = {
        r.labourer_id: r.total
        for r in _q(
            db,
            "SELECT labourer_id, sum(amount) AS total FROM labour_payments WHERE shop_id = :s AND deleted_at IS NULL GROUP BY 1",
            s=ctx.id,
        )
    }
    today_marks = {
        r.labourer_id: r.status
        for r in _q(
            db,
            "SELECT labourer_id, status FROM labour_attendance WHERE shop_id = :s AND day = :d",
            s=ctx.id,
            d=today,
        )
    }
    items = [
        _shape(w, marks.get(w.id, []), paid.get(w.id, ZERO), today)
        | {"today": today_marks.get(w.id)}
        for w in workers
    ]
    return {
        "items": items,
        "balance_to_pay": sum(
            (i["balance_to_pay"] for i in items if i["balance_to_pay"] > 0), ZERO
        ),
    }


def _worker(db: Session, actor: Actor, wid: UUID) -> Any:
    w = _q(
        db,
        "SELECT * FROM labourers WHERE id = :i AND shop_id = :s AND deleted_at IS NULL",
        i=wid,
        s=shop_id_of(actor),
    ).first()
    if not w:
        raise AppError("labour.not_found", "This worker was not found.", 404)
    return w


def _check_wage(data: WorkerIn) -> None:
    wage = data.monthly_wage if data.wage_type == "monthly" else data.daily_wage
    if wage <= 0:
        raise AppError("labour.no_wage", "Enter the worker's wage.", 422)


def create_worker(db: Session, actor: Actor, data: WorkerIn) -> dict[str, Any]:
    _check_wage(data)
    ctx = shop_ctx(db, actor)
    wid: UUID = _q(
        db,
        "INSERT INTO labourers (shop_id, name, phone, aadhaar_last4, gender, wage_type, daily_wage, monthly_wage,"
        " paid_leaves_per_month, joined_on, is_active) VALUES (:s, :n, :p, :a, :g, :wt, :dw, :mw, :pl, :j, :ia) RETURNING id",
        s=ctx.id,
        n=data.name.strip(),
        p=data.phone,
        a=data.aadhaar_last4,
        g=data.gender,
        wt=data.wage_type,
        dw=data.daily_wage,
        mw=data.monthly_wage,
        pl=data.paid_leaves_per_month,
        j=data.joined_on or _today(ctx),
        ia=data.is_active,
    ).scalar_one()
    audit.record(db, actor, "labourer", wid, "create", None, {"name": data.name})
    worker: dict[str, Any] = statement(db, actor, wid)["worker"]
    return worker


def update_worker(db: Session, actor: Actor, wid: UUID, data: WorkerIn) -> dict[str, Any]:
    _check_wage(data)
    before = _worker(db, actor, wid)
    _q(
        db,
        "UPDATE labourers SET name = :n, phone = :p, aadhaar_last4 = :a, gender = :g, wage_type = :wt, daily_wage = :dw,"
        " monthly_wage = :mw, paid_leaves_per_month = :pl, joined_on = :j, is_active = :ia WHERE id = :i",
        n=data.name.strip(),
        p=data.phone,
        a=data.aadhaar_last4,
        g=data.gender,
        wt=data.wage_type,
        dw=data.daily_wage,
        mw=data.monthly_wage,
        pl=data.paid_leaves_per_month,
        j=data.joined_on or before.joined_on,
        ia=data.is_active,
        i=wid,
    )
    audit.record(
        db,
        actor,
        "labourer",
        wid,
        "update",
        {
            "wage_type": before.wage_type,
            "daily_wage": str(before.daily_wage),
            "monthly_wage": str(before.monthly_wage),
        },
        {
            "wage_type": data.wage_type,
            "daily_wage": str(data.daily_wage),
            "monthly_wage": str(data.monthly_wage),
        },
    )
    worker: dict[str, Any] = statement(db, actor, wid)["worker"]
    return worker


def delete_worker(db: Session, actor: Actor, wid: UUID) -> None:
    w = _worker(db, actor, wid)
    _q(db, "UPDATE labourers SET deleted_at = now(), is_active = false WHERE id = :i", i=wid)
    audit.record(db, actor, "labourer", wid, "delete", {"name": w.name}, None)


def attendance(db: Session, actor: Actor, day: date | None) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    day = day or _today(ctx)
    rows = _q(
        db,
        "SELECT w.id AS labourer_id, w.name, w.wage_type, a.status FROM labourers w"
        " LEFT JOIN labour_attendance a ON a.labourer_id = w.id AND a.day = :d"
        " WHERE w.shop_id = :s AND w.deleted_at IS NULL AND w.is_active AND w.joined_on <= :d ORDER BY w.name",
        s=ctx.id,
        d=day,
    ).mappings()
    return {"day": day, "items": [dict(r) for r in rows]}


def mark(db: Session, actor: Actor, data: AttendanceIn) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    w = _worker(db, actor, data.labourer_id)
    if data.day > _today(ctx):
        raise AppError("labour.future", "Attendance can't be marked for a future day.", 422)
    if data.day < w.joined_on:
        raise AppError("labour.before_joining", f"{w.name} joined on {w.joined_on:%d %b %Y}.", 422)
    _q(
        db,
        "INSERT INTO labour_attendance (shop_id, labourer_id, day, status, marked_by) VALUES (:s, :w, :d, :st, :u)"
        " ON CONFLICT (labourer_id, day) DO UPDATE SET status = EXCLUDED.status, marked_by = EXCLUDED.marked_by, updated_at = now()",
        s=ctx.id,
        w=w.id,
        d=data.day,
        st=data.status,
        u=actor.user_id,
    )
    return attendance(db, actor, data.day)


def pay(db: Session, actor: Actor, data: LabourPayIn) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    w = _worker(db, actor, data.labourer_id)
    total = data.cash_amount + data.upi_amount
    if total <= 0:
        raise AppError("labour.zero", "Enter the amount paid.", 422)
    day = data.paid_on or _today(ctx)
    if day > _today(ctx):
        raise AppError("labour.future", "A payment can't be dated in the future.", 422)
    pid: UUID = _q(
        db,
        "INSERT INTO labour_payments (shop_id, labourer_id, kind, amount, days, note, paid_on, created_by, created_by_name)"
        " VALUES (:s, :w, :k, :a, :d, :n, :p, :u, (SELECT full_name FROM users WHERE id = :u)) RETURNING id",
        s=ctx.id,
        w=w.id,
        k=data.kind,
        a=total,
        d=data.days,
        n=data.note,
        p=day,
        u=actor.user_id,
    ).scalar_one()
    at = _at(ctx, day) if day != _today(ctx) else datetime.now(UTC)
    for method, amount in (("cash", data.cash_amount), ("upi", data.upi_amount)):
        if amount > 0:
            _pay(
                db,
                actor,
                ctx,
                "out",
                method,
                amount,
                ("labour_payment", pid),
                at,
                ("labourer", w.id),
            )
    audit.record(
        db,
        actor,
        "labour_payment",
        pid,
        "create",
        None,
        {"worker": w.name, "amount": str(total), "kind": data.kind},
    )
    worker: dict[str, Any] = statement(db, actor, w.id)["worker"]
    return worker


def payments(
    db: Session, actor: Actor, wid: UUID | None, start: date | None, end: date | None
) -> list[dict[str, Any]]:
    p: dict[str, Any] = {"s": shop_id_of(actor)}
    where = "lp.shop_id = :s AND lp.deleted_at IS NULL"
    if wid:
        where += " AND lp.labourer_id = :w"
        p["w"] = wid
    if start:
        where += " AND lp.paid_on >= :a"
        p["a"] = start
    if end:
        where += " AND lp.paid_on <= :b"
        p["b"] = end
    rows = _q(
        db,
        "SELECT lp.id, lp.labourer_id, w.name AS worker_name, lp.kind, lp.amount, lp.days, lp.note, lp.paid_on, lp.created_by_name,"
        " coalesce((SELECT sum(amount) FROM payments p WHERE p.applies_to_type = 'labour_payment' AND p.applies_to_id = lp.id"
        "   AND p.method = 'cash' AND p.status = 'confirmed'), 0) AS cash_amount,"
        " coalesce((SELECT sum(amount) FROM payments p WHERE p.applies_to_type = 'labour_payment' AND p.applies_to_id = lp.id"
        "   AND p.method = 'upi' AND p.status = 'confirmed'), 0) AS upi_amount"
        f" FROM labour_payments lp JOIN labourers w ON w.id = lp.labourer_id WHERE {where} ORDER BY lp.paid_on DESC, lp.created_at DESC",
        **p,
    ).mappings()
    return [dict(r) for r in rows]


def delete_payment(db: Session, actor: Actor, pid: UUID) -> None:
    r = _q(
        db,
        "UPDATE labour_payments SET deleted_at = now() WHERE id = :i AND shop_id = :s AND deleted_at IS NULL RETURNING amount, labourer_id, paid_on",
        i=pid,
        s=shop_id_of(actor),
    ).first()
    if not r:
        raise AppError("labour.payment_not_found", "This payment was not found.", 404)
    _reverse(db, "labour_payment", pid)
    audit.record(db, actor, "labour_payment", pid, "delete", {"amount": str(r.amount)}, None)


def statement(db: Session, actor: Actor, wid: UUID) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    w = _worker(db, actor, wid)
    marks = list(
        _q(
            db,
            "SELECT day, status FROM labour_attendance WHERE labourer_id = :w ORDER BY day DESC",
            w=wid,
        )
    )
    paid = _q(
        db,
        "SELECT coalesce(sum(amount), 0) FROM labour_payments WHERE labourer_id = :w AND deleted_at IS NULL",
        w=wid,
    ).scalar()
    return {
        "worker": _shape(w, marks, paid, _today(ctx)),
        "attendance": [{"day": m.day, "status": m.status} for m in marks[:62]],
        "payments": payments(db, actor, wid, None, None),
    }

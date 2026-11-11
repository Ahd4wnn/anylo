"""Dashboard, goals, P&L, cash flow and ageing (docs/09-finance-reports-goals.md §2, §3, §5).

ponytail: everything is computed live; daily_snapshots (spec §2 "Performance") come when a shop's data makes this slow.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.database import Actor
from app.errors import AppError
from app.services import audit, backoffice
from app.services.finance.metrics import ZERO, balances, bounds, compute, metric_value
from app.services.sales import ShopCtx, _q, _today, shop_ctx

METRIC_LABELS = {
    "sales": "Sales",
    "gross_profit": "Gross profit",
    "net_profit": "Net profit",
    "invoices_count": "Bills",
    "avg_bill_value": "Average bill",
    "new_customers": "New customers",
    "collections": "Collections",
}


def _check_range(start: date, end: date) -> None:
    if end < start:
        raise AppError("report.bad_range", "The end date is before the start date.", 422)
    if (end - start).days > 400:
        raise AppError("report.range_too_long", "Pick a range of up to about a year.", 422)


# --- dashboard ---


def dashboard(db: Session, actor: Actor, start: date, end: date) -> dict[str, Any]:
    _check_range(start, end)
    ctx = shop_ctx(db, actor)
    days = (end - start).days + 1
    prev = compute(db, ctx, start - timedelta(days=days), start - timedelta(days=1))
    now = compute(db, ctx, start, end)
    a, b = bounds(ctx, start, end)
    p: dict[str, Any] = {"s": ctx.id, "a": a, "b": b, "tz": str(ctx.tz)}
    grain = "week" if days > 62 else "day"

    def by(sql: str) -> dict[date, Decimal]:
        return {r.d: r.v for r in _q(db, sql, g=grain, **p)}

    period = "date_trunc(:g, {col} AT TIME ZONE :tz)::date"
    inv_where = "i.shop_id = :s AND i.status = 'issued' AND i.issued_at >= :a AND i.issued_at < :b"
    inv = f"invoices i WHERE {inv_where}"
    lines_join = f"invoice_lines l JOIN invoices i ON i.id = l.invoice_id WHERE {inv_where}"
    cn = "credit_notes n WHERE n.shop_id = :s AND n.issued_at >= :a AND n.issued_at < :b"
    sales = by(
        f"SELECT {period.format(col='i.issued_at')} AS d, sum(i.grand_total) AS v FROM {inv} GROUP BY 1"
    )
    rev = by(
        f"SELECT {period.format(col='i.issued_at')} AS d, sum(i.taxable_total + i.round_off) AS v FROM {inv} GROUP BY 1"
    )
    cogs = by(
        f"SELECT {period.format(col='i.issued_at')} AS d, round(sum(l.qty * l.cost_price), 2) AS v FROM {lines_join} GROUP BY 1"
    )
    ret = by(
        f"SELECT {period.format(col='n.issued_at')} AS d, sum(n.grand_total) AS v FROM {cn} GROUP BY 1"
    )
    ret_rev = by(
        f"SELECT {period.format(col='n.issued_at')} AS d, sum(n.taxable_total + n.round_off) AS v FROM {cn} GROUP BY 1"
    )
    trend = [
        {
            "date": d,
            "sales": sales.get(d, ZERO) - ret.get(d, ZERO),
            "profit": rev.get(d, ZERO) - ret_rev.get(d, ZERO) - cogs.get(d, ZERO),
        }
        for d in _buckets(start, end, grain)
    ]
    mix = [
        dict(r)
        for r in _q(
            db,
            "SELECT p.method, sum(p.amount) AS amount FROM payments p JOIN invoices i ON p.applies_to_type = 'invoice'"
            f" AND i.id = p.applies_to_id WHERE p.status = 'confirmed' AND p.batch_id IS NULL AND {inv_where} GROUP BY 1 ORDER BY 2 DESC",
            **p,
        ).mappings()
    ]
    due = _q(db, f"SELECT coalesce(sum(i.due_total), 0) FROM {inv}", **p).scalar()
    if due:
        mix.append({"method": "due", "amount": due})
    top = (
        "SELECT l.name, sum(l.qty) AS qty, sum(l.taxable) AS revenue, round(sum(l.taxable - l.qty * l.cost_price), 2) AS profit"
        f" FROM {lines_join}"
        " GROUP BY l.name ORDER BY {order} DESC LIMIT 10"
    )
    staff = [
        dict(r)
        for r in _q(
            db,
            "SELECT coalesce(i.created_by_name, 'Someone') AS name, count(*) AS bills, sum(i.grand_total) AS sales,"
            f" round(avg(i.grand_total), 2) AS avg_bill FROM {inv} GROUP BY 1 ORDER BY 3 DESC",
            **p,
        ).mappings()
    ]
    return {
        "from": start,
        "to": end,
        "grain": grain,
        "current": now.as_dict(),
        "previous": prev.as_dict(),
        **balances(db, ctx),
        "cash_in_hand": backoffice.cash_day(db, actor)["expected_cash"],
        "trend": trend,
        "payment_mix": mix,
        "top_by_revenue": [dict(r) for r in _q(db, top.format(order="revenue"), **p).mappings()],
        "top_by_profit": [dict(r) for r in _q(db, top.format(order="profit"), **p).mappings()],
        "staff": staff,
        "alerts": alerts(db, ctx),
        "goals": list_goals(db, actor, active_only=True),
    }


def _buckets(start: date, end: date, grain: str) -> list[date]:
    """Every day (or Monday-started week) in the range, so empty days show as gaps instead of disappearing."""
    step = 7 if grain == "week" else 1
    cur = start - timedelta(days=start.weekday()) if grain == "week" else start
    out = []
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=step)
    return out


def alerts(db: Session, ctx: ShopCtx) -> list[dict[str, Any]]:
    r = _q(
        db,
        "SELECT"
        " (SELECT count(*) FROM product_variants v JOIN products p ON p.id = v.product_id WHERE v.shop_id = :s AND p.track_stock"
        "   AND p.deleted_at IS NULL AND v.reorder_level > 0 AND v.stock_qty <= v.reorder_level AND v.stock_qty >= 0) AS low,"
        " (SELECT count(*) FROM product_variants v JOIN products p ON p.id = v.product_id WHERE v.shop_id = :s AND p.track_stock"
        "   AND p.deleted_at IS NULL AND v.stock_qty < 0) AS negative,"
        " (SELECT coalesce(sum(due_total), 0) FROM invoices WHERE shop_id = :s AND status = 'issued' AND due_total > 0"
        "   AND issued_at < now() - interval '30 days') AS overdue,"
        " (SELECT count(*) FROM approval_requests WHERE shop_id = :s AND status = 'pending') AS approvals,"
        " (SELECT count(*) FROM day_closes WHERE shop_id = :s AND status <> 'rejected' AND abs(difference) >= 100"
        "   AND business_date >= current_date - 7) AS cash_diffs",
        s=ctx.id,
    ).one()
    out = []
    if r.low:
        out.append(
            {
                "kind": "low_stock",
                "text": f"{r.low} item{'s' if r.low != 1 else ''} running low",
                "link": "/app/purchases/restock",
            }
        )
    if r.negative:
        out.append(
            {
                "kind": "negative_stock",
                "text": f"{r.negative} item{'s' if r.negative != 1 else ''} below zero stock",
                "link": "/app/items/stock",
            }
        )
    if r.overdue:
        out.append(
            {
                "kind": "overdue",
                "text": f"₹{r.overdue:,.2f} due for more than 30 days",
                "link": "/app/customers",
            }
        )
    if r.approvals:
        out.append(
            {
                "kind": "approvals",
                "text": f"{r.approvals} waiting for your approval",
                "link": "/app/money/approvals",
            }
        )
    if r.cash_diffs:
        out.append(
            {
                "kind": "cash",
                "text": f"{r.cash_diffs} day close{'s' if r.cash_diffs != 1 else ''} this week didn't match",
                "link": "/app/money/cash",
            }
        )
    return out


# --- goals ---


def _progress(db: Session, ctx: ShopCtx, g: Any) -> dict[str, Any]:
    today = _today(ctx)
    upto = min(today, g.period_end)
    total_days = (g.period_end - g.period_start).days + 1
    elapsed = max(0, (upto - g.period_start).days + 1)
    actual = (
        metric_value(compute(db, ctx, g.period_start, upto, g.user_id), g.metric)
        if elapsed
        else ZERO
    )
    remaining = total_days - elapsed
    projection = (actual / elapsed * total_days).quantize(Decimal("0.01")) if elapsed else ZERO
    if actual >= g.target:
        status = "achieved"
    elif today > g.period_end:
        status = "missed"
    elif projection >= g.target:
        status = "on_track"
    elif projection >= g.target * Decimal("0.9"):
        status = "at_risk"
    else:
        status = "behind"
    return {
        "actual": actual,
        "percent": (actual * 100 / g.target).quantize(Decimal("0.1")),
        "elapsed_percent": Decimal(elapsed * 100 / total_days).quantize(Decimal("0.1")),
        "expected_by_now": (g.target * elapsed / total_days).quantize(Decimal("0.01")),
        "run_rate_needed": ((g.target - actual) / remaining).quantize(Decimal("0.01"))
        if remaining > 0 and actual < g.target
        else None,
        "projection": projection,
        "days_left": remaining,
        "status": status,
    }


def list_goals(db: Session, actor: Actor, active_only: bool = False) -> list[dict[str, Any]]:
    ctx = shop_ctx(db, actor)
    where = "g.shop_id = :s AND g.deleted_at IS NULL"
    if actor.role == "salesperson":  # their own target plus the team's
        where += " AND (g.user_id IS NULL OR g.user_id = :u)"
    if active_only:
        where += " AND g.period_end >= :today - 7"
    rows = _q(
        db,
        "SELECT g.*, u.full_name AS user_name FROM goals g LEFT JOIN users u ON u.id = g.user_id"
        f" WHERE {where} ORDER BY g.period_end DESC, g.created_at DESC LIMIT 50",
        s=ctx.id,
        u=actor.user_id,
        today=_today(ctx),
    ).all()
    return [
        {
            k: getattr(g, k)
            for k in (
                "id",
                "metric",
                "title",
                "period_start",
                "period_end",
                "target",
                "user_id",
                "user_name",
            )
        }
        | {"metric_label": METRIC_LABELS[g.metric]}
        | _progress(db, ctx, g)
        for g in rows
    ]


def create_goal(db: Session, actor: Actor, data: Any) -> dict[str, Any]:
    gid: UUID = _q(
        db,
        "INSERT INTO goals (shop_id, metric, title, period_start, period_end, target, user_id, created_by)"
        " VALUES (:s, :m, :t, :a, :b, :tg, :u, :by) RETURNING id",
        s=shop_ctx(db, actor).id,
        m=data.metric,
        t=data.title or f"{METRIC_LABELS[data.metric]} target",
        a=data.period_start,
        b=data.period_end,
        tg=data.target,
        u=data.user_id,
        by=actor.user_id,
    ).scalar_one()
    audit.record(
        db, actor, "goal", gid, "create", None, {"metric": data.metric, "target": str(data.target)}
    )
    return next(g for g in list_goals(db, actor) if g["id"] == gid)


def delete_goal(db: Session, actor: Actor, goal_id: UUID) -> None:
    r = _q(
        db,
        "UPDATE goals SET deleted_at = now() WHERE id = :i AND shop_id = :s AND deleted_at IS NULL RETURNING id",
        i=goal_id,
        s=shop_ctx(db, actor).id,
    ).first()
    if not r:
        raise AppError("goal.not_found", "This goal was not found.", 404)
    audit.record(db, actor, "goal", goal_id, "delete", None, None)


def suggest_goal(db: Session, actor: Actor, metric: str, start: date, end: date) -> dict[str, Any]:
    """Template "grow 10% over the previous period": what the same-length period before scored."""
    ctx = shop_ctx(db, actor)
    days = (end - start).days + 1
    last = metric_value(
        compute(db, ctx, start - timedelta(days=days), start - timedelta(days=1)), metric
    )
    return {
        "previous": last,
        "suggested": (last * Decimal("1.1")).quantize(Decimal("1")) if last else None,
    }


# --- statements ---


def _months(start: date, end: date) -> list[tuple[date, date]]:
    out, cur = [], start
    while cur <= end:
        nxt = (cur.replace(day=1) + timedelta(days=32)).replace(day=1)
        out.append((cur, min(end, nxt - timedelta(days=1))))
        cur = nxt
    return out


def pnl(db: Session, actor: Actor, start: date, end: date) -> dict[str, Any]:
    _check_range(start, end)
    ctx = shop_ctx(db, actor)
    cats = {
        r.category_name: r.amount
        for r in _q(
            db,
            "SELECT category_name, sum(amount - CASE WHEN itc_eligible THEN coalesce(gst_amount, 0) ELSE 0 END) AS amount FROM expenses"
            " WHERE shop_id = :s AND deleted_at IS NULL AND occurred_on BETWEEN :a AND :b GROUP BY 1 ORDER BY 2 DESC",
            s=ctx.id,
            a=start,
            b=end,
        )
    }
    return {
        "from": start,
        "to": end,
        "months": [
            {"from": a, "to": b} | compute(db, ctx, a, b).as_dict() for a, b in _months(start, end)
        ],
        "total": compute(db, ctx, start, end).as_dict(),
        "expenses_by_category": [{"name": k, "amount": v} for k, v in cats.items()],
    }


def _flow_label(r: Any) -> str:
    if r.direction == "in":
        if r.applies_to_type == "borrowing":
            return "Money borrowed"
        if r.applies_to_type == "capital":
            return "Capital introduced"
        if r.applies_to_type == "asset":
            return "Assets sold"
        if r.party_type == "customer":
            return "Due collections" if r.collected else "Sales"
        return "Other money in"
    return {
        "expense": "Expenses",
        "labour_payment": "Wages",
        "borrowing": "Loan repayments",
        "credit_note": "Refunds to customers",
        "drawing": "Owner drawings",
        "tax": "Tax paid",
        "asset": "Assets bought",
    }.get(
        r.applies_to_type, "Supplier payments" if r.party_type == "supplier" else "Other money out"
    )


def cash_flow(db: Session, actor: Actor, start: date, end: date) -> dict[str, Any]:
    _check_range(start, end)
    ctx = shop_ctx(db, actor)
    a, b = bounds(ctx, start, end)
    lines: dict[tuple[str, str], dict[str, Any]] = {}
    for r in _q(
        db,
        "SELECT direction, applies_to_type, party_type, batch_id IS NOT NULL AS collected, method = 'cash' AS is_cash,"
        " sum(amount) AS amount FROM payments WHERE shop_id = :s AND status = 'confirmed' AND method <> 'store_credit'"
        " AND occurred_at >= :a AND occurred_at < :b GROUP BY 1, 2, 3, 4, 5",
        s=ctx.id,
        a=a,
        b=b,
    ):
        row = lines.setdefault(
            (r.direction, _flow_label(r)),
            {"direction": r.direction, "label": _flow_label(r), "cash": ZERO, "bank": ZERO},
        )
        row["cash" if r.is_cash else "bank"] += r.amount
    rows = sorted(lines.values(), key=lambda x: (x["direction"] != "in", -(x["cash"] + x["bank"])))
    net = {
        k: sum((x[k] if x["direction"] == "in" else -x[k] for x in rows), ZERO)
        for k in ("cash", "bank")
    }
    opening = backoffice._opening(db, ctx, start)
    return {
        "from": start,
        "to": end,
        "lines": rows,
        "net_cash": net["cash"],
        "net_bank": net["bank"],
        "opening_cash": opening,
        "closing_cash": opening + net["cash"],
    }


BUCKETS = ("0_30", "31_60", "61_90", "over_90")


def _bucket(age_days: int) -> str:
    return (
        "0_30"
        if age_days <= 30
        else "31_60"
        if age_days <= 60
        else "61_90"
        if age_days <= 90
        else "over_90"
    )


def receivables(db: Session, actor: Actor) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    today = _today(ctx)
    out: dict[UUID, dict[str, Any]] = {}
    for c in _q(
        db,
        "SELECT c.id, coalesce(c.name, c.phone) AS name, c.phone, b.balance,"
        " (SELECT max(occurred_at) FROM payments p WHERE p.party_type = 'customer' AND p.party_id = c.id AND p.direction = 'in'"
        "   AND p.status = 'confirmed') AS last_payment"
        " FROM customers c JOIN customer_balances b ON b.customer_id = c.id WHERE c.shop_id = :s AND b.balance > 0",
        s=ctx.id,
    ):
        out[c.id] = {
            "customer_id": c.id,
            "name": c.name,
            "phone": c.phone,
            "balance": c.balance,
            "last_payment": c.last_payment,
        } | dict.fromkeys(BUCKETS, ZERO)
    for i in _q(
        db,
        "SELECT customer_id, issued_at, due_total FROM invoices WHERE shop_id = :s AND status = 'issued' AND due_total > 0"
        " AND customer_id IS NOT NULL",
        s=ctx.id,
    ):
        if i.customer_id in out:
            out[i.customer_id][_bucket((today - i.issued_at.astimezone(ctx.tz).date()).days)] += (
                i.due_total
            )
    for row in (
        out.values()
    ):  # old dues from before Anylo, or dues left after returns/store credit, count as oldest
        row["over_90"] += max(row["balance"] - sum((row[k] for k in BUCKETS), ZERO), ZERO)
    return _ageing(list(out.values()))


def payables(db: Session, actor: Actor) -> dict[str, Any]:
    """Supplier payments settle the oldest bills first, so what's still owed sits on the newest bills."""
    ctx = shop_ctx(db, actor)
    today = _today(ctx)
    rows = []
    for s in _q(
        db,
        "SELECT s.id, s.name, b.balance FROM suppliers s JOIN supplier_balances b ON b.supplier_id = s.id"
        " WHERE s.shop_id = :s AND s.deleted_at IS NULL AND b.balance > 0",
        s=ctx.id,
    ):
        row = {"supplier_id": s.id, "name": s.name, "balance": s.balance} | dict.fromkeys(
            BUCKETS, ZERO
        )
        left = s.balance
        for p in _q(
            db,
            "SELECT posted_at, grand_total FROM purchases WHERE supplier_id = :i AND status = 'posted' ORDER BY posted_at DESC",
            i=s.id,
        ):
            if left <= 0:
                break
            part = min(left, p.grand_total)
            row[_bucket((today - p.posted_at.astimezone(ctx.tz).date()).days)] += part
            left -= part
        row["over_90"] += left
        rows.append(row)
    return _ageing(rows)


def _ageing(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows.sort(key=lambda r: -r["balance"])
    return {
        "items": rows,
        "totals": {k: sum((r[k] for r in rows), ZERO) for k in (*BUCKETS, "balance")},
    }

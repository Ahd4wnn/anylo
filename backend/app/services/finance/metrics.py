"""The one place money metrics are defined (docs/09-finance-reports-goals.md §1).

Dashboard, reports, goals, Excel and (later) the AI manager all call these functions; there is no second
implementation. Ranges are inclusive shop-local dates.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.sales import ShopCtx, _q

ZERO = Decimal("0")


def bounds(ctx: ShopCtx, start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time(0), ctx.tz), datetime.combine(
        end + timedelta(days=1), time(0), ctx.tz
    )


@dataclass
class Metrics:
    gross_sales: Decimal
    returns: Decimal
    net_sales: Decimal
    output_tax: Decimal
    net_revenue: Decimal
    cogs: Decimal
    gross_profit: Decimal
    gross_margin_pct: Decimal
    expenses: Decimal
    labour: Decimal
    net_profit: Decimal
    collections: Decimal
    invoices_count: int
    avg_bill_value: Decimal
    new_customers: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute(
    db: Session, ctx: ShopCtx, start: date, end: date, user_id: UUID | None = None
) -> Metrics:
    """`user_id` narrows sales-side numbers to one salesperson; expenses and wages stay shop-wide (zero for staff)."""
    a, b = bounds(ctx, start, end)
    p: dict[str, Any] = {"s": ctx.id, "a": a, "b": b, "u": user_id, "d1": start, "d2": end}
    staff = " AND i.created_by = :u" if user_id else ""
    inv = _q(
        db,
        "SELECT count(*) AS n, coalesce(sum(grand_total), 0) AS gross, coalesce(sum(taxable_total + round_off), 0) AS rev,"
        " coalesce(sum(cgst_total + sgst_total + igst_total + cess_total), 0) AS tax"
        f" FROM invoices i WHERE i.shop_id = :s AND i.status = 'issued' AND i.issued_at >= :a AND i.issued_at < :b{staff}",
        **p,
    ).one()
    cogs = _q(
        db,
        "SELECT coalesce(round(sum(l.qty * l.cost_price), 2), 0) FROM invoice_lines l JOIN invoices i ON i.id = l.invoice_id"
        f" WHERE i.shop_id = :s AND i.status = 'issued' AND i.issued_at >= :a AND i.issued_at < :b{staff}",
        **p,
    ).scalar()
    cn = _q(
        db,
        "SELECT coalesce(sum(n.grand_total), 0) AS gross, coalesce(sum(n.taxable_total + n.round_off), 0) AS rev,"
        " coalesce(sum(n.cgst_total + n.sgst_total + n.igst_total + n.cess_total), 0) AS tax,"
        " coalesce(sum(CASE WHEN n.restock THEN (SELECT round(sum(l.qty * l.cost_price), 2) FROM credit_note_lines l"
        "   WHERE l.credit_note_id = n.id) END), 0) AS cogs"
        " FROM credit_notes n LEFT JOIN invoices i ON i.id = n.original_invoice_id"
        f" WHERE n.shop_id = :s AND n.issued_at >= :a AND n.issued_at < :b{staff}",
        **p,
    ).one()
    if user_id:
        expenses = labour = ZERO
    else:
        # GST on an expense is claimable for regular shops, so it isn't a cost there.
        expenses = _q(
            db,
            "SELECT coalesce(sum(amount - CASE WHEN :reg THEN coalesce(gst_amount, 0) ELSE 0 END), 0) FROM expenses"
            " WHERE shop_id = :s AND deleted_at IS NULL AND occurred_on BETWEEN :d1 AND :d2",
            reg=ctx.scheme == "regular",
            **p,
        ).scalar()
        # ponytail: wages on cash basis (what was paid), as the spec's default; accrual needs the wage engine per day.
        labour = _q(
            db,
            "SELECT coalesce(sum(amount), 0) FROM labour_payments WHERE shop_id = :s AND deleted_at IS NULL"
            " AND paid_on BETWEEN :d1 AND :d2",
            **p,
        ).scalar()
    collections = _q(
        db,
        "SELECT coalesce(sum(amount), 0) FROM payments WHERE shop_id = :s AND direction = 'in' AND status = 'confirmed'"
        " AND party_type = 'customer' AND method <> 'store_credit' AND occurred_at >= :a AND occurred_at < :b"
        + (" AND received_by = :u" if user_id else ""),
        **p,
    ).scalar()
    new_customers = _q(
        db,
        "SELECT count(*) FROM (SELECT i.customer_id FROM invoices i WHERE i.shop_id = :s AND i.status = 'issued'"
        f" AND i.customer_id IS NOT NULL{staff} GROUP BY i.customer_id HAVING min(i.issued_at) >= :a AND min(i.issued_at) < :b) x",
        **p,
    ).scalar()
    net_sales = inv.gross - cn.gross
    net_revenue = inv.rev - cn.rev
    cogs_net = cogs - cn.cogs
    gross_profit = net_revenue - cogs_net
    return Metrics(
        gross_sales=inv.gross,
        returns=cn.gross,
        net_sales=net_sales,
        output_tax=inv.tax - cn.tax,
        net_revenue=net_revenue,
        cogs=cogs_net,
        gross_profit=gross_profit,
        gross_margin_pct=(gross_profit * 100 / net_revenue).quantize(Decimal("0.1"))
        if net_revenue
        else ZERO,
        expenses=expenses,
        labour=labour,
        net_profit=gross_profit - expenses - labour,
        collections=collections,
        invoices_count=inv.n,
        avg_bill_value=(net_sales / inv.n).quantize(Decimal("0.01")) if inv.n else ZERO,
        new_customers=new_customers,
    )


def balances(db: Session, ctx: ShopCtx) -> dict[str, Decimal]:
    """Point-in-time figures: what's owed both ways and what the stock is worth."""
    r = _q(
        db,
        "SELECT (SELECT coalesce(sum(balance), 0) FROM customer_balances WHERE shop_id = :s AND balance > 0) AS receivables,"
        " (SELECT coalesce(sum(balance), 0) FROM supplier_balances WHERE shop_id = :s AND balance > 0) AS payables,"
        " (SELECT round(coalesce(sum(v.stock_qty * v.cost_price), 0), 2) FROM product_variants v JOIN products p ON p.id = v.product_id"
        "   WHERE v.shop_id = :s AND p.track_stock AND p.deleted_at IS NULL AND v.stock_qty > 0) AS stock_value",
        s=ctx.id,
    ).one()
    return dict(r._mapping)


def metric_value(m: Metrics, metric: str) -> Decimal:
    return Decimal(getattr(m, "net_sales" if metric == "sales" else metric))

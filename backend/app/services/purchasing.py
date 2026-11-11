"""Suppliers, purchases (weighted-average cost), supplier payments and stock counts (docs/08-inventory.md §3, §4, §6)."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Actor
from app.errors import AppError
from app.schemas.purchasing import CountIn, CountLineIn, PurchaseIn, SupplierIn, SupplierPayIn
from app.services import audit
from app.services.books import ensure_open
from app.services.catalogue import _move
from app.services.gst import engine
from app.services.sales import _q, shop_ctx
from app.services.shop import shop_id_of

ZERO = Decimal("0")


def q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"))


# --- suppliers ---

SUP = (
    "s.id, s.name, s.gstin, s.phone, s.email, s.address, s.state_code, s.opening_balance, b.balance"
)


def list_suppliers(db: Session, actor: Actor, q: str | None) -> dict[str, Any]:
    p: dict[str, Any] = {"s": shop_id_of(actor)}
    where = "s.shop_id = :s AND s.deleted_at IS NULL"
    if q:
        where += " AND (s.name ILIKE :like OR s.phone LIKE :like OR s.gstin ILIKE :like)"
        p["like"] = f"%{q.strip()}%"
    rows = [
        dict(r)
        for r in _q(
            db,
            f"SELECT {SUP}, (SELECT max(created_at) FROM purchases x WHERE x.supplier_id = s.id AND x.status = 'posted') AS last_purchase"
            f" FROM suppliers s JOIN supplier_balances b ON b.supplier_id = s.id WHERE {where} ORDER BY b.balance DESC, s.name",
            **p,
        ).mappings()
    ]
    return {"items": rows, "payable": sum((r["balance"] for r in rows if r["balance"] > 0), ZERO)}


def _supplier(db: Session, actor: Actor, sid: UUID) -> Any:
    r = _q(
        db,
        f"SELECT {SUP} FROM suppliers s JOIN supplier_balances b ON b.supplier_id = s.id"
        " WHERE s.id = :i AND s.shop_id = :s AND s.deleted_at IS NULL",
        i=sid,
        s=shop_id_of(actor),
    ).first()
    if not r:
        raise AppError("supplier.not_found", "This supplier was not found.", 404)
    return r


def save_supplier(
    db: Session, actor: Actor, data: SupplierIn, sid: UUID | None = None
) -> dict[str, Any]:
    state = data.state_code or (data.gstin[:2] if data.gstin else None)
    vals = {
        "n": data.name.strip(),
        "g": data.gstin,
        "p": data.phone,
        "e": data.email,
        "a": data.address,
        "st": state,
        "ob": data.opening_balance,
    }
    try:
        if sid:
            _supplier(db, actor, sid)
            _q(
                db,
                "UPDATE suppliers SET name = :n, gstin = :g, phone = :p, email = :e, address = :a, state_code = :st,"
                " opening_balance = :ob WHERE id = :i",
                i=sid,
                **vals,
            )
        else:
            sid = _q(
                db,
                "INSERT INTO suppliers (shop_id, name, gstin, phone, email, address, state_code, opening_balance)"
                " VALUES (:s, :n, :g, :p, :e, :a, :st, :ob) RETURNING id",
                s=shop_id_of(actor),
                **vals,
            ).scalar_one()
    except IntegrityError:
        raise AppError(
            "supplier.name_taken", "A supplier with this name already exists.", 409
        ) from None
    audit.record(
        db,
        actor,
        "supplier",
        sid,
        "save",
        None,
        {"name": data.name, "opening_balance": str(data.opening_balance)},
    )
    return dict(_supplier(db, actor, sid)._mapping)


def delete_supplier(db: Session, actor: Actor, sid: UUID) -> None:
    s = _supplier(db, actor, sid)
    if s.balance != 0:
        raise AppError(
            "supplier.has_balance", "Settle what you owe this supplier before removing them.", 409
        )
    _q(db, "UPDATE suppliers SET deleted_at = now() WHERE id = :i", i=sid)
    audit.record(db, actor, "supplier", sid, "delete", {"name": s.name}, None)


def supplier_ledger(db: Session, actor: Actor, sid: UUID) -> dict[str, Any]:
    s = _supplier(db, actor, sid)
    rows = _q(
        db,
        """SELECT posted_at AS at, 'purchase' AS kind, coalesce(supplier_invoice_no, 'Purchase') AS ref, id AS ref_id,
                  grand_total AS added, 0 AS paid FROM purchases WHERE supplier_id = :s AND status = 'posted'
           UNION ALL
           SELECT occurred_at, 'payment', upper(method), applies_to_id, 0, amount FROM payments
             WHERE party_type = 'supplier' AND party_id = :s AND direction = 'out' AND status = 'confirmed'
           ORDER BY 1""",
        s=sid,
    ).mappings()
    running = s.opening_balance
    entries = []
    for r in rows:
        running += r["added"] - r["paid"]
        entries.append(dict(r) | {"balance": running})
    return {
        "supplier": dict(s._mapping),
        "opening_balance": s.opening_balance,
        "entries": entries,
        "balance": s.balance,
    }


def pay_supplier(
    db: Session, actor: Actor, sid: UUID, data: SupplierPayIn, purchase_id: UUID | None = None
) -> dict[str, Any]:
    s = _supplier(db, actor, sid)
    if purchase_id is None and data.amount > s.balance:
        raise AppError(
            "supplier.overpay", f"You owe this supplier ₹{max(s.balance, ZERO):,.2f}.", 422
        )
    _q(
        db,
        "INSERT INTO payments (shop_id, direction, method, amount, reference, party_type, party_id, applies_to_type,"
        " applies_to_id, received_by, note) VALUES (:sh, 'out', :m, :a, :r, 'supplier', :s, :at, :ai, :u, :n)",
        sh=shop_id_of(actor),
        m=data.method,
        a=data.amount,
        r=data.reference,
        s=sid,
        at="purchase" if purchase_id else None,
        ai=purchase_id,
        u=actor.user_id,
        n=data.note,
    )
    audit.record(
        db,
        actor,
        "supplier_payment",
        sid,
        "pay",
        None,
        {"amount": str(data.amount), "method": data.method},
    )
    return dict(_supplier(db, actor, sid)._mapping)


# --- purchases ---


def _price(
    db: Session, actor: Actor, data: PurchaseIn, supply_type: str
) -> tuple[list[dict[str, Any]], engine.InvoiceOut]:
    sid = shop_id_of(actor)
    vids = [ln.variant_id for ln in data.lines]
    items = {
        r.id: r
        for r in _q(
            db,
            "SELECT v.id, v.name AS variant_name, p.name, p.hsn_code, p.tax_rate_id, r.rate FROM product_variants v"
            " JOIN products p ON p.id = v.product_id LEFT JOIN gst_rates r ON r.id = p.tax_rate_id"
            " WHERE v.shop_id = :s AND v.id = ANY(:ids)",
            s=sid,
            ids=vids,
        )
    }
    overrides = {
        r.id: r.rate
        for r in _q(
            db,
            "SELECT id, rate FROM gst_rates WHERE id = ANY(:ids)",
            ids=[ln.tax_rate_id for ln in data.lines if ln.tax_rate_id],
        )
    }
    lines = []
    for ln in data.lines:
        it = items.get(ln.variant_id)
        if not it:
            raise AppError("purchase.bad_item", "One of the items wasn't found.", 422)
        rate = overrides.get(ln.tax_rate_id) if ln.tax_rate_id else it.rate
        lines.append({"in": ln, "item": it, "rate": rate if rate is not None else ZERO})
    out = engine.compute(
        engine.InvoiceIn(
            [
                engine.LineIn(
                    qty=x["in"].qty,
                    unit_price=x["in"].unit_cost,
                    rate=x["rate"],
                    price_includes_tax=False,
                    line_discount=x["in"].discount,
                )
                for x in lines
            ],
            supply_type=supply_type,  # type: ignore[arg-type]
            scheme="regular",  # the supplier's bill carries GST whatever our own scheme is
            round_off=False,
        )
    )
    return lines, out


def _write_lines(
    db: Session, actor: Actor, pid: UUID, lines: list[dict[str, Any]], out: engine.InvoiceOut
) -> None:
    _q(db, "DELETE FROM purchase_lines WHERE purchase_id = :p", p=pid)
    for i, (x, o) in enumerate(zip(lines, out.lines, strict=True), start=1):
        it = x["item"]
        _q(
            db,
            "INSERT INTO purchase_lines (shop_id, purchase_id, line_no, variant_id, description, hsn_code, qty, unit_cost, discount,"
            " taxable, tax_rate, cgst, sgst, igst, cess, line_total)"
            " VALUES (:s, :p, :no, :v, :d, :h, :q, :c, :di, :t, :r, :cg, :sg, :ig, :ce, :lt)",
            s=shop_id_of(actor),
            p=pid,
            no=i,
            v=it.id,
            d=it.name + (f" {it.variant_name}" if it.variant_name else ""),
            h=it.hsn_code,
            q=x["in"].qty,
            c=x["in"].unit_cost,
            di=x["in"].discount,
            t=o.taxable,
            r=o.rate,
            cg=o.cgst,
            sg=o.sgst,
            ig=o.igst,
            ce=o.cess,
            lt=o.total,
        )


def _supply_type(ctx: Any, supplier: Any) -> str:
    return "inter" if supplier.state_code and supplier.state_code != ctx.state_code else "intra"


def create(db: Session, actor: Actor, data: PurchaseIn) -> tuple[dict[str, Any], bool]:
    ctx = shop_ctx(db, actor)
    dup = _q(
        db,
        "SELECT id FROM purchases WHERE shop_id = :s AND idempotency_key = :k",
        s=ctx.id,
        k=data.idempotency_key,
    ).scalar()
    if dup:
        return get(db, actor, dup), True
    sup = _supplier(db, actor, data.supplier_id)
    st = _supply_type(ctx, sup)
    lines, out = _price(db, actor, data, st)
    itc = (
        data.itc_eligible and ctx.scheme == "regular"
    )  # composition and unregistered shops can't claim ITC
    try:
        pid: UUID = _q(
            db,
            "INSERT INTO purchases (shop_id, supplier_id, supplier_invoice_no, supplier_invoice_date, supply_type, taxable_total,"
            " cgst_total, sgst_total, igst_total, cess_total, round_off, grand_total, itc_eligible, notes, idempotency_key,"
            " created_by, created_by_name) VALUES (:s, :sup, :no, :dt, :st, :t, :cg, :sg, :ig, :ce, 0, :gt, :itc, :n, :k, :u,"
            " (SELECT full_name FROM users WHERE id = :u)) RETURNING id",
            s=ctx.id,
            sup=sup.id,
            no=(data.supplier_invoice_no or "").strip() or None,
            dt=data.supplier_invoice_date,
            st=st,
            t=out.taxable_total,
            cg=out.cgst_total,
            sg=out.sgst_total,
            ig=out.igst_total,
            ce=out.cess_total,
            gt=out.grand_total,
            itc=itc,
            n=data.notes,
            k=data.idempotency_key,
            u=actor.user_id,
        ).scalar_one()
    except IntegrityError as e:
        if "purchases_supplier_bill" in str(e.orig):
            raise AppError(
                "purchase.duplicate_bill", "This supplier bill number is already entered.", 409
            ) from None
        raise
    _write_lines(db, actor, pid, lines, out)
    audit.record(
        db,
        actor,
        "purchase",
        pid,
        "create",
        None,
        {"supplier": sup.name, "total": str(out.grand_total)},
    )
    if data.post:
        post(db, actor, pid, data.paid)
    return get(db, actor, pid), False


def update_draft(db: Session, actor: Actor, pid: UUID, data: PurchaseIn) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    p = _purchase(db, actor, pid)
    if p.status != "draft":
        raise AppError(
            "purchase.not_draft",
            "Only a draft can be changed. Cancel this purchase and enter it again.",
            409,
        )
    sup = _supplier(db, actor, data.supplier_id)
    st = _supply_type(ctx, sup)
    lines, out = _price(db, actor, data, st)
    try:
        _q(
            db,
            "UPDATE purchases SET supplier_id = :sup, supplier_invoice_no = :no, supplier_invoice_date = :dt, supply_type = :st,"
            " taxable_total = :t, cgst_total = :cg, sgst_total = :sg, igst_total = :ig, cess_total = :ce, grand_total = :gt,"
            " itc_eligible = :itc, notes = :n WHERE id = :i",
            sup=sup.id,
            no=(data.supplier_invoice_no or "").strip() or None,
            dt=data.supplier_invoice_date,
            st=st,
            t=out.taxable_total,
            cg=out.cgst_total,
            sg=out.sgst_total,
            ig=out.igst_total,
            ce=out.cess_total,
            gt=out.grand_total,
            itc=data.itc_eligible and ctx.scheme == "regular",
            n=data.notes,
            i=pid,
        )
    except IntegrityError:
        raise AppError(
            "purchase.duplicate_bill", "This supplier bill number is already entered.", 409
        ) from None
    _write_lines(db, actor, pid, lines, out)
    if data.post:
        post(db, actor, pid, data.paid)
    return get(db, actor, pid)


def _purchase(db: Session, actor: Actor, pid: UUID) -> Any:
    p = _q(
        db,
        "SELECT * FROM purchases WHERE id = :i AND shop_id = :s FOR UPDATE",
        i=pid,
        s=shop_id_of(actor),
    ).first()
    if not p:
        raise AppError("purchase.not_found", "This purchase was not found.", 404)
    return p


def post(db: Session, actor: Actor, pid: UUID, paid: list[Any] | None = None) -> dict[str, Any]:
    """Stock in, weighted-average cost updated, payable created (docs/08-inventory.md §3)."""
    p = _purchase(db, actor, pid)
    ensure_open(db, p.shop_id, p.supplier_invoice_date or date.today())
    if p.status != "draft":
        raise AppError("purchase.not_draft", "This purchase is already posted or cancelled.", 409)
    if sum((x.amount for x in paid or []), ZERO) > p.grand_total:
        raise AppError("purchase.overpaid", "Paid is more than the bill.", 422)
    for ln in _q(
        db,
        "SELECT l.*, v.stock_qty, v.cost_price, pr.track_stock FROM purchase_lines l JOIN product_variants v ON v.id = l.variant_id"
        " JOIN products pr ON pr.id = v.product_id WHERE l.purchase_id = :p ORDER BY l.line_no FOR UPDATE OF v",
        p=pid,
    ):
        # Landed cost per unit: GST is a cost only when it can't be claimed back as ITC.
        landed = (ln.taxable if p.itc_eligible else ln.line_total) / ln.qty
        old_qty = ln.stock_qty if ln.track_stock else ZERO
        avg = (
            landed
            if old_qty <= 0
            else (old_qty * ln.cost_price + ln.qty * landed) / (old_qty + ln.qty)
        )
        _q(
            db,
            "UPDATE product_variants SET cost_price = :c WHERE id = :v",
            c=q2(avg),
            v=ln.variant_id,
        )
        if ln.track_stock:
            _move(
                db,
                actor,
                ln.variant_id,
                "purchase",
                ln.qty,
                q2(landed),
                p.supplier_invoice_no,
                ("purchase", str(pid)),
            )
    _q(db, "UPDATE purchases SET status = 'posted', posted_at = now() WHERE id = :i", i=pid)
    from app.schemas.purchasing import SupplierPayIn

    for x in paid or []:
        pay_supplier(
            db,
            actor,
            p.supplier_id,
            SupplierPayIn(amount=x.amount, method=x.method, reference=x.reference),
            purchase_id=pid,
        )
    audit.record(db, actor, "purchase", pid, "post", None, {"total": str(p.grand_total)})
    return get(db, actor, pid)


def cancel(db: Session, actor: Actor, pid: UUID) -> dict[str, Any]:
    p = _purchase(db, actor, pid)
    ensure_open(db, p.shop_id, p.supplier_invoice_date or date.today())
    if p.status == "cancelled":
        raise AppError("purchase.cancelled", "This purchase is already cancelled.", 409)
    if p.status == "posted":
        # ponytail: average cost is not rolled back; the next purchase re-averages. Fine unless a costly bill was wrong.
        for ln in _q(
            db,
            "SELECT l.variant_id, l.qty, l.taxable, l.line_total, pr.track_stock FROM purchase_lines l JOIN product_variants v"
            " ON v.id = l.variant_id JOIN products pr ON pr.id = v.product_id WHERE l.purchase_id = :p",
            p=pid,
        ):
            if ln.track_stock:
                landed = (ln.taxable if p.itc_eligible else ln.line_total) / ln.qty
                _move(
                    db,
                    actor,
                    ln.variant_id,
                    "purchase_return",
                    -ln.qty,
                    q2(landed),
                    "Purchase cancelled",
                    ("purchase", str(pid)),
                )
        _q(
            db,
            "UPDATE payments SET status = 'reversed' WHERE applies_to_type = 'purchase' AND applies_to_id = :i AND status = 'confirmed'",
            i=pid,
        )
    _q(db, "UPDATE purchases SET status = 'cancelled', cancelled_at = now() WHERE id = :i", i=pid)
    audit.record(
        db,
        actor,
        "purchase",
        pid,
        "cancel",
        {"status": p.status, "total": str(p.grand_total)},
        None,
    )
    return get(db, actor, pid)


def get(db: Session, actor: Actor, pid: UUID) -> dict[str, Any]:
    p = (
        _q(
            db,
            "SELECT p.*, s.name AS supplier_name, s.gstin AS supplier_gstin,"
            " coalesce((SELECT sum(amount) FROM payments m WHERE m.applies_to_type = 'purchase' AND m.applies_to_id = p.id"
            "   AND m.status = 'confirmed'), 0) AS paid"
            " FROM purchases p JOIN suppliers s ON s.id = p.supplier_id WHERE p.id = :i AND p.shop_id = :s",
            i=pid,
            s=shop_id_of(actor),
        )
        .mappings()
        .first()
    )
    if not p:
        raise AppError("purchase.not_found", "This purchase was not found.", 404)
    lines = _q(
        db, "SELECT * FROM purchase_lines WHERE purchase_id = :i ORDER BY line_no", i=pid
    ).mappings()
    return dict(p) | {"lines": [dict(r) for r in lines]}


def list_purchases(
    db: Session, actor: Actor, supplier_id: UUID | None, status: str | None, limit: int, offset: int
) -> dict[str, Any]:
    p: dict[str, Any] = {"s": shop_id_of(actor), "lim": limit, "off": offset}
    where = "p.shop_id = :s"
    if supplier_id:
        where += " AND p.supplier_id = :sup"
        p["sup"] = supplier_id
    if status:
        where += " AND p.status = :st"
        p["st"] = status
    rows = _q(
        db,
        "SELECT p.id, p.supplier_invoice_no, p.supplier_invoice_date, p.grand_total, p.status, p.created_at, p.posted_at,"
        " s.name AS supplier_name, (SELECT count(*) FROM purchase_lines l WHERE l.purchase_id = p.id) AS items"
        f" FROM purchases p JOIN suppliers s ON s.id = p.supplier_id WHERE {where} ORDER BY p.created_at DESC LIMIT :lim OFFSET :off",
        **p,
    ).mappings()
    return {"items": [dict(r) for r in rows]}


def restock_suggestions(db: Session, actor: Actor) -> list[dict[str, Any]]:
    """Low-stock items with a suggested order (reorder_level x 2 - stock, at least 1)."""
    rows = _q(
        db,
        "SELECT v.id AS variant_id, p.name, v.name AS variant_name, v.stock_qty, v.reorder_level, v.cost_price, coalesce(gr.rate, 0) AS tax_rate,"
        " greatest(v.reorder_level * 2 - v.stock_qty, 1) AS suggested_qty"
        " FROM product_variants v JOIN products p ON p.id = v.product_id LEFT JOIN gst_rates gr ON gr.id = p.tax_rate_id"
        " WHERE v.shop_id = :s AND p.track_stock AND p.deleted_at IS NULL AND v.reorder_level > 0 AND v.stock_qty <= v.reorder_level"
        " ORDER BY v.stock_qty - v.reorder_level, p.name LIMIT 200",
        s=shop_id_of(actor),
    ).mappings()
    return [dict(r) for r in rows]


# --- stock counts ---


def start_count(db: Session, actor: Actor, data: CountIn) -> dict[str, Any]:
    sid = shop_id_of(actor)
    cid: UUID = _q(
        db,
        "INSERT INTO stock_counts (shop_id, name, category_id, started_by, started_by_name)"
        " VALUES (:s, :n, :c, :u, (SELECT full_name FROM users WHERE id = :u)) RETURNING id",
        s=sid,
        n=data.name,
        c=data.category_id,
        u=actor.user_id,
    ).scalar_one()
    # Expected quantities are frozen now; posting applies (counted - expected), so sales during the count still count.
    _q(
        db,
        "INSERT INTO stock_count_lines (shop_id, count_id, variant_id, expected_qty, unit_cost)"
        " SELECT v.shop_id, :c, v.id, v.stock_qty, v.cost_price FROM product_variants v JOIN products p ON p.id = v.product_id"
        " WHERE v.shop_id = :s AND p.track_stock AND p.deleted_at IS NULL AND (CAST(:cat AS uuid) IS NULL OR p.category_id = :cat)",
        c=cid,
        s=sid,
        cat=data.category_id,
    )
    return get_count(db, actor, cid)


def _count(db: Session, actor: Actor, cid: UUID) -> Any:
    c = _q(
        db, "SELECT * FROM stock_counts WHERE id = :i AND shop_id = :s", i=cid, s=shop_id_of(actor)
    ).first()
    if not c:
        raise AppError("count.not_found", "This stock count was not found.", 404)
    return c


def get_count(db: Session, actor: Actor, cid: UUID) -> dict[str, Any]:
    c = _count(db, actor, cid)
    lines = [
        dict(r)
        for r in _q(
            db,
            "SELECT l.variant_id, p.name, v.name AS variant_name, v.barcode, v.sku, p.unit_code, l.expected_qty, l.counted_qty,"
            " l.counted_qty - l.expected_qty AS variance_qty, round((l.counted_qty - l.expected_qty) * l.unit_cost, 2) AS variance_value"
            " FROM stock_count_lines l JOIN product_variants v ON v.id = l.variant_id JOIN products p ON p.id = v.product_id"
            " WHERE l.count_id = :c ORDER BY (l.counted_qty IS NULL), p.name",
            c=cid,
        ).mappings()
    ]
    counted = [x for x in lines if x["counted_qty"] is not None]
    return dict(c._mapping) | {
        "lines": lines,
        "counted": len(counted),
        "variance_value": sum((x["variance_value"] for x in counted), ZERO),
    }


def set_count_line(db: Session, actor: Actor, cid: UUID, data: CountLineIn) -> dict[str, Any]:
    c = _count(db, actor, cid)
    if c.status != "open":
        raise AppError("count.closed", "This stock count is already finished.", 409)
    vid = data.variant_id
    if vid is None and data.code:
        vid = _q(
            db,
            "SELECT id FROM product_variants WHERE shop_id = :s AND (barcode = :c OR lower(sku) = lower(:c))",
            s=c.shop_id,
            c=data.code.strip(),
        ).scalar()
    if vid is None:
        raise AppError("count.unknown_item", "No item has this code.", 404)
    if data.add is not None:
        r = _q(
            db,
            "UPDATE stock_count_lines SET counted_qty = coalesce(counted_qty, 0) + :a WHERE count_id = :c AND variant_id = :v RETURNING variant_id",
            a=data.add,
            c=cid,
            v=vid,
        ).first()
    else:
        r = _q(
            db,
            "UPDATE stock_count_lines SET counted_qty = :q WHERE count_id = :c AND variant_id = :v RETURNING variant_id",
            q=data.counted_qty,
            c=cid,
            v=vid,
        ).first()
    if not r:
        raise AppError(
            "count.not_in_count",
            "This item isn't part of this count (stock not tracked or another category).",
            404,
        )
    line = (
        _q(
            db,
            "SELECT l.variant_id, p.name, l.expected_qty, l.counted_qty FROM stock_count_lines l JOIN product_variants v ON v.id = l.variant_id"
            " JOIN products p ON p.id = v.product_id WHERE l.count_id = :c AND l.variant_id = :v",
            c=cid,
            v=vid,
        )
        .mappings()
        .one()
    )
    return dict(line)


def post_count(db: Session, actor: Actor, cid: UUID) -> dict[str, Any]:
    c = _count(db, actor, cid)
    if c.status != "open":
        raise AppError("count.closed", "This stock count is already finished.", 409)
    n = 0
    for ln in _q(
        db,
        "SELECT variant_id, expected_qty, counted_qty, unit_cost FROM stock_count_lines WHERE count_id = :c AND counted_qty IS NOT NULL",
        c=cid,
    ):
        _move(
            db,
            actor,
            ln.variant_id,
            "adjustment",
            ln.counted_qty - ln.expected_qty,
            ln.unit_cost,
            c.name,
            ("stock_count", str(cid)),
        )
        n += 1
    _q(
        db,
        "UPDATE stock_counts SET status = 'posted', posted_by = :u, posted_at = now() WHERE id = :i",
        u=actor.user_id,
        i=cid,
    )
    audit.record(db, actor, "stock_count", cid, "post", None, {"lines": n})
    return get_count(db, actor, cid)


def cancel_count(db: Session, actor: Actor, cid: UUID) -> None:
    c = _count(db, actor, cid)
    if c.status != "open":
        raise AppError("count.closed", "This stock count is already finished.", 409)
    _q(db, "UPDATE stock_counts SET status = 'cancelled' WHERE id = :i", i=cid)


def list_counts(db: Session, actor: Actor) -> list[dict[str, Any]]:
    rows = _q(
        db,
        "SELECT c.id, c.name, c.status, c.created_at, c.posted_at, c.started_by_name,"
        " (SELECT count(*) FROM stock_count_lines l WHERE l.count_id = c.id AND l.counted_qty IS NOT NULL) AS counted,"
        " (SELECT count(*) FROM stock_count_lines l WHERE l.count_id = c.id) AS items"
        " FROM stock_counts c WHERE c.shop_id = :s ORDER BY c.created_at DESC LIMIT 50",
        s=shop_id_of(actor),
    ).mappings()
    return [dict(r) for r in rows]

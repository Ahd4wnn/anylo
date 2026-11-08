"""Categories, products, variants and the stock ledger (docs/08-inventory.md)."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import media
from app.database import Actor
from app.errors import AppError
from app.schemas.catalogue import AdjustIn, CategoryIn, ProductIn, VariantIn
from app.services import audit
from app.services.shop import shop_id_of

PRODUCT_SQL = """
SELECT p.*, c.name AS category_name, r.rate AS tax_rate,
  (t.gst_scheme = 'regular' AND (p.tax_rate_id IS NULL OR p.hsn_code IS NULL
     OR length(p.hsn_code) < t.hsn_digits_required)) AS missing_tax_info
FROM products p
LEFT JOIN categories c ON c.id = p.category_id
LEFT JOIN gst_rates r ON r.id = p.tax_rate_id
JOIN shop_tax_profiles t ON t.shop_id = p.shop_id
"""
VARIANT_COLS = "id, product_id, name, sku, barcode, mrp, sale_price, cost_price, reorder_level, stock_qty, is_active"


def _q(db: Session, sql: str, **p: Any) -> Any:
    return db.execute(text(sql), p)


def ean13_check(digits12: str) -> str:
    s = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(digits12))
    return str((10 - s % 10) % 10)


def is_valid_ean13(code: str) -> bool:
    return len(code) == 13 and code.isdigit() and ean13_check(code[:12]) == code[12]


# --- categories ---


def list_categories(db: Session, actor: Actor) -> list[Any]:
    return list(
        _q(
            db,
            """
        SELECT c.id, c.name, c.sort_order,
          (SELECT count(*) FROM products p WHERE p.category_id = c.id AND p.deleted_at IS NULL) AS product_count
        FROM categories c WHERE c.shop_id = :s ORDER BY c.sort_order, lower(c.name)""",
            s=shop_id_of(actor),
        )
    )


def save_category(
    db: Session, actor: Actor, data: CategoryIn, category_id: UUID | None = None
) -> Any:
    sid = shop_id_of(actor)
    try:
        with db.begin_nested():
            if category_id:
                row = _q(
                    db,
                    "UPDATE categories SET name = :n, sort_order = :o WHERE id = :i AND shop_id = :s"
                    " RETURNING id, name, sort_order",
                    n=data.name.strip(),
                    o=data.sort_order,
                    i=category_id,
                    s=sid,
                ).first()
                if not row:
                    raise AppError("category.not_found", "This category was not found.", 404)
                return row
            return _q(
                db,
                "INSERT INTO categories (shop_id, name, sort_order) VALUES (:s, :n, :o)"
                " RETURNING id, name, sort_order",
                s=sid,
                n=data.name.strip(),
                o=data.sort_order,
            ).one()
    except IntegrityError:
        raise AppError(
            "category.exists", "A category with this name already exists.", 409
        ) from None


def delete_category(db: Session, actor: Actor, category_id: UUID) -> None:
    # Products keep existing; they just become uncategorised (FK ON DELETE SET NULL).
    _q(
        db,
        "DELETE FROM categories WHERE id = :i AND shop_id = :s",
        i=category_id,
        s=shop_id_of(actor),
    )


def category_by_name(db: Session, shop_id: UUID, name: str) -> UUID:
    row = _q(
        db,
        "SELECT id FROM categories WHERE shop_id = :s AND lower(name) = lower(:n)",
        s=shop_id,
        n=name.strip(),
    ).first()
    if row:
        return row.id  # type: ignore[no-any-return]
    new_id: UUID = _q(
        db,
        "INSERT INTO categories (shop_id, name) VALUES (:s, :n) RETURNING id",
        s=shop_id,
        n=name.strip(),
    ).scalar_one()
    return new_id


# --- reading ---


def _variants(
    db: Session, product_ids: list[UUID], include_inactive: bool = False
) -> dict[UUID, list[Any]]:
    out: dict[UUID, list[Any]] = {pid: [] for pid in product_ids}
    if not product_ids:
        return out
    rows = _q(
        db,
        f"SELECT {VARIANT_COLS} FROM product_variants WHERE product_id = ANY(:ids)"
        f"{'' if include_inactive else ' AND is_active'} ORDER BY created_at, name NULLS FIRST",
        ids=product_ids,
    )
    for r in rows:
        out[r.product_id].append(r._asdict())
    return out


def _shape(row: Any, variants: list[dict[str, Any]]) -> dict[str, Any]:
    d = dict(row._mapping)
    thumb = d["photo_path"].replace(".webp", "_thumb.webp") if d["photo_path"] else None
    return {
        **d,
        "photo_url": media.url(d["photo_path"]),
        "thumb_url": media.url(thumb),
        "archived": d["deleted_at"] is not None,
        "variants": variants,
    }


def get_product(db: Session, actor: Actor, product_id: UUID) -> dict[str, Any]:
    row = _q(
        db, PRODUCT_SQL + " WHERE p.id = :i AND p.shop_id = :s", i=product_id, s=shop_id_of(actor)
    ).first()
    if not row:
        raise AppError("product.not_found", "This item was not found.", 404)
    return _shape(row, _variants(db, [row.id])[row.id])


def list_products(
    db: Session,
    actor: Actor,
    *,
    q: str | None,
    category_id: UUID | None,
    low_stock: bool,
    include_archived: bool,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    where = ["p.shop_id = :s"]
    params: dict[str, Any] = {"s": shop_id_of(actor), "lim": limit, "off": offset}
    if not include_archived:
        where.append("p.deleted_at IS NULL")
    if category_id:
        where.append("p.category_id = :c")
        params["c"] = category_id
    if q:
        where.append(
            "(p.name ILIKE :q OR p.brand ILIKE :q OR EXISTS (SELECT 1 FROM product_variants v"
            " WHERE v.product_id = p.id AND (v.sku ILIKE :q OR v.barcode = :exact OR v.name ILIKE :q)))"
        )
        params["q"], params["exact"] = f"%{q.strip()}%", q.strip()
    if low_stock:
        where.append(
            "p.track_stock AND EXISTS (SELECT 1 FROM product_variants v WHERE v.product_id = p.id"
            " AND v.is_active AND v.stock_qty <= v.reorder_level)"
        )
    cond = " AND ".join(where)  # fragments above are constants; values are bound
    total = _q(db, f"SELECT count(*) FROM products p WHERE {cond}", **params).scalar_one()
    rows = _q(
        db, f"{PRODUCT_SQL} WHERE {cond} ORDER BY lower(p.name) LIMIT :lim OFFSET :off", **params
    ).all()
    vs = _variants(db, [r.id for r in rows])
    return [_shape(r, vs[r.id]) for r in rows], total


def lookup(db: Session, actor: Actor, code: str) -> dict[str, Any]:
    v = _q(
        db,
        f"SELECT {VARIANT_COLS} FROM product_variants WHERE shop_id = :s AND is_active"
        " AND (barcode = :c OR lower(sku) = lower(:c)) LIMIT 1",
        s=shop_id_of(actor),
        c=code.strip(),
    ).first()
    if not v:
        raise AppError("product.code_not_found", "No item has this barcode or SKU.", 404)
    return {"product": get_product(db, actor, v.product_id), "variant": v._asdict()}


# --- writing ---


def next_sku(db: Session, shop_id: UUID) -> str:
    n = _q(
        db,
        "UPDATE shops SET next_sku_seq = next_sku_seq + 1 WHERE id = :s RETURNING next_sku_seq - 1",
        s=shop_id,
    ).scalar_one()
    return f"AN-{n:06d}"


def next_ean(db: Session, shop_id: UUID) -> str:
    """Internal EAN-13 in the GS1 restricted-circulation range (prefix 2), unique per shop."""
    n = _q(
        db,
        "UPDATE shops SET next_ean_seq = next_ean_seq + 1 WHERE id = :s RETURNING next_ean_seq - 1",
        s=shop_id,
    ).scalar_one()
    body = f"2{n:011d}"
    return body + ean13_check(body)


def _shop_default_inclusive(db: Session, shop_id: UUID) -> bool:
    return bool(
        _q(
            db, "SELECT prices_include_tax FROM shop_tax_profiles WHERE shop_id = :s", s=shop_id
        ).scalar()
    )


def _check_refs(db: Session, data: ProductIn) -> None:
    if not _q(db, "SELECT 1 FROM units WHERE code = :u", u=data.unit_code).first():
        raise AppError("product.bad_unit", "Choose a valid unit.", 422)
    if (
        data.tax_rate_id
        and not _q(
            db, "SELECT 1 FROM gst_rates WHERE id = :r AND is_active", r=data.tax_rate_id
        ).first()
    ):
        raise AppError("product.bad_rate", "Choose a current GST rate.", 422)
    if (
        data.category_id
        and not _q(db, "SELECT 1 FROM categories WHERE id = :c", c=data.category_id).first()
    ):
        raise AppError("product.bad_category", "This category was not found.", 422)


def _move(
    db: Session,
    actor: Actor,
    variant_id: UUID,
    kind: str,
    qty: Decimal,
    unit_cost: Decimal,
    reason: str | None = None,
    ref: tuple[str, str] | None = None,
) -> None:
    """The only way stock changes: ledger row + cache update in the same transaction."""
    if qty == 0:
        return
    _q(
        db,
        "INSERT INTO stock_movements (shop_id, variant_id, kind, qty, unit_cost, reason, ref_type, ref_id, created_by)"
        " VALUES (:s, :v, :k, :q, :c, :r, :rt, :ri, :u)",
        s=shop_id_of(actor),
        v=variant_id,
        k=kind,
        q=qty,
        c=unit_cost,
        r=reason,
        rt=ref[0] if ref else None,
        ri=ref[1] if ref else None,
        u=actor.user_id,
    )
    _q(
        db,
        "UPDATE product_variants SET stock_qty = stock_qty + :q WHERE id = :v",
        q=qty,
        v=variant_id,
    )


def _insert_variant(
    db: Session, actor: Actor, product_id: UUID, v: VariantIn, track_stock: bool
) -> UUID:
    sid = shop_id_of(actor)
    vid: UUID = _q(
        db,
        "INSERT INTO product_variants (shop_id, product_id, name, sku, barcode, mrp, sale_price,"
        " cost_price, reorder_level) VALUES (:s, :p, :n, :sku, :b, :mrp, :sp, :cp, :rl) RETURNING id",
        s=sid,
        p=product_id,
        n=(v.name or "").strip() or None,
        sku=v.sku or next_sku(db, sid),
        b=v.barcode or None,
        mrp=v.mrp,
        sp=v.sale_price,
        cp=v.cost_price,
        rl=v.reorder_level,
    ).scalar_one()
    if track_stock and v.opening_stock:
        _move(db, actor, vid, "opening", v.opening_stock, v.cost_price, "Opening stock")
    return vid


def _unique_violation(e: IntegrityError) -> AppError:
    msg = str(e.orig)
    if "variants_shop_barcode" in msg:
        return AppError("product.barcode_taken", "Another item already uses this barcode.", 409)
    if "variants_shop_sku" in msg:
        return AppError("product.sku_taken", "Another item already uses this SKU.", 409)
    return AppError("product.invalid", "Check the item details.", 422)


def create_product(db: Session, actor: Actor, data: ProductIn) -> dict[str, Any]:
    sid = shop_id_of(actor)
    _check_refs(db, data)
    inclusive = (
        data.price_includes_tax
        if data.price_includes_tax is not None
        else _shop_default_inclusive(db, sid)
    )
    try:
        with db.begin_nested():
            pid: UUID = _q(
                db,
                "INSERT INTO products (shop_id, category_id, name, description, brand, hsn_code, is_service,"
                " tax_rate_id, cess_rate, price_includes_tax, unit_code, track_stock)"
                " VALUES (:s, :c, :n, :d, :b, :h, :svc, :r, :cess, :inc, :u, :t) RETURNING id",
                s=sid,
                c=data.category_id,
                n=data.name,
                d=data.description,
                b=data.brand,
                h=data.hsn_code,
                svc=data.is_service,
                r=data.tax_rate_id,
                cess=data.cess_rate,
                inc=inclusive,
                u=data.unit_code,
                t=data.track_stock,
            ).scalar_one()
            for v in data.variants:
                _insert_variant(db, actor, pid, v, data.track_stock)
    except IntegrityError as e:
        raise _unique_violation(e) from None
    audit.record(
        db,
        actor,
        "product",
        pid,
        "create",
        None,
        {"name": data.name, "variants": len(data.variants)},
    )
    return get_product(db, actor, pid)


def update_product(db: Session, actor: Actor, product_id: UUID, data: ProductIn) -> dict[str, Any]:
    before = get_product(db, actor, product_id)
    _check_refs(db, data)
    inclusive = (
        data.price_includes_tax
        if data.price_includes_tax is not None
        else before["price_includes_tax"]
    )
    existing = {v["id"] for v in _variants(db, [product_id], include_inactive=True)[product_id]}
    kept: set[UUID] = set()
    try:
        with db.begin_nested():
            _q(
                db,
                "UPDATE products SET category_id = :c, name = :n, description = :d, brand = :b, hsn_code = :h,"
                " is_service = :svc, tax_rate_id = :r, cess_rate = :cess, price_includes_tax = :inc, unit_code = :u,"
                " track_stock = :t WHERE id = :i",
                c=data.category_id,
                n=data.name,
                d=data.description,
                b=data.brand,
                h=data.hsn_code,
                svc=data.is_service,
                r=data.tax_rate_id,
                cess=data.cess_rate,
                inc=inclusive,
                u=data.unit_code,
                t=data.track_stock,
                i=product_id,
            )
            for v in data.variants:
                if v.id and v.id in existing:
                    kept.add(v.id)
                    # Stock is never edited here; it only changes through movements.
                    _q(
                        db,
                        "UPDATE product_variants SET name = :n, sku = coalesce(:sku, sku), barcode = :b, mrp = :mrp,"
                        " sale_price = :sp, cost_price = :cp, reorder_level = :rl, is_active = true WHERE id = :i",
                        n=(v.name or "").strip() or None,
                        sku=v.sku,
                        b=v.barcode or None,
                        mrp=v.mrp,
                        sp=v.sale_price,
                        cp=v.cost_price,
                        rl=v.reorder_level,
                        i=v.id,
                    )
                else:
                    _insert_variant(db, actor, product_id, v, data.track_stock)
            # Removed variants are deactivated, not deleted: past bills and stock history point at them.
            gone = existing - kept
            if gone:
                _q(
                    db,
                    "UPDATE product_variants SET is_active = false WHERE id = ANY(:ids)",
                    ids=list(gone),
                )
    except IntegrityError as e:
        raise _unique_violation(e) from None
    after = get_product(db, actor, product_id)
    audit.record(
        db,
        actor,
        "product",
        product_id,
        "update",
        {"name": before["name"], "prices": [str(v["sale_price"]) for v in before["variants"]]},
        {"name": after["name"], "prices": [str(v["sale_price"]) for v in after["variants"]]},
    )
    return after


def set_archived(db: Session, actor: Actor, product_id: UUID, archived: bool) -> None:
    get_product(db, actor, product_id)
    _q(
        db,
        f"UPDATE products SET deleted_at = {'now()' if archived else 'NULL'} WHERE id = :i",
        i=product_id,
    )
    audit.record(db, actor, "product", product_id, "archive" if archived else "restore")


def set_photo(db: Session, actor: Actor, product_id: UUID, data: bytes | None) -> dict[str, Any]:
    p = get_product(db, actor, product_id)
    base = f"products/{shop_id_of(actor)}/{product_id}"
    if data:
        media.save_image(data, f"{base}.webp", 800)
        media.save_image(data, f"{base}_thumb.webp", 200)
        path: str | None = f"{base}.webp"
    else:
        media.delete(p["photo_path"])
        media.delete(f"{base}_thumb.webp")
        path = None
    _q(db, "UPDATE products SET photo_path = :p WHERE id = :i", p=path, i=product_id)
    return get_product(db, actor, product_id)


# --- stock ---


def adjust(db: Session, actor: Actor, data: AdjustIn) -> dict[str, Any]:
    v = _q(
        db,
        "SELECT v.id, v.stock_qty, v.cost_price, p.track_stock FROM product_variants v JOIN products p"
        " ON p.id = v.product_id WHERE v.id = :i AND v.shop_id = :s",
        i=data.variant_id,
        s=shop_id_of(actor),
    ).first()
    if not v:
        raise AppError("product.not_found", "This item was not found.", 404)
    if not v.track_stock:
        raise AppError("stock.not_tracked", "Stock isn't tracked for this item.", 400)
    change = {"set": data.qty - v.stock_qty, "add": data.qty, "remove": -data.qty}[data.mode]
    kind = "damage" if data.kind == "damage" else data.kind
    if kind == "damage" and change > 0:
        raise AppError("stock.damage_positive", "Damaged stock can only reduce quantity.", 400)
    _move(db, actor, v.id, kind, change, v.cost_price, data.reason)
    row: dict[str, Any] = (
        _q(db, f"SELECT {VARIANT_COLS} FROM product_variants WHERE id = :i", i=v.id).one()._asdict()
    )
    return row


def movements(
    db: Session, actor: Actor, variant_id: UUID | None, limit: int, offset: int
) -> list[Any]:
    cond = "m.shop_id = :s" + (" AND m.variant_id = :v" if variant_id else "")
    return list(
        _q(
            db,
            f"""
        SELECT m.id, m.variant_id, p.name AS product_name, v.name AS variant_name, m.kind, m.qty, m.unit_cost,
          m.reason, u.full_name AS created_by_name, m.created_at
        FROM stock_movements m JOIN product_variants v ON v.id = m.variant_id JOIN products p ON p.id = v.product_id
        LEFT JOIN users u ON u.id = m.created_by
        WHERE {cond} ORDER BY m.created_at DESC, m.id DESC LIMIT :lim OFFSET :off""",
            s=shop_id_of(actor),
            v=variant_id,
            lim=limit,
            off=offset,
        )
    )


def valuation(db: Session, actor: Actor) -> dict[str, Any]:
    rows = _q(
        db,
        """
        SELECT coalesce(c.name, 'Uncategorised') AS category, count(DISTINCT p.id) AS items,
          coalesce(sum(greatest(v.stock_qty, 0)), 0) AS quantity,
          coalesce(sum(greatest(v.stock_qty, 0) * v.cost_price), 0) AS value
        FROM products p JOIN product_variants v ON v.product_id = p.id AND v.is_active
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.shop_id = :s AND p.deleted_at IS NULL AND p.track_stock
        GROUP BY 1 ORDER BY value DESC""",
        s=shop_id_of(actor),
    ).all()
    out = [r._asdict() for r in rows]
    return {"rows": out, "total_value": sum((r["value"] for r in out), Decimal("0"))}

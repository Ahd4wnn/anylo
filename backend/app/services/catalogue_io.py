"""Catalogue import/export, bulk photos and barcode labels (docs/08-inventory.md §2)."""

import csv
import io
import re
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import media
from app.database import Actor
from app.errors import AppError
from app.schemas.catalogue import LabelsIn, ProductIn, VariantIn
from app.services import catalogue as cat
from app.services.shop import shop_id_of

COLUMNS = [
    "name",
    "variant",
    "category",
    "brand",
    "sku",
    "barcode",
    "hsn",
    "gst_rate",
    "unit",
    "mrp",
    "sale_price",
    "cost_price",
    "opening_stock",
    "reorder_level",
    "price_includes_tax",
]
MAX_ROWS = 20_000
MAX_FILE = 10 * 1024 * 1024


def _q(db: Session, sql: str, **p: Any) -> Any:
    return db.execute(text(sql), p)


# --- reading files ---


def sheet_rows(data: bytes, filename: str) -> list[list[str]]:
    """Every row of a CSV or the first Excel sheet, as text."""
    try:
        if filename.lower().endswith((".xlsx", ".xlsm")):
            wb = load_workbook(
                io.BytesIO(data), read_only=True, data_only=True
            )  # data_only: never evaluate formulas
            rows = [
                ["" if c is None else str(c).strip() for c in r]
                for r in wb.active.iter_rows(values_only=True)
            ]
        else:
            rows = [
                [c.strip() for c in r] for r in csv.reader(io.StringIO(data.decode("utf-8-sig")))
            ]
    except (UnicodeDecodeError, zipfile.BadZipFile, OSError, KeyError):
        raise AppError("import.unreadable", "Upload a CSV or Excel (.xlsx) file.", 415) from None
    if not rows:
        raise AppError("import.empty", "The file is empty.", 400)
    return rows


def read_sheet(data: bytes, filename: str) -> list[dict[str, str]]:
    if len(data) > MAX_FILE:
        raise AppError("import.too_large", "The file is too big. Keep it under 10 MB.", 413)
    rows = sheet_rows(data, filename)
    header = [h.lower().replace(" ", "_") for h in rows[0]]
    if "name" not in header or "sale_price" not in header:
        raise AppError(
            "import.columns",
            "The file needs at least 'name' and 'sale_price' columns. Use our template.",
            400,
        )
    body = [r for r in rows[1:] if any(r)]
    if len(body) > MAX_ROWS:
        raise AppError("import.too_many", f"Import at most {MAX_ROWS:,} rows at a time.", 400)
    return [dict(zip(header, r + [""] * (len(header) - len(r)), strict=False)) for r in body]


def _dec(v: str, field: str) -> Decimal | None:
    if not v:
        return None
    try:
        return Decimal(v.replace(",", "").replace("₹", "").strip())
    except InvalidOperation:
        raise ValueError(f"{field} must be a number") from None


def _rate_id(db: Session, v: str) -> UUID | None:
    if not v:
        return None
    rate = _dec(v.rstrip("%"), "gst_rate")
    rid = _q(
        db,
        "SELECT id FROM gst_rates WHERE rate = :r AND is_active ORDER BY (kind = 'taxable') DESC, (kind = 'nil') DESC"
        " LIMIT 1",
        r=rate,
    ).scalar()
    if not rid:
        raise ValueError(f"GST rate {v} is not a current rate")
    return rid  # type: ignore[no-any-return]


def _find_variant(db: Session, shop_id: UUID, r: dict[str, str]) -> Any:
    if r.get("sku"):
        row = _q(
            db,
            "SELECT id, product_id FROM product_variants WHERE shop_id = :s AND lower(sku) = lower(:v)",
            s=shop_id,
            v=r["sku"],
        ).first()
        if row:
            return row
    if r.get("barcode"):
        row = _q(
            db,
            "SELECT id, product_id FROM product_variants WHERE shop_id = :s AND barcode = :v",
            s=shop_id,
            v=r["barcode"],
        ).first()
        if row:
            return row
    return _q(
        db,
        "SELECT v.id, v.product_id FROM product_variants v JOIN products p ON p.id = v.product_id"
        " WHERE v.shop_id = :s AND lower(p.name) = lower(:n) AND lower(coalesce(v.name, '')) = lower(:vn)"
        " AND p.deleted_at IS NULL",
        s=shop_id,
        n=r["name"],
        vn=r.get("variant", ""),
    ).first()


def import_products(
    db: Session, actor: Actor, data: bytes, filename: str, commit: bool
) -> dict[str, Any]:
    """Runs the whole import inside a savepoint; dry runs roll it back, so preview == real result."""
    sid = shop_id_of(actor)
    rows = read_sheet(data, filename)
    report: list[dict[str, Any]] = []
    creates = updates = 0
    sp = db.begin_nested()
    for i, r in enumerate(rows, start=2):  # row 1 is the header
        errors: list[str] = []
        action = "skip"
        try:
            if not r.get("name"):
                raise ValueError("name is required")
            variant = VariantIn(
                name=r.get("variant") or None,
                sku=r.get("sku") or None,
                barcode=r.get("barcode") or None,
                mrp=_dec(r.get("mrp", ""), "mrp"),
                sale_price=_dec(r.get("sale_price", ""), "sale_price") or Decimal("0"),
                cost_price=_dec(r.get("cost_price", ""), "cost_price") or Decimal("0"),
                reorder_level=_dec(r.get("reorder_level", ""), "reorder_level") or Decimal("0"),
                opening_stock=_dec(r.get("opening_stock", ""), "opening_stock") or Decimal("0"),
            )
            unit = (r.get("unit") or "NOS").upper()
            fields: dict[str, Any] = {
                "category_id": cat.category_by_name(db, sid, r["category"])
                if r.get("category")
                else None,
                "brand": r.get("brand") or None,
                "hsn_code": r.get("hsn") or None,
                "tax_rate_id": _rate_id(db, r.get("gst_rate", "")),
                "unit_code": unit,
            }
            inc = r.get("price_includes_tax", "").lower()
            if inc:
                fields["price_includes_tax"] = inc in ("yes", "y", "true", "1")
            existing = _find_variant(db, sid, r)
            with db.begin_nested():
                if existing:
                    action = "update"
                    p = cat.get_product(db, actor, existing.product_id)
                    vs = [
                        variant.model_copy(update={"id": v["id"], "sku": variant.sku or v["sku"]})
                        if v["id"] == existing.id
                        else VariantIn(
                            id=v["id"],
                            name=v["name"],
                            sku=v["sku"],
                            barcode=v["barcode"],
                            mrp=v["mrp"],
                            sale_price=v["sale_price"],
                            cost_price=v["cost_price"],
                            reorder_level=v["reorder_level"],
                        )
                        for v in p["variants"]
                    ]
                    merged = {
                        k: p[k]
                        for k in (
                            "name",
                            "category_id",
                            "brand",
                            "description",
                            "hsn_code",
                            "is_service",
                            "tax_rate_id",
                            "cess_rate",
                            "price_includes_tax",
                            "unit_code",
                            "track_stock",
                        )
                    }
                    merged.update({k: v for k, v in fields.items() if v is not None})
                    cat.update_product(
                        db, actor, existing.product_id, ProductIn(**merged, variants=vs)
                    )
                else:
                    action = "create"
                    same_name = _q(
                        db,
                        "SELECT id FROM products WHERE shop_id = :s AND lower(name) = lower(:n) AND deleted_at IS NULL",
                        s=sid,
                        n=r["name"],
                    ).scalar()
                    if same_name:  # another variant of a product already in the file or catalogue
                        p = cat.get_product(db, actor, same_name)
                        vs = [
                            VariantIn(
                                id=v["id"],
                                name=v["name"],
                                sku=v["sku"],
                                barcode=v["barcode"],
                                mrp=v["mrp"],
                                sale_price=v["sale_price"],
                                cost_price=v["cost_price"],
                                reorder_level=v["reorder_level"],
                            )
                            for v in p["variants"]
                        ] + [variant]
                        merged = {
                            k: p[k]
                            for k in (
                                "name",
                                "category_id",
                                "brand",
                                "description",
                                "hsn_code",
                                "is_service",
                                "tax_rate_id",
                                "cess_rate",
                                "price_includes_tax",
                                "unit_code",
                                "track_stock",
                            )
                        }
                        cat.update_product(db, actor, same_name, ProductIn(**merged, variants=vs))
                    else:
                        cat.create_product(
                            db, actor, ProductIn(name=r["name"], variants=[variant], **fields)
                        )
        except ValidationError as e:
            errors = [err["msg"].removeprefix("Value error, ") for err in e.errors()]
        except (ValueError, AppError) as e:
            errors = [e.detail if isinstance(e, AppError) else str(e)]
        if errors:
            action = "skip"
        elif action == "create":
            creates += 1
        elif action == "update":
            updates += 1
        report.append({"row": i, "name": r.get("name", ""), "action": action, "errors": errors})
    error_count = sum(1 for x in report if x["errors"])
    committed = commit and error_count == 0
    if committed:
        sp.commit()
    else:
        sp.rollback()  # dry run, or a commit with errors: nothing is saved
    return {
        "committed": committed,
        "creates": creates,
        "updates": updates,
        "errors": error_count,
        "rows": report,
    }


# --- writing files ---


def _workbook(rows: list[list[Any]], help_sheet: bool, db: Session) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Items"
    ws.append(COLUMNS)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="4A5AE0")
    for r in rows:
        ws.append(r)
    ws.freeze_panes = "A2"
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = max(
            12, min(40, max(len(str(c.value or "")) for c in col) + 2)
        )
    if help_sheet:
        h = wb.create_sheet("Help")
        h.append(["Column", "What to enter"])
        for line in [
            ("name", "Item name (required). Rows with the same name become variants of one item."),
            ("variant", "Size/colour, e.g. '500 g' or 'Red / M'. Leave empty for simple items."),
            (
                "sku / barcode",
                "Optional. Leave SKU empty and Anylo makes one. Existing SKU/barcode = update that item.",
            ),
            ("hsn", "4 to 8 digit HSN/SAC code."),
            (
                "gst_rate",
                "One of: "
                + ", ".join(
                    str(r)
                    for r in db.execute(
                        text("SELECT DISTINCT rate FROM gst_rates WHERE is_active ORDER BY rate")
                    ).scalars()
                ),
            ),
            (
                "unit",
                "One of: "
                + ", ".join(db.execute(text("SELECT code FROM units ORDER BY code")).scalars()),
            ),
            ("prices", "mrp, sale_price, cost_price in rupees. sale_price can't be above mrp."),
            ("price_includes_tax", "yes or no. Empty = your shop's GST setting."),
        ]:
            h.append(list(line))
        h.column_dimensions["A"].width, h.column_dimensions["B"].width = 20, 100
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def template(db: Session) -> bytes:
    sample = [
        [
            "Basmati Rice",
            "5 kg",
            "Groceries",
            "India Gate",
            "",
            "",
            "1006",
            "5",
            "BAG",
            "699",
            "650",
            "560",
            "20",
            "5",
            "yes",
        ],
        [
            "Basmati Rice",
            "1 kg",
            "Groceries",
            "India Gate",
            "",
            "",
            "1006",
            "5",
            "BAG",
            "149",
            "140",
            "118",
            "50",
            "10",
            "yes",
        ],
        [
            "Ball Pen Blue",
            "",
            "Stationery",
            "Cello",
            "",
            "",
            "9608",
            "18",
            "NOS",
            "10",
            "10",
            "6",
            "200",
            "50",
            "yes",
        ],
    ]
    return _workbook(sample, True, db)


def export(db: Session, actor: Actor) -> bytes:
    rows = _q(
        db,
        """
        SELECT p.name, v.name AS variant, c.name AS category, p.brand, v.sku, v.barcode, p.hsn_code, r.rate, p.unit_code,
          v.mrp, v.sale_price, v.cost_price, v.stock_qty, v.reorder_level, p.price_includes_tax
        FROM products p JOIN product_variants v ON v.product_id = p.id AND v.is_active
        LEFT JOIN categories c ON c.id = p.category_id LEFT JOIN gst_rates r ON r.id = p.tax_rate_id
        WHERE p.shop_id = :s AND p.deleted_at IS NULL ORDER BY lower(p.name), v.name NULLS FIRST""",
        s=shop_id_of(actor),
    )
    out = [
        ["" if x is None else str(x) if isinstance(x, Decimal) else x for x in r[:14]]
        + ["yes" if r[14] else "no"]
        for r in rows
    ]
    return _workbook(out, False, db)


# --- bulk photos ---


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def photos_zip(db: Session, actor: Actor, data: bytes) -> dict[str, list[str]]:
    sid = shop_id_of(actor)
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise AppError("import.bad_zip", "Upload a .zip file of photos.", 415) from None
    infos = [
        i
        for i in zf.infolist()
        if not i.is_dir() and Path(i.filename).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
    ]
    # Zip-bomb guard: count and declared sizes are checked before anything is decompressed.
    if len(infos) > 500 or sum(i.file_size for i in infos) > 200 * 1024 * 1024:
        raise AppError("import.zip_too_big", "Up to 500 photos and 200 MB per zip.", 413)
    by_sku = {
        r.sku.lower(): r.product_id
        for r in _q(db, "SELECT sku, product_id FROM product_variants WHERE shop_id = :s", s=sid)
    }
    by_name = {
        _slug(r.name): r.id
        for r in _q(
            db, "SELECT id, name FROM products WHERE shop_id = :s AND deleted_at IS NULL", s=sid
        )
    }
    matched: list[str] = []
    unmatched: list[str] = []
    for info in infos:
        stem = Path(info.filename).stem
        pid = by_sku.get(stem.lower()) or by_name.get(_slug(stem))
        if not pid or info.file_size > media.MAX_BYTES:
            unmatched.append(info.filename)
            continue
        try:
            cat.set_photo(db, actor, pid, zf.read(info))
            matched.append(info.filename)
        except AppError:
            unmatched.append(info.filename)
    return {"matched": matched, "unmatched": unmatched}


# --- labels ---


def _font() -> str:
    """A font with the ₹ glyph if one is installed; otherwise labels print 'Rs.'."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for path in (
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("LabelFont", path))
                return "LabelFont"
            except Exception:  # noqa: S112 - try the next candidate font
                continue
    return "Helvetica"


def labels_pdf(db: Session, actor: Actor, data: LabelsIn) -> bytes:
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode import code128, eanbc
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    ids = [i.variant_id for i in data.items]
    rows = {
        r.id: r
        for r in _q(
            db,
            "SELECT v.id, v.name AS variant, v.sku, v.barcode, v.mrp, v.sale_price, p.name"
            " FROM product_variants v JOIN products p ON p.id = v.product_id"
            " WHERE v.id = ANY(:ids) AND v.shop_id = :s",
            ids=ids,
            s=shop_id_of(actor),
        )
    }
    font = _font()
    rupee = "₹" if font != "Helvetica" else "Rs."
    layouts = {  # cols, rows, label w, label h, page size, left/top margin (mm)
        "a4_24": (3, 8, 70 * mm, 37 * mm, A4, 0, 0.5 * mm),
        "a4_65": (5, 13, 38.1 * mm, 21.2 * mm, A4, 4.7 * mm, 10.7 * mm),
        "roll_50x25": (1, 1, 50 * mm, 25 * mm, (50 * mm, 25 * mm), 0, 0),
    }
    cols, nrows, w, h, page, ml, mt = layouts[data.layout]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page)
    labels = [
        rows[i.variant_id] for i in data.items if i.variant_id in rows for _ in range(i.copies)
    ]
    small = data.layout == "a4_65"
    for n, r in enumerate(labels):
        slot = n % (cols * nrows)
        if n and slot == 0:
            c.showPage()
        x = ml + (slot % cols) * w
        y = page[1] - mt - (slot // cols + 1) * h
        pad = 1.5 * mm
        title = f"{r.name} {r.variant or ''}".strip()
        c.setFont(font, 6.5 if small else 8)
        c.drawString(x + pad, y + h - pad - 6, title[: 28 if small else 40])
        code = r.barcode or r.sku
        bc_h = h * (0.38 if small else 0.45)
        widget = (
            eanbc.Ean13BarcodeWidget(code)
            if cat.is_valid_ean13(code)
            else code128.Code128(code, barHeight=bc_h, humanReadable=True, fontSize=5)
        )
        if isinstance(widget, eanbc.Ean13BarcodeWidget):
            b = widget.getBounds()
            bw, bh = b[2] - b[0], b[3] - b[1]
            scale = min((w - 2 * pad) / bw, bc_h / bh)
            d = Drawing(bw * scale, bh * scale, transform=[scale, 0, 0, scale, 0, 0])
            d.add(widget)
            renderPDF.draw(d, c, x + pad, y + pad + (7 if not small else 5))
        else:
            widget.drawOn(c, x + pad - 4, y + pad + (7 if not small else 5))
        c.setFont(font, 7 if small else 9)
        price = f"{rupee}{r.sale_price:,.2f}"
        if data.show_mrp and r.mrp is not None and r.mrp != r.sale_price:
            price = f"MRP {rupee}{r.mrp:,.2f}  {price}"
        c.drawString(x + pad, y + pad, price)
    if not labels:
        raise AppError("labels.none", "Choose at least one item.", 400)
    c.save()
    return buf.getvalue()

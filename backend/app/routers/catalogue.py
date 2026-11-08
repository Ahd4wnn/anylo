from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import text

from app.data.presets import PRESETS
from app.deps import DB, CurrentActor, require
from app.schemas.catalogue import (
    AdjustIn,
    CategoryIn,
    CategoryOut,
    ImportResult,
    LabelsIn,
    LookupOut,
    MovementOut,
    ProductIn,
    ProductOut,
    ProductPage,
    ValuationOut,
    VariantIn,
    VariantOut,
)
from app.services import catalogue as svc
from app.services import catalogue_io as io_svc
from app.services import snap as snap_svc
from app.services.shop import shop_id_of

router = APIRouter(prefix="/v1", tags=["catalogue"])
VIEW = [Depends(require("product.view"))]
MANAGE = [Depends(require("product.manage"))]
STOCK = [Depends(require("stock.manage"))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _file(data: bytes, name: str, media_type: str) -> Response:
    return Response(
        data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# --- reference lists ---


@router.get("/units", dependencies=VIEW)
def units(db: DB) -> list[dict[str, Any]]:
    return [
        r._asdict()
        for r in db.execute(text("SELECT code, label, allows_decimal FROM units ORDER BY label"))
    ]


@router.get("/gst-rates", dependencies=VIEW)
def gst_rates(db: DB) -> list[dict[str, Any]]:
    rows = db.execute(
        text("SELECT id, label, rate, kind FROM gst_rates WHERE is_active ORDER BY rate, kind")
    )
    return [{**r._asdict(), "rate": str(r.rate)} for r in rows]


# --- categories ---


@router.get("/categories", response_model=list[CategoryOut], dependencies=VIEW)
def list_categories(actor: CurrentActor, db: DB) -> Any:
    return svc.list_categories(db, actor)


@router.post("/categories", response_model=CategoryOut, status_code=201, dependencies=MANAGE)
def create_category(data: CategoryIn, actor: CurrentActor, db: DB) -> Any:
    return svc.save_category(db, actor, data)


@router.patch("/categories/{category_id}", response_model=CategoryOut, dependencies=MANAGE)
def update_category(category_id: UUID, data: CategoryIn, actor: CurrentActor, db: DB) -> Any:
    return svc.save_category(db, actor, data, category_id)


@router.delete("/categories/{category_id}", status_code=204, dependencies=MANAGE)
def delete_category(category_id: UUID, actor: CurrentActor, db: DB) -> None:
    svc.delete_category(db, actor, category_id)


# --- products (static paths are declared before /products/{id}: PlantBill bug #10) ---


@router.get("/products", response_model=ProductPage, dependencies=VIEW)
def list_products(
    actor: CurrentActor,
    db: DB,
    q: str | None = None,
    category_id: UUID | None = None,
    low_stock: bool = False,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> Any:
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    items, total = svc.list_products(
        db,
        actor,
        q=q,
        category_id=category_id,
        low_stock=low_stock,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    nxt = offset + limit
    return {"items": items, "total": total, "next_cursor": str(nxt) if nxt < total else None}


@router.get("/products/lookup", response_model=LookupOut, dependencies=VIEW)
def lookup(code: str, actor: CurrentActor, db: DB) -> Any:
    return svc.lookup(db, actor, code)


@router.get("/products/import/template", dependencies=MANAGE)
def import_template(db: DB) -> Response:
    return _file(io_svc.template(db), "anylo-items-template.xlsx", XLSX)


@router.post("/products/import", response_model=ImportResult, dependencies=MANAGE)
async def import_products(
    file: UploadFile, actor: CurrentActor, db: DB, dry_run: bool = True
) -> Any:
    data = await file.read(io_svc.MAX_FILE + 1)
    return io_svc.import_products(
        db, actor, data, file.filename or "upload.csv", commit=not dry_run
    )


@router.get("/products/export", dependencies=MANAGE)
def export_products(actor: CurrentActor, db: DB) -> Response:
    return _file(io_svc.export(db, actor), "anylo-items.xlsx", XLSX)


@router.post("/products/photos/zip", dependencies=MANAGE)
async def photos_zip(file: UploadFile, actor: CurrentActor, db: DB) -> dict[str, list[str]]:
    return io_svc.photos_zip(db, actor, await file.read(250 * 1024 * 1024))


@router.post("/products/labels", dependencies=MANAGE)
def labels(data: LabelsIn, actor: CurrentActor, db: DB) -> Response:
    return Response(
        io_svc.labels_pdf(db, actor, data),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="anylo-labels.pdf"'},
    )


@router.post("/products/snap", dependencies=[Depends(require("product.snap"))])
async def snap(file: UploadFile, actor: CurrentActor, db: DB) -> dict[str, Any]:
    return snap_svc.snap(db, actor, await file.read(5 * 1024 * 1024 + 1), file.content_type or "")


@router.post("/products", response_model=ProductOut, status_code=201, dependencies=MANAGE)
def create_product(data: ProductIn, actor: CurrentActor, db: DB) -> Any:
    return svc.create_product(db, actor, data)


@router.get("/products/{product_id}", response_model=ProductOut, dependencies=VIEW)
def get_product(product_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return svc.get_product(db, actor, product_id)


@router.put("/products/{product_id}", response_model=ProductOut, dependencies=MANAGE)
def update_product(product_id: UUID, data: ProductIn, actor: CurrentActor, db: DB) -> Any:
    return svc.update_product(db, actor, product_id, data)


@router.delete("/products/{product_id}", status_code=204, dependencies=MANAGE)
def archive_product(product_id: UUID, actor: CurrentActor, db: DB) -> None:
    svc.set_archived(db, actor, product_id, True)


@router.post("/products/{product_id}/restore", status_code=204, dependencies=MANAGE)
def restore_product(product_id: UUID, actor: CurrentActor, db: DB) -> None:
    svc.set_archived(db, actor, product_id, False)


@router.post("/products/{product_id}/photo", response_model=ProductOut, dependencies=MANAGE)
async def upload_photo(product_id: UUID, file: UploadFile, actor: CurrentActor, db: DB) -> Any:
    return svc.set_photo(db, actor, product_id, await file.read(5 * 1024 * 1024 + 1))


@router.delete("/products/{product_id}/photo", response_model=ProductOut, dependencies=MANAGE)
def delete_photo(product_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return svc.set_photo(db, actor, product_id, None)


@router.post("/barcodes/generate", dependencies=MANAGE)
def generate_barcode(actor: CurrentActor, db: DB) -> dict[str, str]:
    return {"barcode": svc.next_ean(db, shop_id_of(actor))}


# --- stock ---


@router.post("/stock/adjustments", response_model=VariantOut, dependencies=STOCK)
def adjust(data: AdjustIn, actor: CurrentActor, db: DB) -> Any:
    return svc.adjust(db, actor, data)


@router.get("/stock/movements", response_model=list[MovementOut], dependencies=STOCK)
def movements(
    actor: CurrentActor,
    db: DB,
    variant_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    return svc.movements(db, actor, variant_id, limit, offset)


@router.get("/stock/low", response_model=ProductPage, dependencies=VIEW)
def low_stock(actor: CurrentActor, db: DB) -> Any:
    items, total = svc.list_products(
        db,
        actor,
        q=None,
        category_id=None,
        low_stock=True,
        include_archived=False,
        limit=200,
        offset=0,
    )
    return {"items": items, "total": total, "next_cursor": None}


@router.get("/stock/valuation", response_model=ValuationOut, dependencies=STOCK)
def valuation(actor: CurrentActor, db: DB) -> Any:
    return svc.valuation(db, actor)


# --- starter catalogue (onboarding) ---


@router.post("/shop/starter-products", dependencies=MANAGE)
def starter_products(actor: CurrentActor, db: DB) -> dict[str, int]:
    """Adds starter items at ₹0 for the shop type. Existing names are skipped (repeatable)."""
    sid = shop_id_of(actor)
    btype = db.execute(
        text("SELECT business_type FROM shops WHERE id = :s"), {"s": sid}
    ).scalar_one()
    have = {
        n.lower()
        for n in db.execute(
            text("SELECT name FROM products WHERE shop_id = :s"), {"s": sid}
        ).scalars()
    }
    added = 0
    produce = btype == "produce"
    exempt = (
        db.execute(text("SELECT id FROM gst_rates WHERE kind = 'exempt' LIMIT 1")).scalar()
        if produce
        else None
    )
    for name, category, unit, hsn in PRESETS.get(btype, PRESETS["general"]):
        if name.lower() in have:
            continue
        svc.create_product(
            db,
            actor,
            ProductIn(
                name=name,
                category_id=svc.category_by_name(db, sid, category),
                unit_code=unit,
                hsn_code=hsn,
                tax_rate_id=exempt,
                track_stock=not produce,
                variants=[VariantIn(sale_price=Decimal(0))],
            ),
        )
        added += 1
    return {"added": added}

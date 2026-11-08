from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response

from app.deps import DB, CurrentActor, require
from app.schemas.purchasing import (
    CountIn,
    CountLineIn,
    PaidIn,
    PurchaseIn,
    SupplierIn,
    SupplierPayIn,
)
from app.services import purchasing as svc

router = APIRouter(prefix="/v1", tags=["purchases"])
BUY = [Depends(require("purchase.manage"))]
STOCK = [Depends(require("stock.manage"))]


@router.get("/suppliers", dependencies=BUY)
def list_suppliers(actor: CurrentActor, db: DB, q: str | None = None) -> Any:
    return svc.list_suppliers(db, actor, q)


@router.post("/suppliers", status_code=201, dependencies=BUY)
def create_supplier(data: SupplierIn, actor: CurrentActor, db: DB) -> Any:
    return svc.save_supplier(db, actor, data)


@router.put("/suppliers/{supplier_id}", dependencies=BUY)
def update_supplier(supplier_id: UUID, data: SupplierIn, actor: CurrentActor, db: DB) -> Any:
    return svc.save_supplier(db, actor, data, supplier_id)


@router.delete("/suppliers/{supplier_id}", status_code=204, dependencies=BUY)
def delete_supplier(supplier_id: UUID, actor: CurrentActor, db: DB) -> None:
    svc.delete_supplier(db, actor, supplier_id)


@router.get("/suppliers/{supplier_id}/ledger", dependencies=BUY)
def supplier_ledger(supplier_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return svc.supplier_ledger(db, actor, supplier_id)


@router.post("/suppliers/{supplier_id}/payments", status_code=201, dependencies=BUY)
def pay_supplier(supplier_id: UUID, data: SupplierPayIn, actor: CurrentActor, db: DB) -> Any:
    return svc.pay_supplier(db, actor, supplier_id, data)


@router.get("/purchases", dependencies=BUY)
def list_purchases(
    actor: CurrentActor,
    db: DB,
    supplier_id: UUID | None = None,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> Any:
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    return svc.list_purchases(db, actor, supplier_id, status, limit, offset)


@router.get("/purchases/restock", dependencies=BUY)
def restock(actor: CurrentActor, db: DB) -> Any:
    return svc.restock_suggestions(db, actor)


@router.post("/purchases", status_code=201, dependencies=BUY)
def create_purchase(
    data: PurchaseIn,
    actor: CurrentActor,
    db: DB,
    response: Response,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> Any:
    if idempotency_key:
        data.idempotency_key = idempotency_key
    body, replayed = svc.create(db, actor, data)
    if replayed:
        response.status_code = 200
        response.headers["Idempotent-Replay"] = "true"
    return body


@router.get("/purchases/{purchase_id}", dependencies=BUY)
def get_purchase(purchase_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return svc.get(db, actor, purchase_id)


@router.put("/purchases/{purchase_id}", dependencies=BUY)
def update_purchase(purchase_id: UUID, data: PurchaseIn, actor: CurrentActor, db: DB) -> Any:
    return svc.update_draft(db, actor, purchase_id, data)


@router.post("/purchases/{purchase_id}/post", dependencies=BUY)
def post_purchase(purchase_id: UUID, paid: list[PaidIn], actor: CurrentActor, db: DB) -> Any:
    return svc.post(db, actor, purchase_id, paid)


@router.post("/purchases/{purchase_id}/cancel", dependencies=BUY)
def cancel_purchase(purchase_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return svc.cancel(db, actor, purchase_id)


@router.get("/stock-counts", dependencies=STOCK)
def list_counts(actor: CurrentActor, db: DB) -> Any:
    return svc.list_counts(db, actor)


@router.post("/stock-counts", status_code=201, dependencies=STOCK)
def start_count(data: CountIn, actor: CurrentActor, db: DB) -> Any:
    return svc.start_count(db, actor, data)


@router.get("/stock-counts/{count_id}", dependencies=STOCK)
def get_count(count_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return svc.get_count(db, actor, count_id)


@router.post("/stock-counts/{count_id}/lines", dependencies=STOCK)
def set_count_line(count_id: UUID, data: CountLineIn, actor: CurrentActor, db: DB) -> Any:
    return svc.set_count_line(db, actor, count_id, data)


@router.post("/stock-counts/{count_id}/post", dependencies=STOCK)
def post_count(count_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return svc.post_count(db, actor, count_id)


@router.post("/stock-counts/{count_id}/cancel", status_code=204, dependencies=STOCK)
def cancel_count(count_id: UUID, actor: CurrentActor, db: DB) -> None:
    svc.cancel_count(db, actor, count_id)

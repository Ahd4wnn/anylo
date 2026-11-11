from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response

from app.deps import DB, CurrentActor, require
from app.schemas.backoffice import CollectIn, CreditNoteIn, CustomerIn, DecideIn
from app.services import approvals, customers, returns

router = APIRouter(prefix="/v1", tags=["customers"])
VIEW = [Depends(require("customer.view"))]
MANAGE = [Depends(require("customer.manage"))]


@router.get("/customers", dependencies=VIEW)
def list_customers(
    actor: CurrentActor,
    db: DB,
    q: str | None = None,
    has_due: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> Any:
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    return customers.list_customers(db, actor, q, has_due, limit, offset)


@router.get("/customers/lookup", dependencies=VIEW)
def lookup(phone: str, actor: CurrentActor, db: DB) -> Any:
    return customers.lookup(db, actor, phone)


@router.post("/customers", status_code=201, dependencies=VIEW)
def create(data: CustomerIn, actor: CurrentActor, db: DB) -> Any:
    return customers.create(db, actor, data)


@router.get("/customers/{customer_id}", dependencies=VIEW)
def get(customer_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return customers.get(db, actor, customer_id)


@router.put("/customers/{customer_id}", dependencies=MANAGE)
def update(customer_id: UUID, data: CustomerIn, actor: CurrentActor, db: DB) -> Any:
    return customers.update(db, actor, customer_id, data)


@router.delete("/customers/{customer_id}", status_code=204, dependencies=MANAGE)
def delete(customer_id: UUID, actor: CurrentActor, db: DB) -> None:
    customers.delete(db, actor, customer_id)


@router.get("/customers/{customer_id}/ledger", dependencies=[Depends(require("customer.ledger"))])
def ledger(customer_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return customers.ledger(db, actor, customer_id)


@router.post(
    "/customers/{customer_id}/payments",
    status_code=201,
    dependencies=[Depends(require("payment.collect"))],
)
def collect(
    customer_id: UUID,
    data: CollectIn,
    actor: CurrentActor,
    db: DB,
    response: Response,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> Any:
    if idempotency_key:
        data.idempotency_key = idempotency_key
    receipt, replayed = customers.collect(db, actor, customer_id, data)
    if replayed:
        response.status_code = 200
        response.headers["Idempotent-Replay"] = "true"
    return receipt


@router.get("/approvals", dependencies=[Depends(require("approval.decide"))])
def list_approvals(actor: CurrentActor, db: DB) -> Any:
    return approvals.list_pending(db, actor)


@router.post("/approvals/{request_id}/approve", dependencies=[Depends(require("approval.decide"))])
def approve(request_id: UUID, data: DecideIn, actor: CurrentActor, db: DB) -> Any:
    return approvals.decide(db, actor, request_id, True, data.note)


@router.post("/approvals/{request_id}/reject", dependencies=[Depends(require("approval.decide"))])
def reject(request_id: UUID, data: DecideIn, actor: CurrentActor, db: DB) -> Any:
    return approvals.decide(db, actor, request_id, False, data.note)


@router.post(
    "/credit-notes", status_code=201, dependencies=[Depends(require("credit_note.create"))]
)
def create_credit_note(
    data: CreditNoteIn,
    actor: CurrentActor,
    db: DB,
    response: Response,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> Any:
    if idempotency_key:
        data.idempotency_key = idempotency_key
    body, status = returns.create(db, actor, data)
    response.status_code = status
    return body


@router.get("/credit-notes", dependencies=[Depends(require("invoice.view"))])
def list_credit_notes(
    actor: CurrentActor,
    db: DB,
    invoice_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> Any:
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    return returns.list_notes(db, actor, invoice_id, limit, offset)


@router.get("/credit-notes/{cn_id}", dependencies=[Depends(require("invoice.view"))])
def get_credit_note(cn_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return returns.get(db, actor, cn_id)

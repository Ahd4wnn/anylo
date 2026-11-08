from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response

from app.database import privileged_session
from app.deps import DB, CurrentActor, require
from app.schemas.sales import CancelIn, CartIn, CheckoutIn, HeldIn, HeldOut, InvoicePage, PreviewOut
from app.services import invoice_pdf
from app.services import sales as svc

router = APIRouter(prefix="/v1", tags=["sales"])
CREATE = [Depends(require("invoice.create"))]
VIEW = [Depends(require("invoice.view"))]


@router.post("/invoices/preview", response_model=PreviewOut, dependencies=CREATE)
def preview(data: CartIn, actor: CurrentActor, db: DB) -> Any:
    return svc.preview(db, actor, data)


@router.post("/invoices", status_code=201, dependencies=CREATE)
def checkout(
    data: CheckoutIn,
    actor: CurrentActor,
    db: DB,
    response: Response,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> Any:
    if idempotency_key:
        data.idempotency_key = idempotency_key
    receipt, replayed = svc.checkout(db, actor, data)
    if replayed:
        response.status_code = 200
        response.headers["Idempotent-Replay"] = "true"
    return receipt


@router.get("/invoices", response_model=InvoicePage, dependencies=VIEW)
def list_invoices(
    actor: CurrentActor,
    db: DB,
    frm: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    status: str | None = None,
    q: str | None = None,
    has_due: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> Any:
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    return svc.list_invoices(
        db, actor, frm=frm, to=to, status=status, q=q, has_due=has_due, limit=limit, offset=offset
    )


@router.get("/invoices/{invoice_id}", dependencies=VIEW)
def get_invoice(invoice_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return svc.receipt(db, actor, invoice_id)


@router.put("/invoices/{invoice_id}", dependencies=[Depends(require("invoice.edit"))])
def edit_invoice(invoice_id: UUID, data: CheckoutIn, actor: CurrentActor, db: DB) -> Any:
    return svc.edit(db, actor, invoice_id, data)


@router.post("/invoices/{invoice_id}/cancel", dependencies=[Depends(require("invoice.cancel"))])
def cancel_invoice(invoice_id: UUID, data: CancelIn, actor: CurrentActor, db: DB) -> Any:
    return svc.cancel(db, actor, invoice_id, data.reason)


@router.post("/invoices/{invoice_id}/handover", status_code=204, dependencies=VIEW)
def handover(invoice_id: UUID, actor: CurrentActor, db: DB) -> None:
    """Called when a bill is printed, shared or sent; after this it can no longer be edited."""
    svc.mark_handed_over(db, actor, invoice_id)


@router.get("/invoices/{invoice_id}/pdf", dependencies=VIEW)
def invoice_pdf_file(invoice_id: UUID, actor: CurrentActor, db: DB) -> Response:
    r = svc.receipt(db, actor, invoice_id)
    svc.mark_handed_over(db, actor, invoice_id)
    name = r["number"].replace("/", "-")
    return Response(
        invoice_pdf.render(r),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name}.pdf"'},
    )


@router.get("/public/invoices/{token}")
def public_invoice(token: str) -> Any:
    with (
        privileged_session() as db
    ):  # privileged: customer-facing link, the random token is the credential
        return svc.public_receipt(db, token)


@router.get("/public/invoices/{token}/pdf")
def public_invoice_pdf(token: str) -> Response:
    with (
        privileged_session() as db
    ):  # privileged: customer-facing link, the random token is the credential
        r = svc.public_receipt(db, token)
    return Response(
        invoice_pdf.render(r),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{r["number"].replace("/", "-")}.pdf"'},
    )


@router.get(
    "/held-bills", response_model=list[HeldOut], dependencies=[Depends(require("held_bill.manage"))]
)
def list_held(actor: CurrentActor, db: DB) -> Any:
    return svc.list_held(db, actor)


@router.post(
    "/held-bills",
    response_model=HeldOut,
    status_code=201,
    dependencies=[Depends(require("held_bill.manage"))],
)
def hold(data: HeldIn, actor: CurrentActor, db: DB) -> Any:
    return svc.hold(db, actor, data.label, data.payload)


@router.delete(
    "/held-bills/{held_id}", status_code=204, dependencies=[Depends(require("held_bill.manage"))]
)
def unhold(held_id: UUID, actor: CurrentActor, db: DB) -> None:
    svc.unhold(db, actor, held_id)

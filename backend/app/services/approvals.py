"""Manager approvals for a salesperson's collections, returns and day closes (docs/07-pos-billing.md §6)."""

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.database import Actor
from app.errors import AppError
from app.services import audit
from app.services.sales import _q
from app.services.shop import shop_id_of


def request(
    db: Session,
    actor: Actor,
    kind: str,
    ref_id: UUID | None,
    summary: str,
    amount: Decimal | None,
    payload: dict[str, Any] | None = None,
) -> UUID:
    rid: UUID = _q(
        db,
        "INSERT INTO approval_requests (shop_id, kind, ref_id, summary, amount, payload, requested_by, requested_by_name)"
        " VALUES (:s, :k, :r, :su, :a, CAST(:p AS jsonb), :u, (SELECT full_name FROM users WHERE id = :u)) RETURNING id",
        s=shop_id_of(actor),
        k=kind,
        r=ref_id,
        su=summary,
        a=amount,
        p=json.dumps(payload or {}, default=str),
        u=actor.user_id,
    ).scalar_one()
    return rid


def list_pending(db: Session, actor: Actor) -> list[dict[str, Any]]:
    rows = _q(
        db,
        "SELECT id, kind, ref_id, summary, amount, requested_by_name, created_at FROM approval_requests"
        " WHERE shop_id = :s AND status = 'pending' ORDER BY created_at",
        s=shop_id_of(actor),
    ).mappings()
    return [dict(r) for r in rows]


def decide(
    db: Session, actor: Actor, request_id: UUID, approve: bool, note: str | None
) -> dict[str, Any]:
    from app.services import backoffice, customers, returns  # they import request() from here

    r = _q(
        db,
        "SELECT * FROM approval_requests WHERE id = :i AND shop_id = :s FOR UPDATE",
        i=request_id,
        s=shop_id_of(actor),
    ).first()
    if not r:
        raise AppError("approval.not_found", "This request was not found.", 404)
    if r.status != "pending":
        raise AppError("approval.decided", "This request was already decided.", 409)
    result: dict[str, Any] | None = None
    if r.kind == "collection":
        customers.decide_collection(db, actor, r.ref_id, approve)
    elif r.kind == "cash_close":
        backoffice.decide_close(db, actor, r.ref_id, approve)
    elif r.kind == "return" and approve:
        result = returns.create_from_payload(db, actor, r.payload, requested_by=r.requested_by)
    _q(
        db,
        "UPDATE approval_requests SET status = :st, decided_by = :u, decided_at = now(), note = :n WHERE id = :i",
        st="approved" if approve else "rejected",
        u=actor.user_id,
        n=note,
        i=request_id,
    )
    audit.record(
        db,
        actor,
        "approval",
        request_id,
        "approve" if approve else "reject",
        None,
        {"kind": r.kind},
    )
    return {"id": request_id, "status": "approved" if approve else "rejected", "result": result}

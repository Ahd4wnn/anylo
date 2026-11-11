"""Books & compliance: bank, capital, filings, fixed assets, year locks, balance sheet (M7)."""

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile

from app.deps import DB, CurrentActor, require
from app.schemas.books import (
    AssetIn,
    BankIn,
    BooksSettingsIn,
    FilingIn,
    LockIn,
    MatchIn,
    OwnerMoneyIn,
    SellIn,
)
from app.services import books
from app.services.catalogue_io import MAX_FILE

router = APIRouter(prefix="/v1/books", tags=["books"])
VIEW = [Depends(require("books.view"))]
MANAGE = [Depends(require("books.manage"))]
LOCK = [Depends(require("books.lock"))]
AsOf = Annotated[date | None, Query(alias="as_of")]


@router.get("/settings", dependencies=VIEW)
def get_settings(actor: CurrentActor, db: DB) -> Any:
    return books.settings(db, actor)


@router.put("/settings", dependencies=LOCK)
def put_settings(body: BooksSettingsIn, actor: CurrentActor, db: DB) -> Any:
    return books.update_settings(db, actor, body.books_start, body.opening_cash)


@router.get("/banks", dependencies=VIEW)
def list_banks(actor: CurrentActor, db: DB) -> Any:
    return books.banks(db, actor)


@router.post("/banks", status_code=201, dependencies=MANAGE)
def add_bank(body: BankIn, actor: CurrentActor, db: DB) -> Any:
    return books.add_bank(
        db, actor, body.name, body.account_last4, body.opening_balance, body.is_default
    )


@router.delete("/banks/{bank_id}", status_code=204, dependencies=MANAGE)
def delete_bank(bank_id: UUID, actor: CurrentActor, db: DB) -> None:
    books.delete_bank(db, actor, bank_id)


@router.post("/banks/{bank_id}/statement", dependencies=MANAGE)
async def import_statement(bank_id: UUID, file: UploadFile, actor: CurrentActor, db: DB) -> Any:
    data = await file.read(MAX_FILE + 1)
    return books.import_statement(db, actor, bank_id, data, file.filename or "statement.csv")


@router.get("/banks/{bank_id}/reconciliation", dependencies=VIEW)
def reconciliation(bank_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return books.reconciliation(db, actor, bank_id)


@router.put("/bank-lines/{line_id}/match", dependencies=MANAGE)
def match(line_id: UUID, body: MatchIn, actor: CurrentActor, db: DB) -> Any:
    return books.match_line(db, actor, line_id, body.payment_id)


@router.get("/owner", dependencies=VIEW)
def owner_money(actor: CurrentActor, db: DB) -> Any:
    return books.owner_money(db, actor)


# Only the owner puts in or takes out their own money.
@router.post("/owner", status_code=201, dependencies=LOCK)
def add_owner_money(body: OwnerMoneyIn, actor: CurrentActor, db: DB) -> Any:
    return books.add_owner_money(
        db, actor, body.kind, body.amount, body.method, body.on, body.note, body.bank_account_id
    )


@router.delete("/owner/{payment_id}", dependencies=LOCK)
def delete_owner_money(payment_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return books.delete_owner_money(db, actor, payment_id)


@router.get("/calendar", dependencies=VIEW)
def calendar(actor: CurrentActor, db: DB) -> Any:
    return books.calendar(db, actor)


@router.get("/filings", dependencies=VIEW)
def filings(actor: CurrentActor, db: DB) -> Any:
    return books.filings(db, actor)


@router.post("/filings", status_code=201, dependencies=MANAGE)
def add_filing(body: FilingIn, actor: CurrentActor, db: DB) -> Any:
    return books.add_filing(
        db,
        actor,
        body.return_type,
        body.period,
        body.filed_on,
        body.arn,
        body.tax_paid,
        body.method,
        body.note,
    )


@router.delete("/filings/{filing_id}", dependencies=MANAGE)
def delete_filing(filing_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return books.delete_filing(db, actor, filing_id)


@router.get("/assets", dependencies=VIEW)
def assets(actor: CurrentActor, db: DB, as_of: AsOf = None) -> Any:
    return books.assets(db, actor, as_of)


@router.post("/assets", status_code=201, dependencies=MANAGE)
def add_asset(body: AssetIn, actor: CurrentActor, db: DB) -> Any:
    return books.add_asset(
        db, actor, body.name, body.block, body.cost, body.bought_on, body.paid_method
    )


@router.post("/assets/{asset_id}/sell", dependencies=MANAGE)
def sell_asset(asset_id: UUID, body: SellIn, actor: CurrentActor, db: DB) -> Any:
    return books.sell_asset(db, actor, asset_id, body.sold_on, body.sale_value, body.method)


@router.delete("/assets/{asset_id}", dependencies=MANAGE)
def delete_asset(asset_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return books.delete_asset(db, actor, asset_id)


@router.get("/locks", dependencies=VIEW)
def locks(actor: CurrentActor, db: DB) -> Any:
    return books.locks(db, actor)


@router.post("/locks", dependencies=LOCK)
def lock(body: LockIn, actor: CurrentActor, db: DB) -> Any:
    return books.lock_year(db, actor, body.fy)


@router.delete("/locks/{fy}", dependencies=LOCK)
def unlock(fy: str, actor: CurrentActor, db: DB) -> Any:
    return books.unlock_year(db, actor, fy)


@router.get("/position", dependencies=VIEW)
def position(actor: CurrentActor, db: DB, as_of: AsOf = None) -> Any:
    return books.position(db, actor, as_of)

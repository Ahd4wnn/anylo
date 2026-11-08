from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.deps import DB, CurrentActor, require
from app.schemas.backoffice import (
    AttendanceIn,
    BorrowingIn,
    CategoryNameIn,
    CloseIn,
    ExpenseIn,
    LabourPayIn,
    RepayIn,
    WorkerIn,
)
from app.services import backoffice, labour

router = APIRouter(prefix="/v1", tags=["money"])
From = Annotated[date | None, Query(alias="from")]


def need(p: str) -> list[Any]:
    return [Depends(require(p))]


# expenses
@router.get("/expenses/categories", dependencies=need("expense.create"))
def expense_categories(actor: CurrentActor, db: DB) -> Any:
    return backoffice.categories(db, actor)


@router.post("/expenses/categories", status_code=201, dependencies=need("expense.manage"))
def add_expense_category(data: CategoryNameIn, actor: CurrentActor, db: DB) -> Any:
    return backoffice.add_category(db, actor, data.name)


@router.delete(
    "/expenses/categories/{category_id}", status_code=204, dependencies=need("expense.manage")
)
def delete_expense_category(category_id: UUID, actor: CurrentActor, db: DB) -> None:
    backoffice.delete_category(db, actor, category_id)


@router.get("/expenses", dependencies=need("expense.create"))
def list_expenses(
    actor: CurrentActor,
    db: DB,
    frm: From = None,
    to: date | None = None,
    category_id: UUID | None = None,
) -> Any:
    return backoffice.list_expenses(db, actor, frm, to, category_id)


@router.post("/expenses", status_code=201, dependencies=need("expense.create"))
def create_expense(data: ExpenseIn, actor: CurrentActor, db: DB) -> Any:
    return backoffice.create_expense(db, actor, data)


@router.put("/expenses/{expense_id}", dependencies=need("expense.manage"))
def update_expense(expense_id: UUID, data: ExpenseIn, actor: CurrentActor, db: DB) -> Any:
    return backoffice.update_expense(db, actor, expense_id, data)


@router.delete("/expenses/{expense_id}", status_code=204, dependencies=need("expense.manage"))
def delete_expense(expense_id: UUID, actor: CurrentActor, db: DB) -> None:
    backoffice.delete_expense(db, actor, expense_id)


# labour
@router.get("/labour/workers", dependencies=need("labour.attendance"))
def list_workers(actor: CurrentActor, db: DB, include_inactive: bool = False) -> Any:
    return labour.list_workers(db, actor, include_inactive)


@router.post("/labour/workers", status_code=201, dependencies=need("labour.manage"))
def create_worker(data: WorkerIn, actor: CurrentActor, db: DB) -> Any:
    return labour.create_worker(db, actor, data)


@router.put("/labour/workers/{worker_id}", dependencies=need("labour.manage"))
def update_worker(worker_id: UUID, data: WorkerIn, actor: CurrentActor, db: DB) -> Any:
    return labour.update_worker(db, actor, worker_id, data)


@router.delete("/labour/workers/{worker_id}", status_code=204, dependencies=need("labour.manage"))
def delete_worker(worker_id: UUID, actor: CurrentActor, db: DB) -> None:
    labour.delete_worker(db, actor, worker_id)


@router.get("/labour/workers/{worker_id}/statement", dependencies=need("labour.manage"))
def statement(worker_id: UUID, actor: CurrentActor, db: DB) -> Any:
    return labour.statement(db, actor, worker_id)


@router.get("/labour/attendance", dependencies=need("labour.attendance"))
def attendance(actor: CurrentActor, db: DB, day: date | None = None) -> Any:
    return labour.attendance(db, actor, day)


@router.post("/labour/attendance", dependencies=need("labour.attendance"))
def mark(data: AttendanceIn, actor: CurrentActor, db: DB) -> Any:
    return labour.mark(db, actor, data)


@router.get("/labour/payments", dependencies=need("labour.manage"))
def labour_payments(
    actor: CurrentActor,
    db: DB,
    worker_id: UUID | None = None,
    frm: From = None,
    to: date | None = None,
) -> Any:
    return labour.payments(db, actor, worker_id, frm, to)


@router.post("/labour/payments", status_code=201, dependencies=need("labour.manage"))
def pay(data: LabourPayIn, actor: CurrentActor, db: DB) -> Any:
    return labour.pay(db, actor, data)


@router.delete("/labour/payments/{payment_id}", status_code=204, dependencies=need("labour.manage"))
def delete_labour_payment(payment_id: UUID, actor: CurrentActor, db: DB) -> None:
    labour.delete_payment(db, actor, payment_id)


# borrowings
@router.get("/borrowings", dependencies=need("borrowing.manage"))
def list_borrowings(actor: CurrentActor, db: DB) -> Any:
    return backoffice.list_borrowings(db, actor)


@router.post("/borrowings", status_code=201, dependencies=need("borrowing.manage"))
def create_borrowing(data: BorrowingIn, actor: CurrentActor, db: DB) -> Any:
    return backoffice.create_borrowing(db, actor, data)


@router.post("/borrowings/{borrowing_id}/repay", dependencies=need("borrowing.manage"))
def repay(borrowing_id: UUID, data: RepayIn, actor: CurrentActor, db: DB) -> Any:
    return backoffice.repay(db, actor, borrowing_id, data)


@router.delete("/borrowings/{borrowing_id}", status_code=204, dependencies=need("borrowing.manage"))
def delete_borrowing(borrowing_id: UUID, actor: CurrentActor, db: DB) -> None:
    backoffice.delete_borrowing(db, actor, borrowing_id)


# cash
@router.get("/cash/today", dependencies=need("cash.view_today"))
def cash_today(actor: CurrentActor, db: DB) -> Any:
    return backoffice.cash_day(db, actor)


@router.post("/cash/close", dependencies=need("cash.close"))
def close_day(data: CloseIn, actor: CurrentActor, db: DB) -> Any:
    return backoffice.close_day(db, actor, data)


@router.get("/cash/closes", dependencies=need("cash.book"))
def closes(actor: CurrentActor, db: DB) -> Any:
    return backoffice.closes(db, actor)


@router.get("/cash/book", dependencies=need("cash.book"))
def day_book(actor: CurrentActor, db: DB, frm: From = None, to: date | None = None) -> Any:
    return backoffice.day_book(db, actor, frm, to)

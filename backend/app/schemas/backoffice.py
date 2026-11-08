"""Customers, collections, approvals, returns, expenses, labour, borrowings and cash (docs/05-api.md)."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.money import Money, Qty
from app.services.gst.india import STATES, is_valid_gstin


def _phone(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    v = v.strip().replace(" ", "")
    if not (len(v) == 10 and v.isdigit() and v[0] in "6789"):
        raise ValueError("Enter a 10-digit mobile number.")
    return v


class CustomerIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    phone: str | None = None
    email: str | None = Field(default=None, max_length=200)
    gstin: str | None = None
    billing_address: str | None = Field(default=None, max_length=300)
    state_code: str | None = None
    credit_limit: Money | None = Field(default=None, ge=0)
    opening_balance: Money = Decimal("0")
    notes: str | None = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=10)

    _p = field_validator("phone")(_phone)

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v: str | None) -> str | None:
        if not v:
            return None
        v = v.strip().upper()
        if not is_valid_gstin(v):
            raise ValueError("This GSTIN doesn't look right.")
        return v

    @field_validator("state_code")
    @classmethod
    def _state(cls, v: str | None) -> str | None:
        if v and v not in STATES:
            raise ValueError("Unknown state.")
        return v or None


class CollectIn(BaseModel):
    amount: Money = Field(gt=0)
    method: Literal["cash", "upi", "card", "bank", "cheque"] = "cash"
    reference: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=80)
    approval_pin: str | None = Field(default=None, min_length=4, max_length=6, pattern=r"^[0-9]+$")


class DecideIn(BaseModel):
    note: str | None = Field(default=None, max_length=200)


class ReturnLineIn(BaseModel):
    invoice_line_id: UUID
    qty: Qty = Field(gt=0)


class CreditNoteIn(BaseModel):
    invoice_id: UUID
    lines: list[ReturnLineIn] = Field(min_length=1, max_length=300)
    refund_method: Literal["cash", "upi", "store_credit"] = "cash"
    restock: bool = True
    note: str | None = Field(default=None, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=80)
    approval_pin: str | None = Field(default=None, min_length=4, max_length=6, pattern=r"^[0-9]+$")


class CategoryNameIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class ExpenseIn(BaseModel):
    category_id: UUID | None = None
    category_name: str | None = Field(default=None, max_length=60)
    amount: Money = Field(gt=0)
    method: Literal["cash", "upi", "card", "bank", "cheque"] = "cash"
    gst_amount: Money | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=300)
    occurred_on: date | None = None


class WorkerIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = None
    aadhaar_last4: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    gender: Literal["male", "female", "other"]
    wage_type: Literal["daily", "monthly"] = "daily"
    daily_wage: Money = Field(default=Decimal("0"), ge=0)
    monthly_wage: Money = Field(default=Decimal("0"), ge=0)
    paid_leaves_per_month: int = Field(default=0, ge=0, le=31)
    joined_on: date | None = None
    is_active: bool = True

    _p = field_validator("phone")(_phone)


class AttendanceIn(BaseModel):
    labourer_id: UUID
    day: date
    status: Literal["present", "half_day", "absent"]


class LabourPayIn(BaseModel):
    labourer_id: UUID
    kind: Literal["wage", "advance", "due_clear"] = "wage"
    cash_amount: Money = Field(default=Decimal("0"), ge=0)
    upi_amount: Money = Field(default=Decimal("0"), ge=0)
    days: Decimal | None = Field(default=None, ge=0, le=366)
    note: str | None = Field(default=None, max_length=200)
    paid_on: date | None = None


class BorrowingIn(BaseModel):
    lender_name: str = Field(min_length=1, max_length=120)
    lender_phone: str | None = None
    principal: Money = Field(gt=0)
    received_method: Literal["cash", "upi", "bank", "cheque"] = "cash"
    interest_note: str | None = Field(default=None, max_length=200)
    borrowed_on: date | None = None

    _p = field_validator("lender_phone")(_phone)


class RepayIn(BaseModel):
    amount: Money = Field(gt=0)
    method: Literal["cash", "upi", "bank", "cheque"] = "cash"
    note: str | None = Field(default=None, max_length=200)


class CloseIn(BaseModel):
    counted_cash: Money = Field(ge=0)
    note: str | None = Field(default=None, max_length=300)

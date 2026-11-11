from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.money import Money

Method = Literal["cash", "upi", "card", "bank", "cheque"]


class BooksSettingsIn(BaseModel):
    books_start: date | None = None
    opening_cash: Money = Field(default=Decimal("0"), ge=0)


class BankIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    account_last4: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    opening_balance: Money = Decimal("0")
    is_default: bool = False


class MatchIn(BaseModel):
    payment_id: UUID | None = None  # None unmatches


class OwnerMoneyIn(BaseModel):
    kind: Literal["capital", "drawing"]
    amount: Money = Field(gt=0)
    method: Method = "cash"
    on: date | None = None
    note: str | None = Field(default=None, max_length=200)
    bank_account_id: UUID | None = None


class FilingIn(BaseModel):
    return_type: Literal[
        "GSTR1", "GSTR3B", "CMP08", "GSTR4", "GSTR9", "ITR", "ADVANCE_TAX", "TDS", "OTHER"
    ]
    period: str = Field(min_length=1, max_length=40)
    filed_on: date
    arn: str | None = Field(default=None, max_length=40)
    tax_paid: Money = Field(default=Decimal("0"), ge=0)
    method: Method = "bank"
    note: str | None = Field(default=None, max_length=200)


class AssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    block: Literal["furniture", "plant", "computer", "vehicle", "building"]
    cost: Money = Field(gt=0)
    bought_on: date
    paid_method: Literal["cash", "upi", "bank", "cheque"] | None = None


class SellIn(BaseModel):
    sold_on: date
    sale_value: Money = Field(ge=0)
    method: Method = "cash"


class LockIn(BaseModel):
    fy: str = Field(pattern=r"^\d{4}-\d{2}$")

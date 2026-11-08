"""Suppliers, purchases, supplier payments and stock counts (docs/08-inventory.md §4, §6)."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.money import Money, Qty
from app.services.gst.india import STATES, is_valid_gstin


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    gstin: str | None = None
    phone: str | None = Field(default=None, max_length=15)
    email: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=300)
    state_code: str | None = None
    opening_balance: Money = Decimal("0")

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


class PurchaseLineIn(BaseModel):
    variant_id: UUID
    qty: Qty = Field(gt=0)
    unit_cost: Money = Field(
        ge=0, description="Rate per unit before GST, as on the supplier's bill"
    )
    discount: Money = Field(default=Decimal("0"), ge=0)
    tax_rate_id: UUID | None = Field(default=None, description="Defaults to the item's GST rate")


class PaidIn(BaseModel):
    method: Literal["cash", "upi", "bank", "cheque"]
    amount: Money = Field(gt=0)
    reference: str | None = Field(default=None, max_length=60)


class PurchaseIn(BaseModel):
    supplier_id: UUID
    supplier_invoice_no: str | None = Field(default=None, max_length=40)
    supplier_invoice_date: date | None = None
    lines: list[PurchaseLineIn] = Field(min_length=1, max_length=300)
    itc_eligible: bool = True
    notes: str | None = Field(default=None, max_length=300)
    post: bool = Field(
        default=False, description="Post now (stock in, costs updated) instead of saving a draft"
    )
    paid: list[PaidIn] = Field(default_factory=list, max_length=4)
    idempotency_key: str = Field(min_length=8, max_length=80)


class SupplierPayIn(BaseModel):
    amount: Money = Field(gt=0)
    method: Literal["cash", "upi", "bank", "cheque"] = "cash"
    reference: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=200)


class CountIn(BaseModel):
    name: str = Field(default="Stock count", min_length=1, max_length=80)
    category_id: UUID | None = None


class CountLineIn(BaseModel):
    variant_id: UUID | None = None
    code: str | None = Field(
        default=None, max_length=60, description="Barcode or SKU, for scanning"
    )
    counted_qty: Qty | None = Field(default=None, ge=0)
    add: Qty | None = Field(default=None, gt=0, description="Scanning adds this to the count")

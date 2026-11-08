from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.money import Money, Qty
from app.services.gst.india import STATES, is_valid_gstin


class CustomLine(BaseModel):
    """A one-off line, not saved to the catalogue (PlantBill's Quick Add polluted it)."""

    name: str = Field(min_length=1, max_length=120)
    hsn_code: str | None = Field(default=None, pattern=r"^[0-9]{4,8}$")
    tax_rate_id: UUID | None = None
    unit_code: str = "NOS"
    price_includes_tax: bool | None = None


class LineIn(BaseModel):
    variant_id: UUID | None = None
    custom: CustomLine | None = None
    qty: Qty = Field(gt=0)
    unit_price: Money | None = Field(
        default=None, ge=0, description="Defaults to the item's selling price"
    )
    line_discount: Money = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def _one_source(self) -> "LineIn":
        if (self.variant_id is None) == (self.custom is None):
            raise ValueError("Each line needs either an item or a custom entry.")
        if self.custom and self.unit_price is None:
            raise ValueError("Enter a price for custom items.")
        return self


class CustomerIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, pattern=r"^[6-9][0-9]{9}$")
    gstin: str | None = None
    address: str | None = Field(default=None, max_length=300)

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        v = v.strip().upper()
        if not is_valid_gstin(v):
            raise ValueError("The customer's GSTIN is not valid.")
        return v


class PaymentIn(BaseModel):
    method: Literal["cash", "upi", "card"]
    amount: Money = Field(gt=0)
    reference: str | None = Field(default=None, max_length=60)


class CartIn(BaseModel):
    lines: list[LineIn] = Field(min_length=1, max_length=300)
    customer: CustomerIn | None = None
    discount_type: Literal["flat", "percent"] | None = None
    discount_value: Money = Field(default=Decimal("0"), ge=0)
    delivery_mode: Literal["counter", "dispatched"] = "counter"
    delivery_state_code: str | None = None
    delivery_address: str | None = Field(default=None, max_length=300)
    remarks: str | None = Field(default=None, max_length=300)

    @field_validator("delivery_state_code")
    @classmethod
    def _state(cls, v: str | None) -> str | None:
        if v and v not in STATES:
            raise ValueError("Unknown state.")
        return v


class CheckoutIn(CartIn):
    payments: list[PaymentIn] = Field(default_factory=list, max_length=5)
    idempotency_key: str = Field(min_length=8, max_length=80)
    approval_pin: str | None = Field(
        default=None,
        pattern=r"^[0-9]{4,6}$",
        description="Manager PIN for discounts over the limit",
    )


class PreviewLine(BaseModel):
    name: str
    qty: Qty
    unit_price: Money
    taxable: Money
    tax_rate: Decimal
    cgst: Money
    sgst: Money
    igst: Money
    line_total: Money


class PreviewOut(BaseModel):
    doc_type: str
    supply_type: str
    place_of_supply: str
    lines: list[PreviewLine]
    subtotal_gross: Money
    discount_total: Money
    taxable_total: Money
    cgst_total: Money
    sgst_total: Money
    igst_total: Money
    cess_total: Money
    round_off: Money
    grand_total: Money
    needs_approval: bool


class InvoiceSummary(BaseModel):
    id: UUID
    number: str
    doc_type: str
    issued_at: datetime
    buyer_name: str | None
    buyer_phone: str | None
    grand_total: Money
    paid_total: Money
    due_total: Money
    status: str
    created_by_name: str | None
    methods: list[str]


class InvoicePage(BaseModel):
    items: list[InvoiceSummary]
    next_cursor: str | None
    total: int
    sales_total: Money


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


class HeldIn(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    payload: dict[str, Any]


class HeldOut(BaseModel):
    id: UUID
    label: str
    payload: dict[str, Any]
    created_by_name: str | None
    created_at: datetime

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.money import Money, Qty


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    sort_order: int = 0


class CategoryOut(BaseModel):
    id: UUID
    name: str
    sort_order: int
    product_count: int = 0


class VariantIn(BaseModel):
    id: UUID | None = None
    name: str | None = Field(default=None, max_length=60)
    sku: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9._/\-]+$")
    barcode: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9\-]+$")
    mrp: Money | None = None
    sale_price: Money = Field(ge=0)
    cost_price: Money = Field(default=Decimal("0"), ge=0)
    reorder_level: Qty = Field(default=Decimal("0"), ge=0)
    opening_stock: Qty = Field(
        default=Decimal("0"), ge=0, description="Only used when the variant is created"
    )

    @model_validator(mode="after")
    def _mrp(self) -> "VariantIn":
        if self.mrp is not None and self.sale_price > self.mrp:
            raise ValueError("Selling price can't be more than the MRP.")
        return self


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category_id: UUID | None = None
    brand: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=1000)
    hsn_code: str | None = Field(default=None, pattern=r"^[0-9]{4,8}$")
    is_service: bool = False
    tax_rate_id: UUID | None = None
    cess_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    price_includes_tax: bool | None = Field(
        default=None, description="Defaults to the shop's GST setting"
    )
    unit_code: str = "NOS"
    track_stock: bool = True
    variants: list[VariantIn] = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def _unique(self) -> "ProductIn":
        names = [(v.name or "").strip().lower() for v in self.variants]
        if len(set(names)) != len(names):
            raise ValueError("Each variant needs a different name.")
        if self.is_service:
            self.track_stock = False
        return self


class VariantOut(BaseModel):
    id: UUID
    name: str | None
    sku: str
    barcode: str | None
    mrp: Money | None
    sale_price: Money
    cost_price: Money
    reorder_level: Qty
    stock_qty: Qty
    is_active: bool


class ProductOut(BaseModel):
    id: UUID
    name: str
    category_id: UUID | None
    category_name: str | None
    brand: str | None
    description: str | None
    hsn_code: str | None
    is_service: bool
    tax_rate_id: UUID | None
    tax_rate: Decimal | None
    cess_rate: Decimal
    price_includes_tax: bool
    unit_code: str
    track_stock: bool
    photo_url: str | None
    thumb_url: str | None
    archived: bool
    missing_tax_info: bool = Field(
        description="True when a regular-GST shop has no rate/HSN for this item"
    )
    variants: list[VariantOut]
    updated_at: datetime


class ProductPage(BaseModel):
    items: list[ProductOut]
    next_cursor: str | None
    total: int


class LookupOut(BaseModel):
    product: ProductOut
    variant: VariantOut


class AdjustIn(BaseModel):
    variant_id: UUID
    mode: Literal["set", "add", "remove"] = Field(
        description="set = counted quantity; add/remove = change"
    )
    qty: Qty = Field(ge=0)
    kind: Literal["adjustment", "damage", "opening"] = "adjustment"
    reason: str | None = Field(default=None, max_length=200)


class MovementOut(BaseModel):
    id: int
    variant_id: UUID
    product_name: str
    variant_name: str | None
    kind: str
    qty: Qty
    unit_cost: Money
    reason: str | None
    created_by_name: str | None
    created_at: datetime


class ValuationRow(BaseModel):
    category: str
    items: int
    quantity: Qty
    value: Money


class ValuationOut(BaseModel):
    rows: list[ValuationRow]
    total_value: Money


class ImportRow(BaseModel):
    row: int
    name: str
    action: Literal["create", "update", "skip"]
    errors: list[str]


class ImportResult(BaseModel):
    committed: bool
    creates: int
    updates: int
    errors: int
    rows: list[ImportRow]


class LabelItem(BaseModel):
    variant_id: UUID
    copies: int = Field(default=1, ge=1, le=500)


class LabelsIn(BaseModel):
    items: list[LabelItem] = Field(min_length=1, max_length=500)
    layout: Literal["a4_65", "a4_24", "roll_50x25"] = "a4_24"
    show_mrp: bool = True

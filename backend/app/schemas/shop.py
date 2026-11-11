from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.auth import PHONE, BusinessType
from app.services.gst.india import STATES, is_valid_gstin

UPI = r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$"


class ShopPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    business_type: BusinessType | None = None
    phone: str | None = Field(default=None, pattern=PHONE)
    email: EmailStr | None = None
    address_line1: str | None = Field(default=None, max_length=120)
    address_line2: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=60)
    pincode: str | None = Field(default=None, pattern=r"^[1-9][0-9]{5}$")
    upi_vpa: str | None = Field(default=None, pattern=UPI)
    upi_payee_name: str | None = Field(default=None, max_length=60)
    settings: dict[str, Any] | None = None


class TaxProfileIn(BaseModel):
    gst_scheme: Literal["regular", "composition", "unregistered"]
    gstin: str | None = None
    legal_name: str | None = Field(default=None, max_length=120)
    trade_name: str | None = Field(default=None, max_length=120)
    composition_rate: Decimal | None = Field(default=None, ge=0, le=10)
    prices_include_tax: bool = True
    hsn_digits_required: Literal[4, 6] = 4
    invoice_round_off: bool = True
    einvoice_applicable: bool = False
    filing_frequency: Literal["monthly", "qrmp"] = "monthly"

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip().upper()
        if not is_valid_gstin(v):
            raise ValueError("This GSTIN is not valid. Check the 15 characters.")
        return v

    @model_validator(mode="after")
    def _scheme_needs_gstin(self) -> "TaxProfileIn":
        if self.gst_scheme != "unregistered" and not self.gstin:
            raise ValueError("Enter your GSTIN, or choose 'Not registered for GST'.")
        if self.gst_scheme == "unregistered":
            self.gstin = None
        if self.gst_scheme == "composition" and self.composition_rate is None:
            self.composition_rate = Decimal("1.00")
        return self


class TaxProfileOut(TaxProfileIn):
    pass


class ShopOut(BaseModel):
    id: UUID
    name: str
    business_type: str
    phone: str | None
    email: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    pincode: str | None
    state_code: str
    state_name: str
    logo_url: str | None
    upi_vpa: str | None
    upi_payee_name: str | None
    settings: dict[str, Any]
    onboarding_completed_at: datetime | None
    tax: TaxProfileOut


class OnboardingOut(BaseModel):
    details: bool
    tax: bool
    logo: bool
    upi: bool
    staff: bool
    products: bool
    completed: bool


class NewShopIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    business_type: BusinessType = "general"
    state_code: str

    @field_validator("state_code")
    @classmethod
    def _state(cls, v: str) -> str:
        if v not in STATES:
            raise ValueError("unknown state")
        return v


StaffRole = Literal["manager", "salesperson", "accountant"]


class StaffIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    phone: str | None = Field(default=None, pattern=PHONE)
    role: StaffRole = "salesperson"


class StaffPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=80)
    role: StaffRole | None = None
    is_active: bool | None = None


class StaffOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    role: str
    is_active: bool
    last_login_at: datetime | None
    must_change_password: bool


class StaffCreated(StaffOut):
    temporary_password: str = Field(
        description="Shown once. The user must change it at first login."
    )

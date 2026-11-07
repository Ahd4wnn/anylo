from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.services.gst.india import STATES

BusinessType = Literal[
    "general",
    "grocery",
    "apparel",
    "electronics",
    "hardware",
    "pharmacy",
    "stationery",
    "nursery",
    "other",
]
Platform = Literal["web", "android", "ios"]
PHONE = r"^[6-9][0-9]{9}$"


class SignupIn(BaseModel):
    shop_name: str = Field(min_length=2, max_length=80)
    owner_name: str = Field(min_length=2, max_length=80)
    phone: str = Field(pattern=PHONE)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    business_type: BusinessType = "general"
    state_code: str
    platform: Platform = "web"

    @field_validator("state_code")
    @classmethod
    def _state(cls, v: str) -> str:
        if v not in STATES:
            raise ValueError("unknown state")
        return v

    @field_validator("shop_name", "owner_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class LoginIn(BaseModel):
    login: str = Field(min_length=3, max_length=254, description="Email or 10-digit mobile")
    password: str = Field(min_length=1, max_length=128)
    platform: Platform = "web"
    device_label: str | None = Field(default=None, max_length=80)


class RefreshIn(BaseModel):
    refresh_token: str | None = Field(default=None, description="Mobile only; web uses the cookie")


class TokensOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_in: int
    refresh_token: str | None = Field(default=None, description="Returned to mobile clients only")


class ShopBrief(BaseModel):
    id: UUID
    name: str


class SubscriptionBrief(BaseModel):
    status: str
    trial_ends_at: datetime
    days_left: int | None
    read_only: bool


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    phone: str | None
    role: str
    preferred_language: str
    must_change_password: bool


class MeOut(BaseModel):
    user: UserOut
    onboarding_completed: bool
    shops: list[ShopBrief]
    active_shop_id: UUID | None
    subscription: SubscriptionBrief | None
    permissions: list[str]


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    platform: Platform = "web"


class PinIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    pin: str = Field(pattern=r"^[0-9]{4,6}$")


class SessionOut(BaseModel):
    id: UUID
    device_label: str | None
    platform: str | None
    created_at: datetime
    last_used_at: datetime

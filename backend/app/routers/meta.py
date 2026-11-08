from fastapi import APIRouter
from pydantic import BaseModel

from app.services.gst.india import STATES

router = APIRouter(prefix="/v1/meta", tags=["meta"])


class Option(BaseModel):
    value: str
    label: str


class ReferenceOut(BaseModel):
    states: list[Option]
    business_types: list[Option]


BUSINESS_TYPES = [
    ("general", "General store"),
    ("grocery", "Grocery / Kirana"),
    ("apparel", "Clothing & apparel"),
    ("electronics", "Electronics & mobiles"),
    ("hardware", "Hardware & paints"),
    ("pharmacy", "Pharmacy"),
    ("stationery", "Stationery & books"),
    ("nursery", "Plant nursery"),
    ("produce", "Vegetables & fruits"),
    ("other", "Something else"),
]


@router.get("/reference", response_model=ReferenceOut)
def reference() -> ReferenceOut:
    """Public, static lists used by signup and onboarding forms."""
    return ReferenceOut(
        states=[Option(value=c, label=n) for c, n in sorted(STATES.items(), key=lambda s: s[1])],
        business_types=[Option(value=v, label=lbl) for v, lbl in BUSINESS_TYPES],
    )

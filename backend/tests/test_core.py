from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.main import app
from app.permissions import PERMISSIONS, allowed
from app.schemas.money import Money, Qty


def test_health() -> None:
    r = TestClient(app).get("/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert r.headers["X-Request-Id"]


class _M(BaseModel):
    amount: Money
    qty: Qty


def test_money_round_trip() -> None:
    m = _M(amount="1250.5", qty="1.250")
    assert m.amount == Decimal("1250.5")
    assert m.model_dump(mode="json") == {"amount": "1250.50", "qty": "1.25"}


@pytest.mark.parametrize(
    "bad",
    [
        {"amount": 1.1, "qty": "1"},
        {"amount": "1.001", "qty": "1"},
        {"amount": "1", "qty": "0.0001"},
        {"amount": "NaN", "qty": "1"},
    ],
)
def test_money_rejects(bad: dict) -> None:
    with pytest.raises(ValidationError):
        _M(**bad)


def test_ai_is_owner_exclusive() -> None:
    assert allowed("ai.use", "owner")
    assert not any(allowed("ai.use", r) for r in ("manager", "salesperson", "admin", "support"))


def test_upi_and_gstin_owner_only() -> None:
    assert PERMISSIONS["shop.payment_details"] == {"owner"}
    assert PERMISSIONS["shop.tax_profile"] == {"owner"}

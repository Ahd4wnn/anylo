# ruff: noqa: F811  (pytest fixtures `c` and `clean` are imported from test_sales and injected by name)
"""Vegetable and fruit sellers: starter list sold by weight, GST-exempt, no stock tracking, decimal quantities."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.test_sales import c, clean, gstin  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").endswith("_test"), reason="needs anylo_test database"
)


def test_produce_shop_starter_and_weighed_bill(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/signup",
        json={
            "shop_name": "Fresh Mart",
            "owner_name": "Owner Name",
            "phone": "9876543299",
            "email": "veg@shop.in",
            "password": "s3cret-pass",
            "state_code": "32",
            "business_type": "produce",
            "platform": "android",
        },
    )
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    c.put("/v1/shop/tax-profile", headers=h, json={"gst_scheme": "regular", "gstin": gstin()})
    assert c.post("/v1/shop/starter-products", headers=h).json()["added"] == 12
    tomato = next(
        p for p in c.get("/v1/products", headers=h).json()["items"] if p["name"] == "Tomato"
    )
    assert (
        tomato["unit_code"] == "KGS"
        and tomato["track_stock"] is False
        and tomato["tax_rate"] == "0.00"
    )
    v = tomato["variants"][0]["id"]
    bill = c.post(
        "/v1/invoices",
        headers=h,
        json={
            "lines": [{"variant_id": v, "qty": "1.250", "unit_price": "40.00"}],
            "payments": [{"method": "cash", "amount": "50.00"}],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert bill.status_code == 201, bill.text
    assert bill.json()["totals"]["grand_total"] == "50.00"  # 1.25 kg x 40, no tax on fresh produce

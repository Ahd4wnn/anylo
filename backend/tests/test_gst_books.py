# ruff: noqa: F811  (pytest fixtures `c` and `clean` are imported from test_sales and injected by name)
"""M7: CMP-08 on taxable turnover, expense ITC / reverse charge in 3B, and the read-only accountant role."""

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.test_sales import bill, c, clean, gstin, item, regular, signup, staff  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").endswith("_test"), reason="needs anylo_test database"
)
TODAY = date.today()
PERIOD = f"{TODAY:%Y-%m}"


def test_cmp08_counts_taxable_turnover_only(c: TestClient) -> None:
    h = signup(c)
    c.put("/v1/shop/tax-profile", headers=h, json={"gst_scheme": "composition", "gstin": gstin()})
    v = item(c, h, "Soap", "100.00", "18.00")
    exempt = next(
        r["id"] for r in c.get("/v1/gst-rates", headers=h).json() if r["kind"] == "exempt"
    )
    bill(
        c,
        h,
        [
            {"variant_id": v, "qty": "1"},
            {"custom": {"name": "Spinach", "tax_rate_id": exempt}, "qty": "1", "unit_price": "50"},
        ],
        payments=[{"method": "cash", "amount": "150.00"}],
    )
    r = c.get("/v1/reports/gst/cmp08", headers=h, params={"from": str(TODAY), "to": str(TODAY)})
    assert r.json()["turnover"] == "100.00", r.text


def test_expense_itc_and_reverse_charge_in_3b(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    c.post(
        "/v1/expenses",
        headers=h,
        json={"category_name": "Repairs", "amount": "118.00", "gst_amount": "18.00"},
    )
    c.post(
        "/v1/expenses",
        headers=h,
        json={
            "category_name": "Rent",
            "amount": "1000.00",
            "reverse_charge": True,
            "rcm_rate": "18",
            "supplier_name": "Landlord",
        },
    )
    g = c.get("/v1/reports/gst/gstr3b", headers=h, params={"period": PERIOD}).json()
    assert g["inward_rcm"]["cgst"] == "90.00" and g["inward_rcm"]["sgst"] == "90.00"
    # ITC = 9 + 9 from repairs, plus the RCM paid (90 + 90)
    assert (g["itc"]["cgst"], g["itc"]["sgst"]) == ("99.00", "99.00")
    pl = c.get("/v1/reports/pnl", headers=h).json()
    assert pl["total"]["expenses"] == "1100.00"  # ₹18 GST claimed back isn't a cost


def test_accountant_reads_but_cannot_write(c: TestClient) -> None:
    h = signup(c)
    ca = staff(c, h, "accountant")
    assert c.get("/v1/reports/pnl", headers=ca).status_code == 200
    assert c.get("/v1/expenses", headers=ca).status_code == 200
    assert (
        c.post(
            "/v1/expenses", headers=ca, json={"category_name": "Rent", "amount": "1"}
        ).status_code
        == 403
    )
    assert c.post("/v1/invoices", headers=ca, json={}).status_code in (403, 422)
    manager = staff(c, h, "manager")
    r = c.post(
        "/v1/shop/staff",
        headers=manager,
        json={"full_name": "CA Two", "email": "ca2@shop.in", "role": "accountant"},
    )
    assert r.status_code == 403  # only the owner invites the accountant

# ruff: noqa: F811  (pytest fixtures `c` and `clean` are imported from test_sales and injected by name)
"""M5: suppliers, purchases with weighted-average cost, supplier payments, restock and stock counts."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.test_sales import bill, c, clean, gstin, item, regular, signup, staff  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").endswith("_test"), reason="needs anylo_test database"
)


def key() -> str:
    return str(uuid.uuid4())


def variant(c: TestClient, h: dict, vid: str) -> dict:
    for p in c.get("/v1/products", headers=h).json()["items"]:
        for v in p["variants"]:
            if v["id"] == vid:
                return v
    raise AssertionError(vid)


def supplier(c: TestClient, h: dict, name: str = "Agro Traders", state: str = "32") -> str:
    r = c.post("/v1/suppliers", headers=h, json={"name": name, "gstin": gstin(state, "AAAPA1234A")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_purchase_posts_stock_average_cost_and_payable(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Rice", "100.00", "5.00", stock="10")  # opening 10 @ cost 50
    sup = supplier(c, h)
    body = {
        "supplier_id": sup,
        "supplier_invoice_no": "AT-101",
        "lines": [{"variant_id": v, "qty": "10", "unit_cost": "70.00"}],
        "post": True,
        "paid": [{"method": "cash", "amount": "300.00"}],
        "idempotency_key": key(),
    }
    r = c.post("/v1/purchases", headers=h, json=body)
    assert r.status_code == 201, r.text
    p = r.json()
    assert (
        p["status"],
        p["taxable_total"],
        p["cgst_total"],
        p["sgst_total"],
        p["grand_total"],
        p["paid"],
    ) == (
        "posted",
        "700.00",
        "17.50",
        "17.50",
        "735.00",
        "300.00",
    )
    assert c.post("/v1/purchases", headers=h, json=body).headers["Idempotent-Replay"] == "true"
    dup = c.post("/v1/purchases", headers=h, json=body | {"idempotency_key": key()})
    assert dup.json()["code"] == "purchase.duplicate_bill"
    vv = variant(c, h, v)
    assert (
        vv["stock_qty"] == "20" and vv["cost_price"] == "60.00"
    )  # (10x50 + 10x70) / 20, GST claimable so not a cost
    s = c.get("/v1/suppliers", headers=h).json()
    assert s["payable"] == "435.00"
    assert c.get("/v1/cash/today", headers=h).json()["cash_out"] == "300.00"
    over = c.post(f"/v1/suppliers/{sup}/payments", headers=h, json={"amount": "500.00"})
    assert over.json()["code"] == "supplier.overpay"
    c.post(f"/v1/suppliers/{sup}/payments", headers=h, json={"amount": "435.00", "method": "upi"})
    led = c.get(f"/v1/suppliers/{sup}/ledger", headers=h).json()
    assert [e["kind"] for e in led["entries"]] == ["purchase", "payment", "payment"] and led[
        "balance"
    ] == "0.00"


def test_no_itc_puts_gst_in_cost_and_interstate_is_igst(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Oil", "200.00", "18.00", stock="0")
    sup = supplier(c, h, "Delhi Oils", "07")
    p = c.post(
        "/v1/purchases",
        headers=h,
        json={
            "supplier_id": sup,
            "lines": [{"variant_id": v, "qty": "2", "unit_cost": "100.00"}],
            "itc_eligible": False,
            "post": True,
            "idempotency_key": key(),
        },
    ).json()
    assert (p["supply_type"], p["igst_total"], p["cgst_total"], p["grand_total"]) == (
        "inter",
        "36.00",
        "0.00",
        "236.00",
    )
    assert (
        variant(c, h, v)["cost_price"] == "118.00"
    )  # no ITC: the GST paid is part of what the item cost


def test_draft_edit_cancel_reverses_stock_and_payments(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Rice", "100.00", "0.00", stock="5")
    sup = supplier(c, h)
    d = c.post(
        "/v1/purchases",
        headers=h,
        json={
            "supplier_id": sup,
            "lines": [{"variant_id": v, "qty": "1", "unit_cost": "40"}],
            "idempotency_key": key(),
        },
    ).json()
    assert d["status"] == "draft" and variant(c, h, v)["stock_qty"] == "5"
    d = c.put(
        f"/v1/purchases/{d['id']}",
        headers=h,
        json={
            "supplier_id": sup,
            "lines": [{"variant_id": v, "qty": "4", "unit_cost": "40"}],
            "idempotency_key": key(),
        },
    ).json()
    posted = c.post(
        f"/v1/purchases/{d['id']}/post", headers=h, json=[{"method": "cash", "amount": "160.00"}]
    ).json()
    assert posted["status"] == "posted" and variant(c, h, v)["stock_qty"] == "9"
    assert (
        c.put(
            f"/v1/purchases/{d['id']}",
            headers=h,
            json={
                "supplier_id": sup,
                "lines": [{"variant_id": v, "qty": "1", "unit_cost": "1"}],
                "idempotency_key": key(),
            },
        ).json()["code"]
        == "purchase.not_draft"
    )
    assert c.post(f"/v1/purchases/{d['id']}/cancel", headers=h).json()["status"] == "cancelled"
    assert variant(c, h, v)["stock_qty"] == "5"
    assert c.get("/v1/cash/today", headers=h).json()["cash_out"] == "0"
    assert c.get("/v1/suppliers", headers=h).json()["payable"] == "0"


def test_restock_suggestions_and_permissions(c: TestClient) -> None:
    h = signup(c)
    item(c, h, "Soap", "30.00", "0.00", stock="2", reorder_level="5")
    item(c, h, "Salt", "20.00", "0.00", stock="50", reorder_level="5")
    sug = c.get("/v1/purchases/restock", headers=h).json()
    assert [(s["name"], s["suggested_qty"]) for s in sug] == [("Soap", "8.000")]  # 5 x 2 - 2
    s = staff(c, h)
    assert c.get("/v1/purchases", headers=s).status_code == 403
    assert c.post("/v1/stock-counts", headers=s, json={}).status_code == 403


def test_stock_count_scan_post_with_sale_during_count(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Shampoo", "50.00", "0.00", stock="10", barcode="8901234567894")
    other = item(c, h, "Comb", "10.00", "0.00", stock="3")
    cnt = c.post("/v1/stock-counts", headers=h, json={"name": "Shelf A"}).json()
    assert len(cnt["lines"]) == 2
    for _ in range(3):
        assert (
            c.post(
                f"/v1/stock-counts/{cnt['id']}/lines",
                headers=h,
                json={"code": "8901234567894", "add": "1"},
            ).status_code
            == 200
        )
    c.post(
        f"/v1/stock-counts/{cnt['id']}/lines", headers=h, json={"variant_id": v, "counted_qty": "8"}
    )
    unknown = c.post(
        f"/v1/stock-counts/{cnt['id']}/lines", headers=h, json={"code": "nope", "add": "1"}
    )
    assert unknown.json()["code"] == "count.unknown_item"
    bill(
        c, h, [{"variant_id": v, "qty": "1"}], payments=[{"method": "cash", "amount": "50.00"}]
    )  # sold while counting
    got = c.get(f"/v1/stock-counts/{cnt['id']}", headers=h).json()
    assert got["counted"] == 1 and got["variance_value"] == "-100.00"  # 2 short at cost 50
    c.post(f"/v1/stock-counts/{cnt['id']}/post", headers=h)
    assert variant(c, h, v)["stock_qty"] == "7"  # counted 8, then the sale took one more
    assert variant(c, h, other)["stock_qty"] == "3"  # not counted, untouched
    assert (
        c.post(
            f"/v1/stock-counts/{cnt['id']}/lines",
            headers=h,
            json={"variant_id": v, "counted_qty": "1"},
        ).json()["code"]
        == "count.closed"
    )

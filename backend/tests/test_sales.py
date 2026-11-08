"""Checkout, numbering, stock, payments, permissions, cancel/edit, receipts and PDFs (docs/06, docs/07)."""

import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.database import privileged_session
from app.main import app
from app.services.gst.india import gstin_check_char

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").endswith("_test"), reason="needs anylo_test database"
)


def gstin(state: str = "32", pan: str = "ABCDE1234F") -> str:
    body = f"{state}{pan}1Z"
    return body + gstin_check_char(body)


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    eng = create_engine(os.environ["DATABASE_URL_OWNER"])
    with eng.begin() as c:
        c.execute(text("TRUNCATE shops, users, audit_log CASCADE"))
    yield
    eng.dispose()


@pytest.fixture
def c() -> TestClient:
    return TestClient(app)


def signup(c: TestClient, n: int = 1) -> dict[str, str]:
    r = c.post(
        "/v1/auth/signup",
        json={
            "shop_name": f"Shop {n}",
            "owner_name": "Owner Name",
            "phone": f"98765432{n:02d}",
            "email": f"o{n}@shop.in",
            "password": "s3cret-pass",
            "state_code": "32",
            "platform": "android",
        },
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def regular(c: TestClient, h: dict[str, str]) -> None:
    assert (
        c.put(
            "/v1/shop/tax-profile", headers=h, json={"gst_scheme": "regular", "gstin": gstin()}
        ).status_code
        == 200
    )


def rate(c: TestClient, h: dict[str, str], r: str) -> str:
    return next(
        x["id"]
        for x in c.get("/v1/gst-rates", headers=h).json()
        if x["rate"] == r and x["kind"] in ("taxable", "nil")
    )


def item(
    c: TestClient,
    h: dict[str, str],
    name: str,
    price: str,
    r: str = "18.00",
    inclusive: bool = False,
    stock: str = "10",
    **v: str,
) -> str:
    p = c.post(
        "/v1/products",
        headers=h,
        json={
            "name": name,
            "tax_rate_id": rate(c, h, r),
            "hsn_code": "1006",
            "price_includes_tax": inclusive,
            "variants": [{"sale_price": price, "opening_stock": stock, "cost_price": "50", **v}],
        },
    )
    assert p.status_code == 201, p.text
    return p.json()["variants"][0]["id"]


def bill(c: TestClient, h: dict[str, str], lines: list[dict], **kw: object) -> dict:
    body = {"lines": lines, "idempotency_key": str(uuid.uuid4()), **kw}
    r = c.post("/v1/invoices", headers=h, json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()


def staff(c: TestClient, owner: dict[str, str], role: str = "salesperson") -> dict[str, str]:
    s = c.post(
        "/v1/shop/staff",
        headers=owner,
        json={"full_name": "Staff One", "email": f"{role}@shop.in", "role": role},
    ).json()
    t = c.post(
        "/v1/auth/login",
        json={
            "login": f"{role}@shop.in",
            "password": s["temporary_password"],
            "platform": "android",
        },
    ).json()
    return {"Authorization": f"Bearer {t['access_token']}"}


def stock_of(c: TestClient, h: dict[str, str], variant: str) -> str:
    return (
        c.get("/v1/products", headers=h).json()["items"][0]["variants"][0]["stock_qty"]
        if variant
        else ""
    )


def test_e1_exclusive_bill_matches_gst_fixture(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    a = item(c, h, "A", "100.00", "18.00")
    b = item(c, h, "B", "50.50", "5.00")
    r = bill(
        c,
        h,
        [{"variant_id": a, "qty": "2"}, {"variant_id": b, "qty": "1"}],
        payments=[{"method": "cash", "amount": "289.00"}],
    )
    t = r["totals"]
    assert (
        t["taxable_total"],
        t["cgst_total"],
        t["sgst_total"],
        t["round_off"],
        t["grand_total"],
    ) == ("250.50", "19.26", "19.26", "-0.02", "289.00")
    assert r["title"] == "TAX INVOICE" and r["number"].startswith("INV/") and len(r["number"]) <= 16
    assert r["amount_in_words"].startswith("Rupees Two Hundred Eighty-Nine")
    assert [s["rate"] for s in r["tax_summary"]] == ["5.00", "18.00"]


def test_numbering_is_gapless_and_concurrency_safe(c: TestClient) -> None:
    h = signup(c)
    v = item(c, h, "Pen", "10.00", stock="1000")

    def one(_: int) -> str:
        return bill(
            c, h, [{"variant_id": v, "qty": "1"}], payments=[{"method": "cash", "amount": "10.00"}]
        )["number"]

    with ThreadPoolExecutor(8) as pool:
        numbers = list(pool.map(one, range(24)))
    seqs = sorted(int(n.rsplit("/", 1)[1]) for n in numbers)
    assert seqs == list(range(1, 25))


def test_idempotent_retry_returns_same_invoice(c: TestClient) -> None:
    h = signup(c)
    v = item(c, h, "Pen", "10.00")
    body = {
        "lines": [{"variant_id": v, "qty": "1"}],
        "payments": [{"method": "cash", "amount": "10.00"}],
        "idempotency_key": "retry-key-123",
    }
    first = c.post("/v1/invoices", headers=h, json=body)
    again = c.post("/v1/invoices", headers=h, json=body)
    assert (
        first.status_code == 201
        and again.status_code == 200
        and again.headers["Idempotent-Replay"] == "true"
    )
    assert first.json()["id"] == again.json()["id"]
    assert c.get("/v1/invoices", headers=h).json()["total"] == 1
    assert stock_of(c, h, v) == "9"  # stock moved once


def test_counter_vs_dispatch_place_of_supply_and_b2b(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Rice", "1250.00", "18.00", stock="100")
    buyer = {"name": "KA Traders", "phone": "9876500000", "gstin": gstin("29", "AAACR5055K")}
    counter = bill(
        c,
        h,
        [{"variant_id": v, "qty": "1"}],
        customer=buyer,
        payments=[{"method": "upi", "amount": "1475.00"}],
    )
    assert (
        counter["supply_type"] == "intra" and counter["place_of_supply"] == "Kerala (32)"
    )  # CA finding F2
    shipped = bill(
        c,
        h,
        [{"variant_id": v, "qty": "10"}],
        customer=buyer,
        delivery_mode="dispatched",
        payments=[{"method": "card", "amount": "14750.00"}],
    )
    assert (
        shipped["supply_type"] == "inter" and shipped["totals"]["igst_total"] == "2250.00"
    )  # fixture E3
    bad = c.post(
        "/v1/invoices",
        headers=h,
        json={
            "lines": [{"variant_id": v, "qty": "1"}],
            "idempotency_key": "x" * 10,
            "customer": {"gstin": "29ABCDE1234F1Z0"},
        },
    )
    assert bad.status_code == 422


def test_composition_bill_of_supply_and_interstate_block(c: TestClient) -> None:
    h = signup(c)
    c.put("/v1/shop/tax-profile", headers=h, json={"gst_scheme": "composition", "gstin": gstin()})
    v = item(c, h, "Soap", "40.00", "18.00")
    r = bill(
        c, h, [{"variant_id": v, "qty": "1"}], payments=[{"method": "cash", "amount": "40.00"}]
    )
    assert (
        r["title"] == "BILL OF SUPPLY"
        and r["composition_note"]
        and r["totals"]["cgst_total"] == "0.00"
        and not r["tax_summary"]
    )
    out = c.post(
        "/v1/invoices",
        headers=h,
        json={
            "lines": [{"variant_id": v, "qty": "1"}],
            "idempotency_key": "y" * 10,
            "delivery_mode": "dispatched",
            "delivery_state_code": "29",
            "customer": {"phone": "9876500001"},
        },
    )
    assert out.status_code == 422 and out.json()["code"] == "gst.composition_interstate_blocked"


def test_regular_shop_requires_rate_and_einvoice_blocks_b2b(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    p = c.post(
        "/v1/products", headers=h, json={"name": "NoRate", "variants": [{"sale_price": "10"}]}
    ).json()
    r = c.post(
        "/v1/invoices",
        headers=h,
        json={
            "lines": [{"variant_id": p["variants"][0]["id"], "qty": "1"}],
            "idempotency_key": "z" * 10,
        },
    )
    assert r.status_code == 422 and r.json()["code"] == "invoice.missing_rate"
    c.put(
        "/v1/shop/tax-profile",
        headers=h,
        json={"gst_scheme": "regular", "gstin": gstin(), "einvoice_applicable": True},
    )
    v = item(c, h, "Rated", "10.00")
    b2b = c.post(
        "/v1/invoices",
        headers=h,
        json={
            "lines": [{"variant_id": v, "qty": "1"}],
            "idempotency_key": "w" * 10,
            "customer": {"gstin": gstin("29", "AAACR5055K")},
        },
    )
    assert b2b.status_code == 422 and b2b.json()["code"] == "invoice.einvoice_required"


def test_payments_due_and_custom_line(c: TestClient) -> None:
    h = signup(c)
    v = item(c, h, "Atta", "50.00", "5.00", inclusive=True)
    no_phone = c.post(
        "/v1/invoices",
        headers=h,
        json={
            "lines": [{"variant_id": v, "qty": "2"}],
            "idempotency_key": "d" * 10,
            "payments": [{"method": "cash", "amount": "40.00"}],
        },
    )
    assert no_phone.status_code == 422 and no_phone.json()["code"] == "invoice.due_needs_customer"
    over = c.post(
        "/v1/invoices",
        headers=h,
        json={
            "lines": [{"variant_id": v, "qty": "1"}],
            "idempotency_key": "o" * 10,
            "payments": [{"method": "cash", "amount": "60.00"}],
        },
    )
    assert over.status_code == 422
    r = bill(
        c,
        h,
        [
            {"variant_id": v, "qty": "2"},
            {"custom": {"name": "Delivery"}, "qty": "1", "unit_price": "20.00"},
        ],
        customer={"name": "Ravi", "phone": "9876511111"},
        payments=[{"method": "cash", "amount": "50.00"}, {"method": "upi", "amount": "30.00"}],
    )
    assert r["totals"]["grand_total"] == "120.00" and r["totals"]["due_total"] == "40.00"
    assert {p["method"] for p in r["payments"]} == {"cash", "upi"}
    assert c.get("/v1/invoices", headers=h, params={"has_due": True}).json()["total"] == 1
    assert (
        c.get("/v1/products", headers=h).json()["total"] == 1
    )  # custom line didn't create a product


def test_salesperson_rules_price_discount_pin_visibility(c: TestClient) -> None:
    h = signup(c)
    v = item(c, h, "Shirt", "1000.00", "5.00", inclusive=True)
    s = staff(c, h)
    locked = c.post(
        "/v1/invoices",
        headers=s,
        json={
            "lines": [{"variant_id": v, "qty": "1", "unit_price": "900.00"}],
            "idempotency_key": "p" * 10,
        },
    )
    assert locked.status_code == 403 and locked.json()["code"] == "invoice.price_locked"
    big = {
        "lines": [{"variant_id": v, "qty": "1"}],
        "discount_type": "percent",
        "discount_value": "20",
        "payments": [{"method": "cash", "amount": "800.00"}],
    }
    need = c.post("/v1/invoices", headers=s, json={**big, "idempotency_key": "q" * 10})
    assert need.status_code == 403 and need.json()["code"] == "invoice.approval_required"
    c.put("/v1/auth/pin", headers=h, json={"password": "s3cret-pass", "pin": "4821"})
    wrong = c.post(
        "/v1/invoices", headers=s, json={**big, "idempotency_key": "r" * 10, "approval_pin": "1111"}
    )
    assert wrong.status_code == 403
    ok = c.post(
        "/v1/invoices", headers=s, json={**big, "idempotency_key": "t" * 10, "approval_pin": "4821"}
    )
    assert ok.status_code == 201, ok.text
    bill(c, h, [{"variant_id": v, "qty": "1"}], payments=[{"method": "cash", "amount": "1000.00"}])
    assert c.get("/v1/invoices", headers=s).json()["total"] == 1  # salesperson sees only their own
    assert c.get("/v1/invoices", headers=h).json()["total"] == 2
    assert (
        c.post(
            f"/v1/invoices/{ok.json()['id']}/cancel", headers=s, json={"reason": "mistake"}
        ).status_code
        == 403
    )


def test_cancel_reverses_stock_and_keeps_number(c: TestClient) -> None:
    h = signup(c)
    v = item(c, h, "Pen", "10.00", stock="10")
    r = bill(
        c, h, [{"variant_id": v, "qty": "3"}], payments=[{"method": "cash", "amount": "30.00"}]
    )
    assert stock_of(c, h, v) == "7"
    x = c.post(
        f"/v1/invoices/{r['id']}/cancel", headers=h, json={"reason": "Customer changed mind"}
    ).json()
    assert x["status"] == "cancelled" and x["number"] == r["number"] and not x["payments"]
    assert stock_of(c, h, v) == "10"
    assert (
        c.post(f"/v1/invoices/{r['id']}/cancel", headers=h, json={"reason": "again"}).status_code
        == 409
    )
    nxt = bill(
        c, h, [{"variant_id": v, "qty": "1"}], payments=[{"method": "cash", "amount": "10.00"}]
    )
    assert nxt["number"].endswith("00002")  # cancelled number is never reused


def test_edit_only_before_handover(c: TestClient) -> None:
    h = signup(c)
    v = item(c, h, "Pen", "10.00", stock="10")
    r = bill(
        c, h, [{"variant_id": v, "qty": "2"}], payments=[{"method": "cash", "amount": "20.00"}]
    )
    body = {
        "lines": [{"variant_id": v, "qty": "5"}],
        "payments": [{"method": "upi", "amount": "50.00"}],
        "idempotency_key": "e" * 10,
    }
    e = c.put(f"/v1/invoices/{r['id']}", headers=h, json=body).json()
    assert e["is_edited"] and e["totals"]["grand_total"] == "50.00" and e["number"] == r["number"]
    assert stock_of(c, h, v) == "5"
    assert (
        c.get(f"/v1/invoices/{r['id']}/pdf", headers=h).content[:4] == b"%PDF"
    )  # PDF counts as handing over
    late = c.put(f"/v1/invoices/{r['id']}", headers=h, json=body)
    assert late.status_code == 409 and late.json()["code"] == "invoice.handed_over"


def test_stock_guard_preview_and_held_bills(c: TestClient) -> None:
    h = signup(c)
    v = item(c, h, "Rare", "100.00", stock="1")
    c.patch("/v1/shop", headers=h, json={"settings": {"allow_negative_stock": False}})
    r = c.post(
        "/v1/invoices",
        headers=h,
        json={
            "lines": [{"variant_id": v, "qty": "2"}],
            "idempotency_key": "s" * 10,
            "payments": [{"method": "cash", "amount": "236.00"}],
        },
    )
    assert r.status_code == 409 and r.json()["code"] == "invoice.out_of_stock"
    pv = c.post(
        "/v1/invoices/preview", headers=h, json={"lines": [{"variant_id": v, "qty": "1"}]}
    ).json()
    assert (
        pv["grand_total"] == "100.00" and pv["doc_type"] == "cash_memo"
    )  # unregistered shop: no tax
    held = c.post(
        "/v1/held-bills",
        headers=h,
        json={"label": "Table 4", "payload": {"lines": [{"variant_id": v, "qty": "1"}]}},
    ).json()
    assert [x["label"] for x in c.get("/v1/held-bills", headers=h).json()] == ["Table 4"]
    c.delete(f"/v1/held-bills/{held['id']}", headers=h)
    assert c.get("/v1/held-bills", headers=h).json() == []


def test_public_link_masks_phone_and_isolation(c: TestClient) -> None:
    a, b = signup(c, 1), signup(c, 2)
    v = item(c, a, "Pen", "10.00")
    r = bill(
        c,
        a,
        [{"variant_id": v, "qty": "1"}],
        customer={"name": "Ravi", "phone": "9876512345"},
        payments=[{"method": "cash", "amount": "10.00"}],
    )
    token = r["public_url"].rsplit("/", 1)[1]
    pub = c.get(f"/v1/public/invoices/{token}").json()
    assert pub["buyer"]["phone"] == "98xxxxx345" and pub["number"] == r["number"]
    assert c.get(f"/v1/public/invoices/{token}/pdf").content[:4] == b"%PDF"
    assert c.get(f"/v1/invoices/{r['id']}", headers=b).status_code == 404
    assert c.get("/v1/invoices", headers=b).json()["total"] == 0
    with privileged_session() as db:  # FORCE RLS: read ledger as system
        moves = db.execute(
            text("SELECT count(*) FROM stock_movements WHERE ref_type = 'invoice'")
        ).scalar()
    assert moves == 1


def test_snap_reports_not_configured(c: TestClient) -> None:
    h = signup(c)
    r = c.post(
        "/v1/products/snap", headers=h, files={"file": ("x.jpg", b"\xff\xd8\xff", "image/jpeg")}
    )
    assert r.status_code == 503 and r.json()["code"] == "snap.not_configured"

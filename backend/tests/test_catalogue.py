"""Catalogue, stock ledger, import/export, labels and starter products (docs/08-inventory.md)."""

import io
import os
import zipfile
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from PIL import Image
from sqlalchemy import create_engine, text

from app.database import privileged_session
from app.main import app
from app.services.catalogue import is_valid_ean13
from app.services.gst.india import gstin_check_char

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").endswith("_test"), reason="needs anylo_test database"
)


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


def signup(c: TestClient, n: int = 1, business_type: str = "grocery") -> dict[str, str]:
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
            "business_type": business_type,
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def rate_id(c: TestClient, h: dict[str, str], rate: str) -> str:
    return next(
        r["id"]
        for r in c.get("/v1/gst-rates", headers=h).json()
        if r["rate"] == rate and r["kind"] in ("taxable", "nil")
    )


def make(c: TestClient, h: dict[str, str], **kw: object) -> dict:
    body = {
        "name": "Basmati Rice",
        "unit_code": "BAG",
        "variants": [
            {
                "sale_price": "650",
                "mrp": "699",
                "cost_price": "560",
                "opening_stock": "20",
                "reorder_level": "5",
            }
        ],
    }
    body.update(kw)
    r = c.post("/v1/products", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_with_auto_sku_and_opening_stock(c: TestClient) -> None:
    h = signup(c)
    p = make(c, h)
    v = p["variants"][0]
    assert v["sku"] == "AN-000001" and v["stock_qty"] == "20" and v["sale_price"] == "650.00"
    assert make(c, h, name="Sugar")["variants"][0]["sku"] == "AN-000002"
    mv = c.get("/v1/stock/movements", headers=h, params={"variant_id": v["id"]}).json()
    assert [(m["kind"], m["qty"]) for m in mv] == [("opening", "20")]


def test_validation_rules(c: TestClient) -> None:
    h = signup(c)
    bad_mrp = c.post(
        "/v1/products",
        headers=h,
        json={"name": "X", "variants": [{"sale_price": "100", "mrp": "90"}]},
    )
    assert bad_mrp.status_code == 422
    dup_variant = c.post(
        "/v1/products",
        headers=h,
        json={
            "name": "X",
            "variants": [{"name": "1 kg", "sale_price": "1"}, {"name": "1 KG", "sale_price": "2"}],
        },
    )
    assert dup_variant.status_code == 422
    make(c, h, variants=[{"sale_price": "10", "barcode": "8901234567890"}])
    taken = c.post(
        "/v1/products",
        headers=h,
        json={"name": "Y", "variants": [{"sale_price": "5", "barcode": "8901234567890"}]},
    )
    assert taken.status_code == 409 and taken.json()["code"] == "product.barcode_taken"
    assert (
        c.post(
            "/v1/products",
            headers=h,
            json={"name": "Z", "unit_code": "XYZ", "variants": [{"sale_price": "1"}]},
        ).status_code
        == 422
    )


def test_variants_update_and_deactivate(c: TestClient) -> None:
    h = signup(c)
    p = make(
        c,
        h,
        variants=[{"name": "1 kg", "sale_price": "140"}, {"name": "5 kg", "sale_price": "650"}],
    )
    one, five = p["variants"]
    body = {
        "name": "Basmati Rice",
        "variants": [
            {"id": one["id"], "name": "1 kg", "sale_price": "145"},
            {"name": "10 kg", "sale_price": "1250"},
        ],
    }
    r = c.put(f"/v1/products/{p['id']}", headers=h, json=body)
    assert r.status_code == 200, r.text
    names = {v["name"]: v for v in r.json()["variants"]}
    assert set(names) == {"1 kg", "10 kg"} and names["1 kg"]["sale_price"] == "145.00"
    assert names["1 kg"]["sku"] == one["sku"]  # SKU kept when not sent
    # The removed 5 kg variant is deactivated (kept for history), not deleted.
    with privileged_session() as db:  # FORCE RLS hides rows from the table owner, so read as system
        assert (
            db.execute(
                text("SELECT is_active FROM product_variants WHERE id = :i"), {"i": five["id"]}
            ).scalar()
            is False
        )


def test_lookup_and_generated_ean(c: TestClient) -> None:
    h = signup(c)
    code = c.post("/v1/barcodes/generate", headers=h).json()["barcode"]
    assert code.startswith("2") and is_valid_ean13(code)
    p = make(c, h, variants=[{"sale_price": "10", "barcode": code, "sku": "RICE-5"}])
    assert (
        c.get("/v1/products/lookup", headers=h, params={"code": code}).json()["product"]["id"]
        == p["id"]
    )
    assert c.get("/v1/products/lookup", headers=h, params={"code": "rice-5"}).status_code == 200
    assert c.get("/v1/products/lookup", headers=h, params={"code": "nope"}).status_code == 404


def test_missing_tax_info_flag(c: TestClient) -> None:
    h = signup(c)
    body = "32ABCDE1234F1Z"
    c.put(
        "/v1/shop/tax-profile",
        headers=h,
        json={"gst_scheme": "regular", "gstin": body + gstin_check_char(body)},
    )
    assert make(c, h)["missing_tax_info"] is True
    ok = make(c, h, name="Rice 2", hsn_code="1006", tax_rate_id=rate_id(c, h, "5.00"))
    assert ok["missing_tax_info"] is False and ok["tax_rate"] == "5.00"


def test_stock_adjustments_keep_ledger_and_cache_equal(c: TestClient) -> None:
    h = signup(c)
    v = make(c, h)["variants"][0]
    adj = lambda **kw: c.post(
        "/v1/stock/adjustments", headers=h, json={"variant_id": v["id"], **kw}
    )
    assert adj(mode="set", qty="17").json()["stock_qty"] == "17"
    assert adj(mode="add", qty="2.5").json()["stock_qty"] == "19.5"
    assert adj(mode="remove", qty="1.5", kind="damage", reason="wet").json()["stock_qty"] == "18"
    assert adj(mode="add", qty="1", kind="damage").status_code == 400
    with privileged_session() as db:
        ledger = db.execute(
            text("SELECT sum(qty) FROM stock_movements WHERE variant_id = :v"), {"v": v["id"]}
        ).scalar()
        cache = db.execute(
            text("SELECT stock_qty FROM product_variants WHERE id = :v"), {"v": v["id"]}
        ).scalar()
    assert ledger == cache == Decimal("18")


def test_low_stock_valuation_and_filters(c: TestClient) -> None:
    h = signup(c)
    low = make(
        c,
        h,
        name="Atta",
        variants=[
            {"sale_price": "50", "cost_price": "40", "opening_stock": "2", "reorder_level": "5"}
        ],
    )
    make(
        c,
        h,
        name="Sugar",
        variants=[
            {"sale_price": "45", "cost_price": "38", "opening_stock": "50", "reorder_level": "5"}
        ],
    )
    assert [p["id"] for p in c.get("/v1/stock/low", headers=h).json()["items"]] == [low["id"]]
    val = c.get("/v1/stock/valuation", headers=h).json()
    assert val["total_value"] == "1980.00"  # 2*40 + 50*38
    assert c.get("/v1/products", headers=h, params={"q": "sug"}).json()["total"] == 1


def test_archive_restore_and_permissions(c: TestClient) -> None:
    h = signup(c)
    p = make(c, h)
    staff = c.post(
        "/v1/shop/staff", headers=h, json={"full_name": "Sal Person", "email": "s@shop.in"}
    ).json()
    sh = c.post(
        "/v1/auth/login",
        json={"login": "s@shop.in", "password": staff["temporary_password"], "platform": "android"},
    ).json()
    s = {"Authorization": f"Bearer {sh['access_token']}"}
    assert c.get("/v1/products", headers=s).json()["total"] == 1
    assert (
        c.post(
            "/v1/products", headers=s, json={"name": "X", "variants": [{"sale_price": "1"}]}
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/v1/stock/adjustments",
            headers=s,
            json={"variant_id": p["variants"][0]["id"], "mode": "add", "qty": "1"},
        ).status_code
        == 403
    )
    assert c.delete(f"/v1/products/{p['id']}", headers=h).status_code == 204
    assert c.get("/v1/products", headers=h).json()["total"] == 0
    assert (
        c.get("/v1/products", headers=h, params={"include_archived": True}).json()["items"][0][
            "archived"
        ]
        is True
    )
    c.post(f"/v1/products/{p['id']}/restore", headers=h)
    assert c.get("/v1/products", headers=h).json()["total"] == 1


def test_shops_cannot_see_each_others_items(c: TestClient) -> None:
    a, b = signup(c, 1), signup(c, 2)
    p = make(c, a)
    assert c.get("/v1/products", headers=b).json()["total"] == 0
    assert c.get(f"/v1/products/{p['id']}", headers=b).status_code == 404
    assert (
        c.post(
            "/v1/stock/adjustments",
            headers=b,
            json={"variant_id": p["variants"][0]["id"], "mode": "add", "qty": "1"},
        ).status_code
        == 404
    )


def _xlsx(rows: list[list[str]]) -> bytes:
    wb = Workbook()
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_dry_run_commit_and_update(c: TestClient) -> None:
    h = signup(c)
    head = [
        "name",
        "variant",
        "category",
        "sku",
        "hsn",
        "gst_rate",
        "unit",
        "mrp",
        "sale_price",
        "opening_stock",
    ]
    good = _xlsx(
        [
            head,
            ["Tea", "250 g", "Beverages", "TEA-250", "0902", "5", "PAC", "150", "140", "10"],
            ["Tea", "1 kg", "Beverages", "TEA-1K", "0902", "5", "PAC", "520", "500", "4"],
        ]
    )
    up = lambda data, dry: c.post(
        "/v1/products/import",
        headers=h,
        params={"dry_run": dry},
        files={"file": ("items.xlsx", data)},
    )
    dry = up(good, True).json()
    assert dry == {**dry, "committed": False, "creates": 2, "errors": 0}
    assert c.get("/v1/products", headers=h).json()["total"] == 0  # dry run saved nothing
    assert up(good, False).json()["committed"] is True
    items = c.get("/v1/products", headers=h).json()["items"]
    assert (
        len(items) == 1
        and len(items[0]["variants"]) == 2
        and items[0]["category_name"] == "Beverages"
    )

    # Re-import by SKU updates the price; a bad row blocks the whole commit.
    mixed = _xlsx(
        [
            head,
            ["Tea", "250 g", "", "TEA-250", "", "", "PAC", "150", "145", ""],
            ["Bad", "", "", "", "", "7", "NOS", "", "x", ""],
        ]
    )
    res = up(mixed, False).json()
    assert res["committed"] is False and res["errors"] == 1 and res["rows"][1]["errors"]
    fixed = _xlsx([head, ["Tea", "250 g", "", "TEA-250", "", "", "PAC", "150", "145", ""]])
    assert up(fixed, False).json() == {**up(fixed, True).json(), "committed": True}
    tea = c.get("/v1/products/lookup", headers=h, params={"code": "TEA-250"}).json()["variant"]
    assert tea["sale_price"] == "145.00" and tea["stock_qty"] == "10"  # stock untouched by updates


def test_export_template_labels(c: TestClient) -> None:
    h = signup(c)
    p = make(c, h, variants=[{"sale_price": "650", "mrp": "699", "barcode": "8901234567890"}])
    tpl = load_workbook(io.BytesIO(c.get("/v1/products/import/template", headers=h).content))
    assert tpl.active["A1"].value == "name" and "Help" in tpl.sheetnames
    exp = load_workbook(io.BytesIO(c.get("/v1/products/export", headers=h).content)).active
    assert [x.value for x in exp[2]][:2] == ["Basmati Rice", None] and exp[2][10].value == "650.00"
    for layout in ("a4_24", "a4_65", "roll_50x25"):
        r = c.post(
            "/v1/products/labels",
            headers=h,
            json={"items": [{"variant_id": p["variants"][0]["id"], "copies": 3}], "layout": layout},
        )
        assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_photo_and_zip(c: TestClient) -> None:
    h = signup(c)
    p = make(c, h, variants=[{"sale_price": "1", "sku": "RICE-5"}])
    img = io.BytesIO()
    Image.new("RGB", (1200, 900), "#5B6CF0").save(img, "JPEG")
    one = c.post(
        f"/v1/products/{p['id']}/photo", headers=h, files={"file": ("x.jpg", img.getvalue())}
    ).json()
    assert one["photo_url"].endswith(".webp") and one["thumb_url"].endswith("_thumb.webp")
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("rice-5.jpg", img.getvalue())
        zf.writestr("unknown.jpg", img.getvalue())
    res = c.post(
        "/v1/products/photos/zip", headers=h, files={"file": ("p.zip", z.getvalue())}
    ).json()
    assert res == {"matched": ["rice-5.jpg"], "unmatched": ["unknown.jpg"]}


def test_starter_products_and_onboarding_flag(c: TestClient) -> None:
    h = signup(c, business_type="nursery")
    assert c.get("/v1/shop/onboarding", headers=h).json()["products"] is False
    first = c.post("/v1/shop/starter-products", headers=h).json()["added"]
    assert (
        first >= 5 and c.post("/v1/shop/starter-products", headers=h).json()["added"] == 0
    )  # idempotent
    assert c.get("/v1/shop/onboarding", headers=h).json()["products"] is True
    names = {
        p["name"] for p in c.get("/v1/products", headers=h, params={"limit": 200}).json()["items"]
    }
    assert "Tulsi Plant" in names

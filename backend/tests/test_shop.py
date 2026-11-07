"""Shop profile, GST profile, staff management, password flows and onboarding."""

import io
import os
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text

from app.main import app
from app.services import email
from app.services.gst.india import gstin_check_char

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").endswith("_test"), reason="needs anylo_test database"
)

OWNER = {
    "shop_name": "Ravi Stores",
    "owner_name": "Ravi Kumar",
    "phone": "9876543210",
    "email": "ravi@shop.in",
    "password": "s3cret-pass",
    "state_code": "32",
    "platform": "android",
}


def gstin(state: str = "32") -> str:
    body = f"{state}ABCDE1234F1Z"
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


def login(c: TestClient, who: str, password: str) -> dict[str, str]:
    r = c.post("/v1/auth/login", json={"login": who, "password": password, "platform": "android"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def owner(c: TestClient) -> dict[str, str]:
    r = c.post("/v1/auth/signup", json=OWNER)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def add_staff(c: TestClient, h: dict[str, str], role: str, email_: str) -> tuple[str, str]:
    r = c.post(
        "/v1/shop/staff",
        headers=h,
        json={"full_name": f"{role} one", "email": email_, "role": role},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"], r.json()["temporary_password"]


def test_shop_profile_and_upi_owner_only(c: TestClient, owner: dict[str, str]) -> None:
    r = c.patch(
        "/v1/shop",
        headers=owner,
        json={
            "address_line1": "MG Road",
            "pincode": "682001",
            "upi_vpa": "ravi@okaxis",
            "settings": {"receipt_width_mm": 58},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["upi_vpa"] == "ravi@okaxis" and body["settings"]["receipt_width_mm"] == 58
    assert body["state_name"] == "Kerala"

    _, pw = add_staff(c, owner, "manager", "m@shop.in")
    mgr = login(c, "m@shop.in", pw)
    assert c.patch("/v1/shop", headers=mgr, json={"city": "Kochi"}).status_code == 200
    r = c.patch("/v1/shop", headers=mgr, json={"upi_vpa": "thief@okaxis"})
    assert r.status_code == 403 and r.json()["code"] == "shop.upi_owner_only"


def test_tax_profile_validation_and_state_sync(c: TestClient, owner: dict[str, str]) -> None:
    bad = c.put(
        "/v1/shop/tax-profile",
        headers=owner,
        json={"gst_scheme": "regular", "gstin": gstin()[:-1] + "0"},
    )
    assert bad.status_code == 422
    missing = c.put("/v1/shop/tax-profile", headers=owner, json={"gst_scheme": "regular"})
    assert missing.status_code == 422
    r = c.put(
        "/v1/shop/tax-profile",
        headers=owner,
        json={"gst_scheme": "regular", "gstin": gstin("29").lower(), "legal_name": "Ravi Traders"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["tax"]["gstin"] == gstin("29") and r.json()["state_code"] == "29"
    comp = c.put(
        "/v1/shop/tax-profile",
        headers=owner,
        json={"gst_scheme": "composition", "gstin": gstin("29")},
    )
    assert comp.json()["tax"]["composition_rate"] == "1.00"


def test_tax_profile_is_owner_only(c: TestClient, owner: dict[str, str]) -> None:
    _, pw = add_staff(c, owner, "manager", "m@shop.in")
    mgr = login(c, "m@shop.in", pw)
    assert (
        c.put("/v1/shop/tax-profile", headers=mgr, json={"gst_scheme": "unregistered"}).status_code
        == 403
    )


def test_staff_lifecycle_and_role_rules(c: TestClient, owner: dict[str, str]) -> None:
    mid, mpw = add_staff(c, owner, "manager", "m@shop.in")
    assert re.fullmatch(r"[a-z2-9]{10}", mpw)
    mgr = login(c, "m@shop.in", mpw)
    me = c.get("/v1/auth/me", headers=mgr).json()
    assert me["user"]["must_change_password"] is True and "ai.use" not in me["permissions"]

    # Managers create salespeople but not managers, and cannot touch other managers.
    sid, spw = add_staff(c, mgr, "salesperson", "s@shop.in")
    r = c.post(
        "/v1/shop/staff",
        headers=mgr,
        json={"full_name": "x y", "email": "m2@shop.in", "role": "manager"},
    )
    assert r.status_code == 403
    assert c.patch(f"/v1/shop/staff/{mid}", headers=mgr, json={"is_active": False}).status_code in (
        400,
        403,
    )

    # Salesperson cannot manage staff at all.
    sales = login(c, "s@shop.in", spw)
    assert c.get("/v1/shop/staff", headers=sales).status_code == 403

    # Deactivation kills the salesperson's live access token.
    assert (
        c.patch(f"/v1/shop/staff/{sid}", headers=mgr, json={"is_active": False}).status_code == 200
    )
    assert c.get("/v1/auth/me", headers=sales).status_code == 401

    # Duplicate email across the platform is a clean 409.
    r = c.post(
        "/v1/shop/staff", headers=owner, json={"full_name": "dup e", "email": "ravi@shop.in"}
    )
    assert r.status_code == 409
    roles = sorted(s["role"] for s in c.get("/v1/shop/staff", headers=owner).json())
    assert roles == ["manager", "salesperson"]


def test_staff_reset_and_forced_change(c: TestClient, owner: dict[str, str]) -> None:
    sid, _ = add_staff(c, owner, "salesperson", "s@shop.in")
    new_pw = c.post(f"/v1/shop/staff/{sid}/reset-password", headers=owner).json()[
        "temporary_password"
    ]
    h = login(c, "s@shop.in", new_pw)
    r = c.post(
        "/v1/auth/password/change",
        headers=h,
        json={"current_password": new_pw, "new_password": "my-own-pass", "platform": "android"},
    )
    assert r.status_code == 200 and r.json()["refresh_token"]
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert c.get("/v1/auth/me", headers=h2).json()["user"]["must_change_password"] is False
    assert c.get("/v1/auth/me", headers=h).status_code == 401  # old token revoked


def test_forgot_and_reset_password(c: TestClient, owner: dict[str, str]) -> None:
    email.outbox.clear()
    assert c.post("/v1/auth/password/forgot", json={"email": "nobody@shop.in"}).status_code == 202
    assert not email.outbox
    assert c.post("/v1/auth/password/forgot", json={"email": "RAVI@shop.in"}).status_code == 202
    token = re.search(r"/reset/(\S+)", email.outbox[-1].get_content()).group(1)  # type: ignore[union-attr]
    assert (
        c.post(
            "/v1/auth/password/reset", json={"token": token, "password": "brand-new-1"}
        ).status_code
        == 204
    )
    assert (
        c.post(
            "/v1/auth/password/reset", json={"token": token, "password": "again-again"}
        ).status_code
        == 400
    )
    assert c.get("/v1/auth/me", headers=owner).status_code == 401  # all sessions revoked
    login(c, "ravi@shop.in", "brand-new-1")


def test_logo_upload_rejects_non_images(c: TestClient, owner: dict[str, str]) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (900, 300), "#4F6BFF").save(buf, "PNG")
    r = c.post(
        "/v1/shop/logo", headers=owner, files={"file": ("logo.png", buf.getvalue(), "image/png")}
    )
    assert r.status_code == 200 and r.json()["logo_url"].endswith(".webp")
    fake = c.post(
        "/v1/shop/logo", headers=owner, files={"file": ("x.png", b"<script>", "image/png")}
    )
    assert fake.status_code == 415


def test_onboarding_and_second_shop(c: TestClient, owner: dict[str, str]) -> None:
    ob = c.get("/v1/shop/onboarding", headers=owner).json()
    assert not ob["details"] and not ob["completed"]
    assert c.get("/v1/auth/me", headers=owner).json()["onboarding_completed"] is False
    c.patch("/v1/shop", headers=owner, json={"address_line1": "MG Road", "pincode": "682001"})
    c.put("/v1/shop/tax-profile", headers=owner, json={"gst_scheme": "unregistered"})
    assert c.post("/v1/shop/onboarding/complete", headers=owner).status_code == 204
    ob = c.get("/v1/shop/onboarding", headers=owner).json()
    assert ob["details"] and ob["tax"] and ob["completed"]

    r = c.post("/v1/shops", headers=owner, json={"name": "Ravi Stores 2", "state_code": "32"})
    assert r.status_code == 201
    me = c.get("/v1/auth/me", headers=owner).json()
    assert len(me["shops"]) == 2 and me["active_shop_id"] is None  # must pick a shop now
    assert c.get("/v1/shop", headers=owner).status_code == 400
    picked = c.get("/v1/shop", headers={**owner, "X-Shop-Id": r.json()["id"]})
    assert picked.json()["name"] == "Ravi Stores 2"


def test_sessions_and_pin(c: TestClient, owner: dict[str, str]) -> None:
    sessions = c.get("/v1/auth/sessions", headers=owner).json()
    assert len(sessions) == 1
    assert (
        c.put(
            "/v1/auth/pin", headers=owner, json={"password": "s3cret-pass", "pin": "4821"}
        ).status_code
        == 204
    )
    assert (
        c.put("/v1/auth/pin", headers=owner, json={"password": "wrong", "pin": "4821"}).status_code
        == 400
    )
    assert c.delete(f"/v1/auth/sessions/{sessions[0]['id']}", headers=owner).status_code == 204
    assert c.get("/v1/auth/sessions", headers=owner).json() == []

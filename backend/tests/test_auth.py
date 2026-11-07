"""Auth flows end to end through FastAPI against the anylo_test database."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").endswith("_test"), reason="needs anylo_test database"
)

SIGNUP = {
    "shop_name": "Ravi Stores",
    "owner_name": "Ravi Kumar",
    "phone": "9876543210",
    "email": "ravi@shop.in",
    "password": "s3cret-pass",
    "business_type": "grocery",
    "state_code": "32",
}


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    eng = create_engine(os.environ["DATABASE_URL_OWNER"])
    with eng.begin() as c:
        c.execute(text("TRUNCATE shops, users CASCADE"))
    yield
    eng.dispose()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_signup_creates_owner_shop_and_trial(client: TestClient) -> None:
    r = client.post("/v1/auth/signup", json=SIGNUP)
    assert r.status_code == 201, r.text
    assert "anylo_rt" in r.cookies and r.json()["refresh_token"] is None  # web: cookie only
    me = client.get("/v1/auth/me", headers=_auth(r.json()["access_token"])).json()
    assert me["user"]["role"] == "owner"
    assert [s["name"] for s in me["shops"]] == ["Ravi Stores"]
    assert me["active_shop_id"] == me["shops"][0]["id"]
    assert me["subscription"]["status"] == "trialing"
    assert me["subscription"]["days_left"] in (29, 30)
    assert "ai.use" in me["permissions"]


def test_signup_duplicate_rejected(client: TestClient) -> None:
    client.post("/v1/auth/signup", json=SIGNUP)
    r = client.post("/v1/auth/signup", json={**SIGNUP, "email": "other@shop.in"})
    assert r.status_code == 409 and r.json()["code"] == "auth.account_exists"


@pytest.mark.parametrize("bad", [{"phone": "12345"}, {"password": "short"}, {"state_code": "99"}])
def test_signup_validation(client: TestClient, bad: dict) -> None:
    assert client.post("/v1/auth/signup", json={**SIGNUP, **bad}).status_code == 422


def test_login_by_email_or_phone(client: TestClient) -> None:
    client.post("/v1/auth/signup", json=SIGNUP)
    for login in ("ravi@shop.in", "RAVI@shop.in", "9876543210"):
        r = client.post("/v1/auth/login", json={"login": login, "password": "s3cret-pass"})
        assert r.status_code == 200, (login, r.text)


def test_wrong_password_locks_after_five(client: TestClient) -> None:
    client.post("/v1/auth/signup", json=SIGNUP)
    for _ in range(5):
        r = client.post("/v1/auth/login", json={"login": "ravi@shop.in", "password": "nope-nope"})
        assert r.status_code == 401 and r.json()["code"] == "auth.invalid_credentials"
    r = client.post("/v1/auth/login", json={"login": "ravi@shop.in", "password": "s3cret-pass"})
    assert r.status_code == 429


def test_unknown_user_same_error(client: TestClient) -> None:
    r = client.post("/v1/auth/login", json={"login": "ghost@shop.in", "password": "whatever1"})
    assert r.status_code == 401 and r.json()["code"] == "auth.invalid_credentials"


def test_mobile_refresh_rotation_and_reuse_detection(client: TestClient) -> None:
    r = client.post("/v1/auth/signup", json={**SIGNUP, "platform": "android"})
    rt1 = r.json()["refresh_token"]
    assert rt1
    r2 = client.post("/v1/auth/refresh", json={"refresh_token": rt1})
    assert r2.status_code == 200
    rt2 = r2.json()["refresh_token"]
    assert rt2 and rt2 != rt1
    # Re-using the rotated token is treated as theft: the whole family dies.
    assert client.post("/v1/auth/refresh", json={"refresh_token": rt1}).status_code == 401
    assert client.post("/v1/auth/refresh", json={"refresh_token": rt2}).status_code == 401


def test_web_refresh_uses_cookie(client: TestClient) -> None:
    client.post("/v1/auth/signup", json=SIGNUP)  # TestClient keeps the cookie
    r = client.post("/v1/auth/refresh")
    assert r.status_code == 200 and r.json()["refresh_token"] is None


def test_logout_all_kills_access_tokens(client: TestClient) -> None:
    tok = client.post("/v1/auth/signup", json=SIGNUP).json()["access_token"]
    assert client.post("/v1/auth/logout-all", headers=_auth(tok)).status_code == 204
    assert client.get("/v1/auth/me", headers=_auth(tok)).status_code == 401


def test_me_requires_valid_token(client: TestClient) -> None:
    assert client.get("/v1/auth/me").status_code == 401
    assert client.get("/v1/auth/me", headers=_auth("garbage")).status_code == 401

"""Tenant isolation against a real Postgres (anylo_test), connected as the NOBYPASSRLS app role."""

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.database import Actor, privileged_session, rls_session

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").endswith("_test"), reason="needs anylo_test database"
)


def _q(db, sql: str, **p):  # type: ignore[no-untyped-def]
    return db.execute(text(sql), p)


@pytest.fixture
def world() -> Iterator[dict[str, uuid.UUID]]:
    owner_engine = create_engine(os.environ["DATABASE_URL_OWNER"])
    with owner_engine.begin() as c:
        c.execute(text("TRUNCATE shops, users CASCADE"))
    ids = {
        k: uuid.uuid4() for k in ("shop_a", "shop_b", "mgr_a", "mgr_b", "owner", "admin", "support")
    }
    with privileged_session() as db:
        for shop in ("shop_a", "shop_b"):
            _q(
                db,
                "INSERT INTO shops (id, name, state_code) VALUES (:i, :n, '32')",
                i=ids[shop],
                n=shop,
            )
        users = [
            ("mgr_a", "manager", ids["shop_a"]),
            ("mgr_b", "manager", ids["shop_b"]),
            ("owner", "owner", None),
            ("admin", "admin", None),
            ("support", "support", None),
        ]
        for key, role, shop_id in users:
            _q(
                db,
                "INSERT INTO users (id, email, full_name, password_hash, role, shop_id)"
                " VALUES (:i, :e, :n, 'x', :r, :s)",
                i=ids[key],
                e=f"{key}@t.in",
                n=key,
                r=role,
                s=shop_id,
            )
        _q(db, "INSERT INTO shop_owners VALUES (:s, :o)", s=ids["shop_a"], o=ids["owner"])
    yield ids
    with owner_engine.begin() as c:
        c.execute(text("TRUNCATE shops, users CASCADE"))
    owner_engine.dispose()


def _shops(actor: Actor) -> set[str]:
    with rls_session(actor) as db:
        return {r[0] for r in _q(db, "SELECT name FROM shops")}


def test_manager_sees_only_own_shop(world: dict[str, uuid.UUID]) -> None:
    a = Actor(world["mgr_a"], "manager", world["shop_a"])
    assert _shops(a) == {"shop_a"}
    with rls_session(a) as db:
        emails = {r[0] for r in _q(db, "SELECT email FROM users")}
    assert emails == {"mgr_a@t.in"}


def test_manager_cannot_write_other_shop(world: dict[str, uuid.UUID]) -> None:
    a = Actor(world["mgr_a"], "manager", world["shop_a"])
    with pytest.raises(DBAPIError), rls_session(a) as db:
        _q(
            db,
            "INSERT INTO users (email, full_name, password_hash, role, shop_id)"
            " VALUES ('x@t.in', 'x', 'x', 'salesperson', :s)",
            s=world["shop_b"],
        )
    with rls_session(a) as db:
        updated = _q(
            db, "UPDATE shops SET name = 'hacked' WHERE id = :s", s=world["shop_b"]
        ).rowcount
    assert updated == 0


def test_owner_sees_linked_shops_only(world: dict[str, uuid.UUID]) -> None:
    o = Actor(world["owner"], "owner", None)
    assert _shops(o) == {"shop_a"}
    with rls_session(o) as db:
        emails = {r[0] for r in _q(db, "SELECT email FROM users")}
    assert emails == {"owner@t.in", "mgr_a@t.in"}


def test_platform_roles(world: dict[str, uuid.UUID]) -> None:
    assert _shops(Actor(world["admin"], "admin", None)) == {"shop_a", "shop_b"}
    assert _shops(Actor(world["support"], "support", None)) == {"shop_a", "shop_b"}
    with rls_session(Actor(world["support"], "support", None)) as db:
        roles = {r[0] for r in _q(db, "SELECT role FROM users")}
    assert "admin" not in roles


def test_no_context_sees_nothing(world: dict[str, uuid.UUID]) -> None:
    assert _shops(Actor(None, "salesperson", None)) == set()


def test_app_role_cannot_bypass_rls() -> None:
    with privileged_session() as db:
        user, bypass = _q(
            db, "SELECT current_user, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).one()
    assert user == "anylo_app" and bypass is False

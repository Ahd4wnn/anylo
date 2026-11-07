from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine = create_engine(
    get_settings().database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={
        "options": "-c statement_timeout=15000 -c idle_in_transaction_session_timeout=30000"
    },
)
SessionLocal = sessionmaker(_engine, expire_on_commit=False)

RLS_ROLES = {"admin", "support", "owner", "manager", "salesperson", "system"}


@dataclass(frozen=True)
class Actor:
    user_id: UUID | None
    role: str
    shop_id: UUID | None


def _set_guc(db: Session, actor: Actor) -> None:
    # Transaction-local (is_local=true) so pooled connections never leak another tenant's context.
    db.execute(
        text(
            "SELECT set_config('app.role', :r, true), set_config('app.user_id', :u, true),"
            " set_config('app.shop_id', :s, true)"
        ),
        {"r": actor.role, "u": str(actor.user_id or ""), "s": str(actor.shop_id or "")},
    )


@contextmanager
def rls_session(actor: Actor) -> Iterator[Session]:
    """One RLS-scoped transaction per request: commit on success, roll back on error."""
    if actor.role not in RLS_ROLES:
        raise ValueError(f"unknown role {actor.role!r}")
    with SessionLocal() as db, db.begin():
        _set_guc(db, actor)
        yield db


@contextmanager
def privileged_session() -> Iterator[Session]:
    """Cross-tenant access. Only for login, signup, public pages, webhooks and the worker."""
    with rls_session(Actor(user_id=None, role="system", shop_id=None)) as db:
        yield db

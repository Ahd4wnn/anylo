"""Request dependencies: who is calling, which shop, and an RLS-scoped DB session."""

from collections.abc import Callable, Iterator
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import Actor, privileged_session, rls_session
from app.errors import AppError
from app.permissions import allowed
from app.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)
_UNAUTH = AppError("auth.required", "Please log in again.", 401)


def get_actor(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    x_shop_id: Annotated[UUID | None, Header()] = None,
) -> Actor:
    if creds is None:
        raise _UNAUTH
    try:
        claims = decode_access_token(creds.credentials)
        user_id = UUID(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _UNAUTH from None
    # Re-read the user every request: role, shop, active flag and token version are live.
    with privileged_session() as db:  # privileged: actor not established yet
        u = db.execute(
            text("SELECT role, shop_id, is_active, token_version FROM users WHERE id = :i"),
            {"i": user_id},
        ).first()
        if not u or not u.is_active or u.token_version != claims.get("ver"):
            raise _UNAUTH
        shop_id = u.shop_id
        if u.role == "owner" and x_shop_id:
            linked = db.execute(
                text("SELECT 1 FROM shop_owners WHERE owner_id = :o AND shop_id = :s"),
                {"o": user_id, "s": x_shop_id},
            ).first()
            if not linked:
                raise AppError("shop.not_yours", "You don't have access to this shop.", 403)
            shop_id = x_shop_id
        elif u.role == "owner":
            # Default an owner with exactly one shop to that shop.
            owned = db.execute(
                text("SELECT shop_id FROM shop_owners WHERE owner_id = :o LIMIT 2"), {"o": user_id}
            ).all()
            shop_id = owned[0].shop_id if len(owned) == 1 else None
    return Actor(user_id=user_id, role=u.role, shop_id=shop_id)


CurrentActor = Annotated[Actor, Depends(get_actor)]


def get_db(actor: CurrentActor) -> Iterator[Session]:
    with rls_session(actor) as db:
        yield db


DB = Annotated[Session, Depends(get_db)]


def require(permission: str) -> Callable[[Actor], Actor]:
    def check(actor: CurrentActor) -> Actor:
        if not allowed(permission, actor.role):
            raise AppError("auth.forbidden", "You don't have permission to do this.", 403)
        return actor

    return check

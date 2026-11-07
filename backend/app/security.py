"""Password hashing and token primitives (docs/17-security.md §2)."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import get_settings

_ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)
# Used to keep login timing equal when the account does not exist.
_DUMMY_HASH = _ph.hash("anylo-timing-equaliser")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return _ph.verify(hashed or _DUMMY_HASH, password) and hashed is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def new_refresh_token() -> tuple[str, str]:
    """Returns (token for the client, sha256 hash for the database)."""
    token = secrets.token_urlsafe(32)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(
    *, user_id: UUID, session_id: UUID, role: str, shop_id: UUID | None, version: int
) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "role": role,
        "shop": str(shop_id) if shop_id else None,
        "ver": version,
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_minutes),
    }
    return jwt.encode(claims, s.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError on any invalid, expired or tampered token."""
    return jwt.decode(
        token, get_settings().jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]}
    )

"""Signup, login, refresh rotation and logout (docs/17-security.md §2)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.schemas.auth import LoginIn, SignupIn
from app.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int


def _q(db: Session, sql: str, **p: Any) -> Any:
    return db.execute(text(sql), p)


def _issue(
    db: Session, user: Any, *, platform: str, device: str | None, family: uuid.UUID | None = None
) -> IssuedTokens:
    s = get_settings()
    refresh, refresh_hash = new_refresh_token()
    session_id = _q(
        db,
        "INSERT INTO auth_sessions (user_id, family_id, refresh_hash, device_label, platform, expires_at)"
        " VALUES (:u, :f, :h, :d, :p, now() + make_interval(days => :days)) RETURNING id",
        u=user.id,
        f=family or uuid.uuid4(),
        h=refresh_hash,
        d=device,
        p=platform,
        days=s.refresh_token_days,
    ).scalar_one()
    access = create_access_token(
        user_id=user.id,
        session_id=session_id,
        role=user.role,
        shop_id=user.shop_id,
        version=user.token_version,
    )
    return IssuedTokens(access, refresh, s.access_token_minutes * 60)


def signup(db: Session, data: SignupIn) -> IssuedTokens:
    """Creates shop + tax profile + owner + trial subscription in one transaction. db is privileged."""
    taken = _q(
        db, "SELECT 1 FROM users WHERE email = :e OR phone = :p", e=data.email, p=data.phone
    ).first()
    if taken:
        raise AppError(
            "auth.account_exists", "An account with this email or mobile already exists.", 409
        )

    shop_id = _q(
        db,
        "INSERT INTO shops (name, business_type, phone, email, state_code) VALUES (:n, :b, :p, :e, :s)"
        " RETURNING id",
        n=data.shop_name,
        b=data.business_type,
        p=data.phone,
        e=data.email,
        s=data.state_code,
    ).scalar_one()
    _q(db, "INSERT INTO shop_tax_profiles (shop_id) VALUES (:s)", s=shop_id)
    user = _q(
        db,
        "INSERT INTO users (email, phone, full_name, password_hash, role)"
        " VALUES (:e, :p, :n, :h, 'owner') RETURNING id, role, shop_id, token_version",
        e=data.email,
        p=data.phone,
        n=data.owner_name,
        h=hash_password(data.password),
    ).one()
    _q(db, "INSERT INTO shop_owners (shop_id, owner_id) VALUES (:s, :o)", s=shop_id, o=user.id)
    _q(
        db,
        "INSERT INTO subscriptions (shop_id, plan_id, trial_ends_at)"
        " SELECT :s, id, now() + make_interval(days => :d) FROM plans WHERE code = 'standard_monthly'",
        s=shop_id,
        d=get_settings().trial_days,
    )
    return _issue(db, user, platform=data.platform, device=None)


def login(db: Session, data: LoginIn) -> IssuedTokens | AppError:
    """db is privileged (no actor yet). Errors are *returned* so the failed-attempt counter commits."""
    field = "phone" if data.login.isdigit() else "email"
    user = _q(
        db,
        f"SELECT id, role, shop_id, token_version, password_hash, is_active, locked_until"  # noqa: S608
        f" FROM users WHERE {field} = :v",
        v=data.login.strip().lower() if field == "email" else data.login,
    ).first()
    now = datetime.now(UTC)
    if user and user.locked_until and user.locked_until > now:
        return AppError("auth.locked", "Too many wrong attempts. Try again in a few minutes.", 429)
    if not verify_password(data.password, user.password_hash if user else None) or not user:
        if user:
            _q(
                db,
                "UPDATE users SET failed_logins = failed_logins + 1,"
                " locked_until = CASE WHEN failed_logins + 1 >= :m THEN :until END WHERE id = :i",
                m=MAX_FAILED_LOGINS,
                until=now + timedelta(minutes=LOCK_MINUTES),
                i=user.id,
            )
        return AppError("auth.invalid_credentials", "Wrong email/mobile or password.", 401)
    if not user.is_active:
        return AppError(
            "auth.inactive", "This account has been switched off. Contact your owner.", 403
        )
    _q(
        db,
        "UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = now() WHERE id = :i",
        i=user.id,
    )
    return _issue(db, user, platform=data.platform, device=data.device_label)


def refresh(db: Session, token: str) -> IssuedTokens | AppError:
    """Rotates the refresh token. Re-use of a rotated token revokes the whole family (committed)."""
    sess = _q(
        db,
        "SELECT s.id, s.family_id, s.platform, s.device_label, s.revoked_at, s.expires_at,"
        " u.id AS user_id, u.role, u.shop_id, u.token_version, u.is_active"
        " FROM auth_sessions s JOIN users u ON u.id = s.user_id WHERE s.refresh_hash = :h",
        h=hash_refresh_token(token),
    ).first()
    invalid = AppError("auth.session_expired", "Please log in again.", 401)
    if not sess:
        return invalid
    if sess.revoked_at is not None:
        _q(
            db,
            "UPDATE auth_sessions SET revoked_at = now() WHERE family_id = :f AND revoked_at IS NULL",
            f=sess.family_id,
        )
        return invalid
    if sess.expires_at <= datetime.now(UTC) or not sess.is_active:
        return invalid
    _q(
        db,
        "UPDATE auth_sessions SET revoked_at = now(), last_used_at = now() WHERE id = :i",
        i=sess.id,
    )
    user = type(
        "U",
        (),
        {
            "id": sess.user_id,
            "role": sess.role,
            "shop_id": sess.shop_id,
            "token_version": sess.token_version,
        },
    )
    return _issue(db, user, platform=sess.platform, device=sess.device_label, family=sess.family_id)


def logout(db: Session, token: str) -> None:
    fam = _q(
        db,
        "SELECT family_id FROM auth_sessions WHERE refresh_hash = :h",
        h=hash_refresh_token(token),
    ).scalar()
    if fam:
        _q(
            db,
            "UPDATE auth_sessions SET revoked_at = now() WHERE family_id = :f AND revoked_at IS NULL",
            f=fam,
        )


def logout_all(db: Session, user_id: uuid.UUID) -> None:
    _q(db, "UPDATE users SET token_version = token_version + 1 WHERE id = :i", i=user_id)
    _q(
        db,
        "UPDATE auth_sessions SET revoked_at = now() WHERE user_id = :i AND revoked_at IS NULL",
        i=user_id,
    )


RESET_MINUTES = 30
_TEMP_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o/1/l/i confusion when read aloud


def temp_password() -> str:
    import secrets

    return "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(10))


def forgot_password(db: Session, email: str) -> str | None:
    """Returns the raw reset token (to be emailed) or None. Caller always answers 200."""
    user = _q(
        db, "SELECT id FROM users WHERE email = :e AND is_active", e=email.strip().lower()
    ).first()
    if not user:
        return None
    token, token_hash = new_refresh_token()
    _q(
        db,
        "UPDATE password_reset_tokens SET used_at = now() WHERE user_id = :u AND used_at IS NULL",
        u=user.id,
    )
    _q(
        db,
        "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)"
        " VALUES (:u, :h, now() + make_interval(mins => :m))",
        u=user.id,
        h=token_hash,
        m=RESET_MINUTES,
    )
    return token


def _set_password(db: Session, user_id: uuid.UUID, password: str) -> None:
    """New password revokes every session and access token."""
    _q(
        db,
        "UPDATE users SET password_hash = :h, must_change_password = false, failed_logins = 0,"
        " locked_until = NULL, token_version = token_version + 1 WHERE id = :i",
        h=hash_password(password),
        i=user_id,
    )
    _q(
        db,
        "UPDATE auth_sessions SET revoked_at = now() WHERE user_id = :i AND revoked_at IS NULL",
        i=user_id,
    )


def reset_password(db: Session, token: str, password: str) -> None:
    row = _q(
        db,
        "UPDATE password_reset_tokens SET used_at = now()"
        " WHERE token_hash = :h AND used_at IS NULL AND expires_at > now() RETURNING user_id",
        h=hash_refresh_token(token),
    ).first()
    if not row:
        raise AppError(
            "auth.reset_invalid", "This reset link has expired. Please ask for a new one.", 400
        )
    _set_password(db, row.user_id, password)


def change_password(
    db: Session, user_id: uuid.UUID, old: str, new: str, platform: str
) -> IssuedTokens:
    u = _q(db, "SELECT password_hash FROM users WHERE id = :i", i=user_id).one()
    if not verify_password(old, u.password_hash):
        raise AppError("auth.wrong_password", "Your current password is not correct.", 400)
    if old == new:
        raise AppError(
            "auth.same_password", "Choose a password different from the current one.", 400
        )
    _set_password(db, user_id, new)
    user = _q(
        db, "SELECT id, role, shop_id, token_version FROM users WHERE id = :i", i=user_id
    ).one()
    return _issue(db, user, platform=platform, device=None)


def set_pin(db: Session, user_id: uuid.UUID, password: str, pin: str) -> None:
    u = _q(db, "SELECT password_hash FROM users WHERE id = :i", i=user_id).one()
    if not verify_password(password, u.password_hash):
        raise AppError("auth.wrong_password", "Your password is not correct.", 400)
    _q(db, "UPDATE users SET pin_hash = :h WHERE id = :i", h=hash_password(pin), i=user_id)

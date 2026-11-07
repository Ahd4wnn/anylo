"""Shop profile, GST tax profile, onboarding and staff management (docs/03, docs/06 §1)."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import media
from app.config import get_settings
from app.database import Actor
from app.errors import AppError
from app.permissions import allowed
from app.schemas.shop import NewShopIn, ShopPatch, StaffIn, StaffPatch, TaxProfileIn
from app.security import hash_password
from app.services import audit
from app.services.auth import temp_password
from app.services.gst.india import STATES

STAFF_COLS = "id, full_name, email, phone, role, is_active, last_login_at, must_change_password"


def _q(db: Session, sql: str, **p: Any) -> Any:
    return db.execute(text(sql), p)


def shop_id_of(actor: Actor) -> UUID:
    if not actor.shop_id:
        raise AppError("shop.choose", "Choose a shop first.", 400)
    return actor.shop_id


def get_shop(db: Session, actor: Actor) -> dict[str, Any]:
    sid = shop_id_of(actor)
    s = _q(db, "SELECT * FROM shops WHERE id = :s", s=sid).mappings().one()
    t = _q(db, "SELECT * FROM shop_tax_profiles WHERE shop_id = :s", s=sid).mappings().one()
    return {
        **s,
        "state_name": STATES[s["state_code"]],
        "logo_url": media.url(s["logo_path"]),
        "tax": dict(t),
    }


def update_shop(db: Session, actor: Actor, patch: ShopPatch) -> None:
    sid = shop_id_of(actor)
    data = patch.model_dump(exclude_unset=True)
    if {"upi_vpa", "upi_payee_name"} & data.keys() and not allowed(
        "shop.payment_details", actor.role
    ):
        raise AppError("shop.upi_owner_only", "Only the owner can change payment details.", 403)
    before = _q(db, "SELECT * FROM shops WHERE id = :s", s=sid).mappings().one()
    settings = data.pop("settings", None)
    if data:
        sets = ", ".join(f"{k} = :{k}" for k in data)  # keys are validated schema fields
        _q(db, f"UPDATE shops SET {sets} WHERE id = :sid", sid=sid, **data)
    if settings is not None:
        _q(
            db,
            "UPDATE shops SET settings = settings || CAST(:j AS jsonb) WHERE id = :s",
            j=json.dumps(settings),
            s=sid,
        )
    audit.record(
        db,
        actor,
        "shop",
        sid,
        "update",
        {k: before[k] for k in data},
        {**data, **({"settings": settings} if settings else {})},
    )


def put_tax_profile(db: Session, actor: Actor, data: TaxProfileIn) -> None:
    sid = shop_id_of(actor)
    before = _q(db, "SELECT * FROM shop_tax_profiles WHERE shop_id = :s", s=sid).mappings().one()
    try:
        with db.begin_nested():
            _q(
                db,
                "UPDATE shop_tax_profiles SET gst_scheme = :gst_scheme, gstin = :gstin, legal_name = :legal_name,"
                " trade_name = :trade_name, composition_rate = :composition_rate,"
                " prices_include_tax = :prices_include_tax, hsn_digits_required = :hsn_digits_required,"
                " invoice_round_off = :invoice_round_off, einvoice_applicable = :einvoice_applicable,"
                " filing_frequency = :filing_frequency WHERE shop_id = :sid",
                sid=sid,
                **data.model_dump(),
            )
    except IntegrityError:
        raise AppError(
            "shop.gstin_taken", "This GSTIN is already used by another shop on Anylo.", 409
        ) from None
    if data.gstin:  # the GSTIN's registration state is authoritative for place of supply
        _q(db, "UPDATE shops SET state_code = :c WHERE id = :s", c=data.gstin[:2], s=sid)
    _q(
        db,
        "UPDATE shops SET settings = settings || '{\"onboarding_tax\": true}' WHERE id = :s",
        s=sid,
    )
    audit.record(
        db, actor, "tax_profile", sid, "update", dict(before), data.model_dump(mode="json")
    )


def set_logo(db: Session, actor: Actor, data: bytes | None) -> str | None:
    sid = shop_id_of(actor)
    old = _q(db, "SELECT logo_path FROM shops WHERE id = :s", s=sid).scalar()
    path = media.save_image(data, f"logos/{sid}.webp", 512) if data else None
    if not data:
        media.delete(old)
    _q(db, "UPDATE shops SET logo_path = :p WHERE id = :s", p=path, s=sid)
    return media.url(path)


def onboarding(db: Session, actor: Actor) -> dict[str, bool]:
    sid = shop_id_of(actor)
    r = (
        _q(
            db,
            "SELECT address_line1 IS NOT NULL AND pincode IS NOT NULL AS details,"
            " coalesce((settings->>'onboarding_tax')::boolean, false) AS tax,"
            " logo_path IS NOT NULL AS logo, upi_vpa IS NOT NULL AS upi,"
            " EXISTS (SELECT 1 FROM users u WHERE u.shop_id = s.id) AS staff,"
            " onboarding_completed_at IS NOT NULL AS completed FROM shops s WHERE id = :s",
            s=sid,
        )
        .mappings()
        .one()
    )
    return {**r, "products": False}  # products step goes live with the catalogue (M2)


def complete_onboarding(db: Session, actor: Actor) -> None:
    _q(
        db,
        "UPDATE shops SET onboarding_completed_at = coalesce(onboarding_completed_at, now()) WHERE id = :s",
        s=shop_id_of(actor),
    )


def create_shop(db: Session, owner_id: UUID, data: NewShopIn) -> UUID:
    """Owner adds another shop; db is privileged because the owner is not yet linked to it."""
    sid: UUID = _q(
        db,
        "INSERT INTO shops (name, business_type, state_code) VALUES (:n, :b, :s) RETURNING id",
        n=data.name.strip(),
        b=data.business_type,
        s=data.state_code,
    ).scalar_one()
    _q(db, "INSERT INTO shop_tax_profiles (shop_id) VALUES (:s)", s=sid)
    _q(db, "INSERT INTO shop_owners (shop_id, owner_id) VALUES (:s, :o)", s=sid, o=owner_id)
    _q(
        db,
        "INSERT INTO subscriptions (shop_id, plan_id, trial_ends_at) SELECT :s, id,"
        " now() + make_interval(days => :d) FROM plans WHERE code = 'standard_monthly'",
        s=sid,
        d=get_settings().trial_days,
    )
    return sid


# --- staff ---


def _need_role_permission(actor: Actor, role: str) -> None:
    if role == "manager" and not allowed("staff.managers", actor.role):
        raise AppError("staff.managers_owner_only", "Only the owner can manage managers.", 403)


def _staff(db: Session, actor: Actor, user_id: UUID) -> Any:
    u = _q(db, f"SELECT {STAFF_COLS}, shop_id FROM users WHERE id = :i", i=user_id).first()
    if not u or u.shop_id != shop_id_of(actor):
        raise AppError("staff.not_found", "This staff member was not found.", 404)
    return u


def list_staff(db: Session, actor: Actor) -> list[Any]:
    return list(
        _q(
            db,
            f"SELECT {STAFF_COLS} FROM users WHERE shop_id = :s"
            " ORDER BY is_active DESC, role, full_name",
            s=shop_id_of(actor),
        )
    )


def create_staff(db: Session, actor: Actor, data: StaffIn) -> tuple[Any, str]:
    _need_role_permission(actor, data.role)
    password = temp_password()
    try:
        with db.begin_nested():
            u = _q(
                db,
                "INSERT INTO users (email, phone, full_name, password_hash, role, shop_id, must_change_password)"
                f" VALUES (:e, :p, :n, :h, :r, :s, true) RETURNING {STAFF_COLS}",
                e=str(data.email).lower(),
                p=data.phone,
                n=data.full_name.strip(),
                h=hash_password(password),
                r=data.role,
                s=shop_id_of(actor),
            ).one()
    except IntegrityError:
        raise AppError(
            "staff.exists", "Someone already uses this email or mobile on Anylo.", 409
        ) from None
    audit.record(db, actor, "staff", u.id, "create", None, {"email": u.email, "role": u.role})
    return u, password


def update_staff(db: Session, actor: Actor, user_id: UUID, patch: StaffPatch) -> Any:
    u = _staff(db, actor, user_id)
    _need_role_permission(actor, u.role)
    data = patch.model_dump(exclude_unset=True)
    if "role" in data:
        _need_role_permission(actor, data["role"])
    if user_id == actor.user_id and data.get("is_active") is False:
        raise AppError("staff.self_deactivate", "You can't switch off your own account.", 400)
    if data:
        sets = ", ".join(f"{k} = :{k}" for k in data)
        _q(db, f"UPDATE users SET {sets} WHERE id = :uid", uid=user_id, **data)
    if data.get("is_active") is False or "role" in data:
        _q(db, "UPDATE users SET token_version = token_version + 1 WHERE id = :i", i=user_id)
        _q(
            db,
            "UPDATE auth_sessions SET revoked_at = now() WHERE user_id = :i AND revoked_at IS NULL",
            i=user_id,
        )
    audit.record(db, actor, "staff", user_id, "update", {k: getattr(u, k) for k in data}, data)
    return _staff(db, actor, user_id)


def reset_staff_password(db: Session, actor: Actor, user_id: UUID) -> tuple[Any, str]:
    u = _staff(db, actor, user_id)
    _need_role_permission(actor, u.role)
    password = temp_password()
    _q(
        db,
        "UPDATE users SET password_hash = :h, must_change_password = true,"
        " token_version = token_version + 1, failed_logins = 0, locked_until = NULL WHERE id = :i",
        h=hash_password(password),
        i=user_id,
    )
    _q(
        db,
        "UPDATE auth_sessions SET revoked_at = now() WHERE user_id = :i AND revoked_at IS NULL",
        i=user_id,
    )
    audit.record(db, actor, "staff", user_id, "reset_password")
    return _staff(db, actor, user_id), password

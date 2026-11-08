"""Snap & Find: photo of any item → OpenAI vision → matching catalogue items (docs/01 §6, PlantBill plant scan)."""

import base64
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Actor, rls_session
from app.errors import AppError
from app.media import MAX_BYTES
from app.services import catalogue
from app.services.shop import shop_id_of

PROMPT = (
    "You identify retail products for an Indian shop's billing app. Look at the photo and reply with JSON only: "
    '{"name": short common product name a shopkeeper would type (include brand and size if readable), '
    '"category": simple category, "keywords": up to 4 search words}. If unsure, give your best guess.'
)


def _log(actor: Actor, name: str | None, ok: bool) -> None:
    # Own transaction: failed scans must still count towards usage (PlantBill lost them on rollback).
    with rls_session(actor) as db:
        db.execute(
            text(
                "INSERT INTO snap_scans (shop_id, user_id, identified_name, succeeded) VALUES (:s, :u, :n, :ok)"
            ),
            {"s": shop_id_of(actor), "u": actor.user_id, "n": name, "ok": ok},
        )


def identify(image: bytes, content_type: str) -> dict[str, Any]:
    s = get_settings()
    if not s.openai_api_key or not s.openai_model:
        raise AppError(
            "snap.not_configured",
            "Snap & Find isn't set up yet. Search or scan the barcode instead.",
            503,
        )
    if len(image) > MAX_BYTES or content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise AppError("snap.bad_image", "Use a JPG, PNG or WebP photo under 5 MB.", 415)
    from openai import OpenAI

    client = OpenAI(api_key=s.openai_api_key, timeout=30)
    url = f"data:{content_type};base64,{base64.b64encode(image).decode()}"
    resp = client.chat.completions.create(
        model=s.openai_model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            }
        ],
    )
    data: dict[str, Any] = json.loads(resp.choices[0].message.content or "{}")
    if not data.get("name"):
        raise AppError(
            "snap.unknown",
            "Couldn't recognise this item. Try another photo or search by name.",
            422,
        )
    return data


def snap(db: Session, actor: Actor, image: bytes, content_type: str) -> dict[str, Any]:
    try:
        found = identify(image, content_type)
    except AppError as e:
        if e.code != "snap.not_configured":
            _log(actor, None, False)
        raise
    except Exception:
        _log(actor, None, False)
        raise AppError(
            "snap.failed", "Snap & Find is busy. Try again or search by name.", 502
        ) from None
    _log(actor, found["name"], True)
    words = [found["name"], *found.get("keywords", [])][:5]
    ids = (
        db.execute(
            text(
                "SELECT p.id FROM products p WHERE p.shop_id = :s AND p.deleted_at IS NULL"
                " ORDER BY greatest("
                + ", ".join(f"similarity(p.name, :w{i})" for i in range(len(words)))
                + ") DESC LIMIT 5"
            ),
            {"s": shop_id_of(actor), **{f"w{i}": w for i, w in enumerate(words)}},
        )
        .scalars()
        .all()
    )
    matches = [catalogue.get_product(db, actor, pid) for pid in ids]
    return {"identified_name": found["name"], "category": found.get("category"), "matches": matches}

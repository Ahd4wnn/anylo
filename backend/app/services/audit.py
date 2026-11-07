import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import Actor


def record(
    db: Session,
    actor: Actor,
    entity: str,
    entity_id: object,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    db.execute(
        text(
            "INSERT INTO audit_log (shop_id, actor_id, actor_email, actor_role, entity, entity_id, action, before, after)"
            " VALUES (:s, :a, (SELECT email FROM users WHERE id = :a), :r, :e, :i, :ac,"
            " CAST(:b AS jsonb), CAST(:af AS jsonb))"
        ),
        {
            "s": actor.shop_id,
            "a": actor.user_id,
            "r": actor.role,
            "e": entity,
            "i": str(entity_id),
            "ac": action,
            "b": json.dumps(before, default=str) if before is not None else None,
            "af": json.dumps(after, default=str) if after is not None else None,
        },
    )

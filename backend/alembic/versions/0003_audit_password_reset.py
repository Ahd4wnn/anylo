"""audit log and password reset tokens

Revision ID: 0003
Revises: 0002
"""

from alembic import op

from app.rls import ROLE, enable_rls, tenant_predicate

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    x = op.execute
    # No FKs on purpose: audit rows must outlive whatever they describe.
    x("""
    CREATE TABLE audit_log (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      shop_id uuid,
      actor_id uuid,
      actor_email text,
      actor_role text,
      entity text NOT NULL,
      entity_id text,
      action text NOT NULL,
      before jsonb,
      after jsonb,
      at timestamptz NOT NULL DEFAULT now()
    )""")
    x("CREATE INDEX audit_log_shop_at ON audit_log (shop_id, at DESC)")
    # Readable by the shop's owners/managers and the platform; insert-only for everyone.
    for sql in enable_rls(
        "audit_log",
        f"{ROLE} IN ('admin','system') OR ({ROLE} IN ('owner','manager') AND ({tenant_predicate()}))",
        write_predicate=f"{ROLE} IN ('admin','system','support','owner','manager','salesperson')",
    ):
        x(sql)
    x("REVOKE UPDATE, DELETE ON audit_log FROM anylo_app")

    x("""
    CREATE TABLE password_reset_tokens (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      token_hash text NOT NULL UNIQUE,
      expires_at timestamptz NOT NULL,
      used_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    for sql in enable_rls("password_reset_tokens", f"{ROLE} IN ('admin','system')"):
        x(sql)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS password_reset_tokens, audit_log CASCADE")

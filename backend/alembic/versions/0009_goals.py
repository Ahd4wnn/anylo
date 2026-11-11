"""goals

Revision ID: 0009
Revises: 0008
"""

from alembic import op

from app.rls import enable_rls, tenant_predicate

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE goals (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      metric text NOT NULL CHECK (metric IN ('sales','gross_profit','net_profit','invoices_count','avg_bill_value','new_customers','collections')),
      title text NOT NULL,
      period_start date NOT NULL,
      period_end date NOT NULL CHECK (period_end >= period_start),
      target numeric(14,2) NOT NULL CHECK (target > 0),
      user_id uuid REFERENCES users(id) ON DELETE CASCADE,
      created_by uuid,
      created_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz
    )""")
    op.execute("CREATE INDEX goals_shop ON goals (shop_id, period_end) WHERE deleted_at IS NULL")
    for sql in enable_rls("goals", tenant_predicate()):
        op.execute(sql)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS goals")

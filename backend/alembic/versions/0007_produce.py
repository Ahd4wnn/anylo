"""shop type for vegetable and fruit sellers (sell by weight)

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

OLD = "'general','grocery','apparel','electronics','hardware','pharmacy','stationery','nursery','other'"


def upgrade() -> None:
    op.execute("ALTER TABLE shops DROP CONSTRAINT shops_business_type_check")
    op.execute(
        f"ALTER TABLE shops ADD CONSTRAINT shops_business_type_check CHECK (business_type IN ({OLD},'produce'))"
    )


def downgrade() -> None:
    op.execute("UPDATE shops SET business_type = 'grocery' WHERE business_type = 'produce'")
    op.execute("ALTER TABLE shops DROP CONSTRAINT shops_business_type_check")
    op.execute(
        f"ALTER TABLE shops ADD CONSTRAINT shops_business_type_check CHECK (business_type IN ({OLD}))"
    )

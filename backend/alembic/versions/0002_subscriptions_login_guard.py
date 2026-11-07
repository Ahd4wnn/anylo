"""plans, subscriptions (trial on signup) and login lockout columns

Revision ID: 0002
Revises: 0001
"""

from alembic import op

from app.rls import ROLE, enable_rls, tenant_predicate

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    x = op.execute
    x("ALTER TABLE users ADD COLUMN failed_logins integer NOT NULL DEFAULT 0")
    x("ALTER TABLE users ADD COLUMN locked_until timestamptz")

    x("""
    CREATE TABLE plans (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      code text NOT NULL UNIQUE,
      name text NOT NULL,
      price numeric(12,2) NOT NULL CHECK (price > 0),
      price_includes_tax boolean NOT NULL DEFAULT true,
      gst_rate numeric(5,2) NOT NULL DEFAULT 18,
      interval text NOT NULL DEFAULT 'month' CHECK (interval IN ('month','year')),
      razorpay_plan_id text,
      is_active boolean NOT NULL DEFAULT true
    )""")
    x("INSERT INTO plans (code, name, price) VALUES ('standard_monthly', 'Anylo Standard', 599.00)")
    x("GRANT SELECT ON plans TO anylo_app")

    x("""
    CREATE TABLE subscriptions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL UNIQUE REFERENCES shops(id) ON DELETE CASCADE,
      plan_id uuid NOT NULL REFERENCES plans(id),
      status text NOT NULL DEFAULT 'trialing' CHECK (status IN
        ('trialing','active','past_due','grace','expired','cancelled','comped')),
      trial_ends_at timestamptz NOT NULL,
      current_period_start timestamptz,
      current_period_end timestamptz,
      grace_ends_at timestamptz,
      comped_until timestamptz,
      cancel_at_period_end boolean NOT NULL DEFAULT false,
      razorpay_subscription_id text UNIQUE,
      razorpay_customer_id text,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    x(
        "CREATE TRIGGER subscriptions_touch BEFORE UPDATE ON subscriptions FOR EACH ROW EXECUTE FUNCTION touch_updated_at()"
    )
    # Shops can read their subscription; only the platform (webhooks/admin) changes it.
    for sql in enable_rls(
        "subscriptions",
        tenant_predicate(),
        write_predicate=f"{ROLE} IN ('admin','system','support')",
    ):
        x(sql)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS subscriptions, plans CASCADE")
    op.execute(
        "ALTER TABLE users DROP COLUMN IF EXISTS failed_logins, DROP COLUMN IF EXISTS locked_until"
    )

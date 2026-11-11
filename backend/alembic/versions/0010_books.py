"""books & compliance: line rate kind, filings, bank accounts + statements, expense GST, fixed assets, year locks, CA role

Revision ID: 0010
Revises: 0009
"""

from alembic import op

from app.rls import enable_rls, tenant_predicate

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TABLES = ("filings", "bank_accounts", "bank_lines", "fixed_assets", "book_locks")


def upgrade() -> None:
    x = op.execute
    # GST rate kind on every line, so composition turnover and Table 8 can tell exempt / nil / non-GST sales apart.
    x("ALTER TABLE invoice_lines ADD COLUMN rate_kind text NOT NULL DEFAULT 'taxable' CHECK (rate_kind IN ('taxable','nil','exempt','non_gst'))")
    x("""
    UPDATE invoice_lines l SET rate_kind = r.kind FROM product_variants v JOIN products p ON p.id = v.product_id
      JOIN gst_rates r ON r.id = p.tax_rate_id WHERE v.id = l.variant_id AND r.kind <> 'taxable'""")

    # Accountant (CA) login: read-only, shop-bound like staff.
    x("ALTER TABLE users DROP CONSTRAINT users_role_check")
    x("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('admin','support','owner','manager','salesperson','accountant'))")
    x("ALTER TABLE users DROP CONSTRAINT users_check")
    x("ALTER TABLE users ADD CONSTRAINT users_check CHECK ((role IN ('manager','salesperson','accountant')) = (shop_id IS NOT NULL))")

    x("""
    CREATE TABLE filings (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      return_type text NOT NULL CHECK (return_type IN ('GSTR1','GSTR3B','CMP08','GSTR4','GSTR9','ITR','ADVANCE_TAX','TDS','OTHER')),
      period text NOT NULL,
      filed_on date NOT NULL,
      arn text,
      tax_paid numeric(12,2) NOT NULL DEFAULT 0 CHECK (tax_paid >= 0),
      note text,
      created_by uuid,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (shop_id, return_type, period)
    )""")

    x("""
    CREATE TABLE bank_accounts (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      name text NOT NULL,
      account_last4 text CHECK (account_last4 ~ '^[0-9]{4}$'),
      opening_balance numeric(12,2) NOT NULL DEFAULT 0,
      is_default boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz
    )""")
    x("CREATE UNIQUE INDEX bank_accounts_default ON bank_accounts (shop_id) WHERE is_default AND deleted_at IS NULL")
    # Non-cash money is placed in a bank account; NULL means the shop's default account.
    x("ALTER TABLE payments ADD COLUMN bank_account_id uuid REFERENCES bank_accounts(id) ON DELETE SET NULL")
    x("""
    CREATE TABLE bank_lines (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      bank_account_id uuid NOT NULL REFERENCES bank_accounts(id) ON DELETE CASCADE,
      txn_date date NOT NULL,
      description text NOT NULL DEFAULT '',
      reference text NOT NULL DEFAULT '',
      amount numeric(12,2) NOT NULL CHECK (amount <> 0),
      payment_id uuid REFERENCES payments(id) ON DELETE SET NULL,
      imported_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (bank_account_id, txn_date, amount, reference, description)
    )""")
    x("CREATE UNIQUE INDEX bank_lines_payment ON bank_lines (payment_id) WHERE payment_id IS NOT NULL")

    # Opening cash at the day the shop starts keeping books in Anylo.
    x("ALTER TABLE shops ADD COLUMN books_start date, ADD COLUMN opening_cash numeric(12,2) NOT NULL DEFAULT 0")

    # Expenses: the supplier's GST bill, ITC, and reverse charge (rent from a registered landlord, GTA freight, legal fees).
    x("""
    ALTER TABLE expenses
      ADD COLUMN supplier_name text, ADD COLUMN supplier_gstin text, ADD COLUMN bill_no text,
      ADD COLUMN itc_eligible boolean NOT NULL DEFAULT false,
      ADD COLUMN reverse_charge boolean NOT NULL DEFAULT false,
      ADD COLUMN rcm_rate numeric(5,2) CHECK (rcm_rate >= 0)""")
    # Before this, GST on an expense counted as claimable for regular shops; keep that for old rows.
    x("""
    UPDATE expenses e SET itc_eligible = true FROM shop_tax_profiles t
      WHERE t.shop_id = e.shop_id AND t.gst_scheme = 'regular' AND coalesce(e.gst_amount, 0) > 0""")

    x("""
    CREATE TABLE fixed_assets (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      name text NOT NULL,
      block text NOT NULL CHECK (block IN ('furniture','plant','computer','vehicle','building')),
      cost numeric(12,2) NOT NULL CHECK (cost > 0),
      bought_on date NOT NULL,
      paid_method text CHECK (paid_method IN ('cash','upi','bank','cheque')),
      sold_on date, sale_value numeric(12,2),
      created_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz
    )""")

    # A closed financial year can't be changed (expenses, wages, purchases, bills dated inside it).
    x("""
    CREATE TABLE book_locks (
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      fy text NOT NULL,
      locked_until date NOT NULL,
      locked_by uuid,
      locked_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (shop_id, fy)
    )""")
    for t in TABLES:
        for sql in enable_rls(t, tenant_predicate()):
            x(sql)


def downgrade() -> None:
    x = op.execute
    x(f"DROP TABLE IF EXISTS {', '.join(reversed(TABLES))} CASCADE")
    x("ALTER TABLE payments DROP COLUMN IF EXISTS bank_account_id")
    x("ALTER TABLE shops DROP COLUMN books_start, DROP COLUMN opening_cash")
    x(
        "ALTER TABLE expenses DROP COLUMN supplier_name, DROP COLUMN supplier_gstin, DROP COLUMN bill_no,"
        " DROP COLUMN itc_eligible, DROP COLUMN reverse_charge, DROP COLUMN rcm_rate"
    )
    x("ALTER TABLE invoice_lines DROP COLUMN rate_kind")
    x("DELETE FROM users WHERE role = 'accountant'")
    x("ALTER TABLE users DROP CONSTRAINT users_role_check")
    x("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('admin','support','owner','manager','salesperson'))")
    x("ALTER TABLE users DROP CONSTRAINT users_check")
    x("ALTER TABLE users ADD CONSTRAINT users_check CHECK ((role IN ('manager','salesperson')) = (shop_id IS NOT NULL))")

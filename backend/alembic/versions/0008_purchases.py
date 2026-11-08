"""purchases: suppliers, purchases + lines, supplier balances, stock counts

Revision ID: 0008
Revises: 0007
"""

from alembic import op

from app.rls import enable_rls, tenant_predicate

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TABLES = ("suppliers", "purchases", "purchase_lines", "stock_counts", "stock_count_lines")


def upgrade() -> None:
    x = op.execute
    x("""
    CREATE TABLE suppliers (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      name text NOT NULL CHECK (length(trim(name)) > 0),
      gstin text, phone text, email text, address text,
      state_code text REFERENCES gst_states(code),
      opening_balance numeric(12,2) NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz
    )""")
    x(
        "CREATE UNIQUE INDEX suppliers_name ON suppliers (shop_id, lower(name)) WHERE deleted_at IS NULL"
    )
    x("""
    CREATE TABLE purchases (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      supplier_id uuid NOT NULL REFERENCES suppliers(id),
      supplier_invoice_no text,
      supplier_invoice_date date,
      supply_type text NOT NULL CHECK (supply_type IN ('intra','inter')),
      taxable_total numeric(12,2) NOT NULL DEFAULT 0,
      cgst_total numeric(12,2) NOT NULL DEFAULT 0, sgst_total numeric(12,2) NOT NULL DEFAULT 0,
      igst_total numeric(12,2) NOT NULL DEFAULT 0, cess_total numeric(12,2) NOT NULL DEFAULT 0,
      round_off numeric(12,2) NOT NULL DEFAULT 0,
      grand_total numeric(12,2) NOT NULL DEFAULT 0,
      itc_eligible boolean NOT NULL,
      status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','posted','cancelled')),
      notes text,
      idempotency_key text NOT NULL,
      created_by uuid, created_by_name text,
      created_at timestamptz NOT NULL DEFAULT now(),
      posted_at timestamptz, cancelled_at timestamptz,
      CHECK (grand_total = taxable_total + cgst_total + sgst_total + igst_total + cess_total + round_off)
    )""")
    x("CREATE UNIQUE INDEX purchases_idem ON purchases (shop_id, idempotency_key)")
    # The same supplier bill can't be entered twice (a common double-counting mistake).
    x(
        "CREATE UNIQUE INDEX purchases_supplier_bill ON purchases (supplier_id, lower(supplier_invoice_no))"
        " WHERE supplier_invoice_no IS NOT NULL AND status <> 'cancelled'"
    )
    x("CREATE INDEX purchases_shop_time ON purchases (shop_id, created_at DESC)")
    x("""
    CREATE TABLE purchase_lines (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      purchase_id uuid NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
      line_no integer NOT NULL,
      variant_id uuid NOT NULL REFERENCES product_variants(id),
      description text NOT NULL, hsn_code text,
      qty numeric(12,3) NOT NULL CHECK (qty > 0),
      unit_cost numeric(12,2) NOT NULL CHECK (unit_cost >= 0),
      discount numeric(12,2) NOT NULL DEFAULT 0,
      taxable numeric(12,2) NOT NULL, tax_rate numeric(5,2) NOT NULL,
      cgst numeric(12,2) NOT NULL, sgst numeric(12,2) NOT NULL, igst numeric(12,2) NOT NULL, cess numeric(12,2) NOT NULL,
      line_total numeric(12,2) NOT NULL
    )""")
    x("""
    CREATE VIEW supplier_balances WITH (security_invoker = true) AS
    SELECT s.id AS supplier_id, s.shop_id,
      s.opening_balance
      + coalesce((SELECT sum(p.grand_total) FROM purchases p WHERE p.supplier_id = s.id AND p.status = 'posted'), 0)
      - coalesce((SELECT sum(m.amount) FROM payments m WHERE m.party_type = 'supplier' AND m.party_id = s.id
                  AND m.direction = 'out' AND m.status = 'confirmed'), 0)
      AS balance
    FROM suppliers s""")
    x("GRANT SELECT ON supplier_balances TO anylo_app")
    x("""
    CREATE TABLE stock_counts (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      name text NOT NULL,
      category_id uuid REFERENCES categories(id) ON DELETE SET NULL,
      status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','posted','cancelled')),
      started_by uuid, started_by_name text, posted_by uuid, posted_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    x("""
    CREATE TABLE stock_count_lines (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      count_id uuid NOT NULL REFERENCES stock_counts(id) ON DELETE CASCADE,
      variant_id uuid NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
      expected_qty numeric(12,3) NOT NULL,
      counted_qty numeric(12,3) CHECK (counted_qty >= 0),
      unit_cost numeric(12,2) NOT NULL DEFAULT 0,
      UNIQUE (count_id, variant_id)
    )""")
    for t in TABLES:
        for sql in enable_rls(t, tenant_predicate()):
            x(sql)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS supplier_balances")
    op.execute(f"DROP TABLE IF EXISTS {', '.join(reversed(TABLES))} CASCADE")

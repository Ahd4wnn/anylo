"""money: customer profiles + balances, approvals, credit notes, expenses, labour, borrowings, day close

Revision ID: 0006
Revises: 0005
"""

from alembic import op

from app.rls import enable_rls, tenant_predicate

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TABLES = (
    "approval_requests",
    "credit_notes",
    "credit_note_lines",
    "expense_categories",
    "expenses",
    "labourers",
    "labour_attendance",
    "labour_payments",
    "borrowings",
    "day_closes",
)


def upgrade() -> None:
    x = op.execute
    x("""
    ALTER TABLE customers
      ADD COLUMN email text,
      ADD COLUMN credit_limit numeric(12,2) CHECK (credit_limit >= 0),
      ADD COLUMN opening_balance numeric(12,2) NOT NULL DEFAULT 0,
      ADD COLUMN notes text,
      ADD COLUMN tags text[] NOT NULL DEFAULT '{}',
      ADD COLUMN deleted_at timestamptz""")
    # batch_id groups the rows of one collection (FIFO across invoices) under one receipt number.
    x("""
    ALTER TABLE payments
      ADD COLUMN batch_id uuid,
      ADD COLUMN receipt_no text,
      ADD COLUMN note text,
      ADD COLUMN approved_by uuid,
      ADD COLUMN approved_at timestamptz,
      ADD COLUMN idempotency_key text""")
    x(
        "CREATE UNIQUE INDEX payments_idem ON payments (shop_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
    )
    x("CREATE INDEX payments_party ON payments (party_type, party_id)")
    x("CREATE INDEX payments_batch ON payments (batch_id) WHERE batch_id IS NOT NULL")

    x("""
    CREATE TABLE approval_requests (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      kind text NOT NULL CHECK (kind IN ('collection','return','cash_close')),
      ref_id uuid,
      summary text NOT NULL,
      amount numeric(12,2),
      payload jsonb NOT NULL DEFAULT '{}',
      requested_by uuid, requested_by_name text,
      status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
      decided_by uuid, decided_at timestamptz, note text,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    x(
        "CREATE INDEX approvals_pending ON approval_requests (shop_id, created_at) WHERE status = 'pending'"
    )

    # Sales returns (docs/06-gst.md §11): same rates and place of supply as the original invoice.
    x("""
    CREATE TABLE credit_notes (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      series_key text NOT NULL, fy text NOT NULL, seq integer NOT NULL,
      number text NOT NULL CHECK (length(number) <= 16),
      original_invoice_id uuid REFERENCES invoices(id),
      customer_id uuid REFERENCES customers(id) ON DELETE SET NULL,
      reason text NOT NULL DEFAULT 'return' CHECK (reason IN ('return','discount','correction')),
      refund_method text NOT NULL CHECK (refund_method IN ('cash','upi','store_credit')),
      restock boolean NOT NULL,
      place_of_supply text NOT NULL, supply_type text NOT NULL,
      taxable_total numeric(12,2) NOT NULL,
      cgst_total numeric(12,2) NOT NULL, sgst_total numeric(12,2) NOT NULL,
      igst_total numeric(12,2) NOT NULL, cess_total numeric(12,2) NOT NULL,
      round_off numeric(12,2) NOT NULL,
      grand_total numeric(12,2) NOT NULL CHECK (grand_total > 0),
      due_adjusted numeric(12,2) NOT NULL DEFAULT 0,
      refunded numeric(12,2) NOT NULL DEFAULT 0,
      note text,
      idempotency_key text NOT NULL,
      issued_at timestamptz NOT NULL DEFAULT now(),
      created_by uuid, created_by_name text,
      CHECK (grand_total = taxable_total + cgst_total + sgst_total + igst_total + cess_total + round_off),
      CHECK (reason = 'discount' OR original_invoice_id IS NOT NULL)
    )""")
    x("CREATE UNIQUE INDEX credit_notes_number ON credit_notes (series_key, fy, number)")
    x("CREATE INDEX credit_notes_invoice ON credit_notes (original_invoice_id)")
    x("CREATE UNIQUE INDEX credit_notes_idem ON credit_notes (shop_id, idempotency_key)")
    x("""
    CREATE TABLE credit_note_lines (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      credit_note_id uuid NOT NULL REFERENCES credit_notes(id) ON DELETE CASCADE,
      invoice_line_id uuid REFERENCES invoice_lines(id),
      variant_id uuid REFERENCES product_variants(id) ON DELETE SET NULL,
      name text NOT NULL, hsn_code text, unit_code text NOT NULL,
      qty numeric(12,3) NOT NULL CHECK (qty > 0),
      taxable numeric(12,2) NOT NULL, tax_rate numeric(5,2) NOT NULL,
      cgst numeric(12,2) NOT NULL, sgst numeric(12,2) NOT NULL, igst numeric(12,2) NOT NULL, cess numeric(12,2) NOT NULL,
      line_total numeric(12,2) NOT NULL,
      cost_price numeric(12,2) NOT NULL DEFAULT 0
    )""")
    x("REVOKE DELETE ON credit_notes FROM anylo_app")

    # One ledger for every customer: what they bought, paid, returned and were refunded.
    x("""
    CREATE VIEW customer_balances WITH (security_invoker = true) AS
    SELECT c.id AS customer_id, c.shop_id,
      c.opening_balance
      + coalesce((SELECT sum(i.grand_total) FROM invoices i WHERE i.customer_id = c.id AND i.status = 'issued'), 0)
      - coalesce((SELECT sum(p.amount) FROM payments p WHERE p.party_type = 'customer' AND p.party_id = c.id
                  AND p.direction = 'in' AND p.status = 'confirmed' AND p.method <> 'store_credit'), 0)
      - coalesce((SELECT sum(n.grand_total) FROM credit_notes n WHERE n.customer_id = c.id), 0)
      + coalesce((SELECT sum(p.amount) FROM payments p WHERE p.party_type = 'customer' AND p.party_id = c.id
                  AND p.direction = 'out' AND p.status = 'confirmed'), 0)
      AS balance
    FROM customers c""")
    x("GRANT SELECT ON customer_balances TO anylo_app")

    x("""
    CREATE TABLE expense_categories (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      name text NOT NULL,
      is_system boolean NOT NULL DEFAULT false
    )""")
    x("CREATE UNIQUE INDEX expense_categories_name ON expense_categories (shop_id, lower(name))")
    x("""
    CREATE TABLE expenses (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      category_id uuid REFERENCES expense_categories(id) ON DELETE SET NULL,
      category_name text NOT NULL,
      amount numeric(12,2) NOT NULL CHECK (amount > 0),
      method text NOT NULL CHECK (method IN ('cash','upi','card','bank','cheque')),
      gst_amount numeric(12,2) CHECK (gst_amount >= 0),
      note text,
      occurred_on date NOT NULL,
      created_by uuid, created_by_name text,
      created_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz
    )""")
    x(
        "CREATE INDEX expenses_shop_day ON expenses (shop_id, occurred_on DESC) WHERE deleted_at IS NULL"
    )

    # Labour, ported from PlantBill (wage rules live in services/labour_wages.py).
    x("""
    CREATE TABLE labourers (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      name text NOT NULL,
      phone text,
      aadhaar_last4 text CHECK (aadhaar_last4 ~ '^[0-9]{4}$'),
      gender text NOT NULL CHECK (gender IN ('male','female','other')),
      wage_type text NOT NULL DEFAULT 'daily' CHECK (wage_type IN ('daily','monthly')),
      daily_wage numeric(12,2) NOT NULL DEFAULT 0 CHECK (daily_wage >= 0),
      monthly_wage numeric(12,2) NOT NULL DEFAULT 0 CHECK (monthly_wage >= 0),
      paid_leaves_per_month integer NOT NULL DEFAULT 0 CHECK (paid_leaves_per_month BETWEEN 0 AND 31),
      joined_on date NOT NULL,
      is_active boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz
    )""")
    x("""
    CREATE TABLE labour_attendance (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      labourer_id uuid NOT NULL REFERENCES labourers(id) ON DELETE CASCADE,
      day date NOT NULL,
      status text NOT NULL CHECK (status IN ('present','half_day','absent')),
      marked_by uuid,
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (labourer_id, day)
    )""")
    x("""
    CREATE TABLE labour_payments (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      labourer_id uuid NOT NULL REFERENCES labourers(id) ON DELETE CASCADE,
      kind text NOT NULL CHECK (kind IN ('wage','advance','due_clear')),
      amount numeric(12,2) NOT NULL CHECK (amount > 0),
      days numeric(6,1),
      note text,
      paid_on date NOT NULL,
      created_by uuid, created_by_name text,
      created_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz
    )""")

    x("""
    CREATE TABLE borrowings (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      lender_name text NOT NULL,
      lender_phone text,
      principal numeric(12,2) NOT NULL CHECK (principal > 0),
      received_method text NOT NULL CHECK (received_method IN ('cash','upi','bank','cheque')),
      interest_note text,
      borrowed_on date NOT NULL,
      status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
      created_by uuid,
      created_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz
    )""")

    # One register per shop in v1, so the register column is left out until a second one exists.
    x("""
    CREATE TABLE day_closes (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      business_date date NOT NULL,
      opening_cash numeric(12,2) NOT NULL,
      cash_in numeric(12,2) NOT NULL,
      cash_out numeric(12,2) NOT NULL,
      expected_cash numeric(12,2) NOT NULL,
      counted_cash numeric(12,2) NOT NULL CHECK (counted_cash >= 0),
      difference numeric(12,2) NOT NULL,
      note text,
      status text NOT NULL CHECK (status IN ('pending','confirmed','rejected')),
      closed_by uuid, closed_by_name text, confirmed_by uuid,
      created_at timestamptz NOT NULL DEFAULT now(),
      CHECK (expected_cash = opening_cash + cash_in - cash_out),
      CHECK (difference = counted_cash - expected_cash)
    )""")
    x(
        "CREATE UNIQUE INDEX day_closes_day ON day_closes (shop_id, business_date) WHERE status <> 'rejected'"
    )

    for t in TABLES:
        for sql in enable_rls(t, tenant_predicate()):
            x(sql)


def downgrade() -> None:
    x = op.execute
    x("DROP VIEW IF EXISTS customer_balances")
    x(f"DROP TABLE IF EXISTS {', '.join(reversed(TABLES))} CASCADE")
    x("DROP INDEX IF EXISTS payments_idem, payments_party, payments_batch")
    x(
        "ALTER TABLE payments DROP COLUMN batch_id, DROP COLUMN receipt_no, DROP COLUMN note, DROP COLUMN approved_by,"
        " DROP COLUMN approved_at, DROP COLUMN idempotency_key"
    )
    x(
        "ALTER TABLE customers DROP COLUMN email, DROP COLUMN credit_limit, DROP COLUMN opening_balance, DROP COLUMN notes,"
        " DROP COLUMN tags, DROP COLUMN deleted_at"
    )

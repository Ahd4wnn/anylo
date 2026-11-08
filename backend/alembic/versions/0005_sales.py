"""sales: customers, document series, invoices, lines, payments, held bills, snap scans

Revision ID: 0005
Revises: 0004
"""

from alembic import op

from app.rls import enable_rls, tenant_predicate

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    x = op.execute
    # Minimal customer record for checkout; M4 adds the ledger and profile screens.
    x("""
    CREATE TABLE customers (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      name text,
      phone text CHECK (phone ~ '^[6-9][0-9]{9}$'),
      gstin text,
      billing_address text,
      state_code text REFERENCES gst_states(code),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    x(
        "CREATE UNIQUE INDEX customers_shop_phone ON customers (shop_id, phone) WHERE phone IS NOT NULL"
    )
    x(
        "CREATE TRIGGER customers_touch BEFORE UPDATE ON customers FOR EACH ROW EXECUTE FUNCTION touch_updated_at()"
    )

    # Gapless numbering per GSTIN (or shop when unregistered) per financial year (docs/06-gst.md §6).
    x("""
    CREATE TABLE doc_series (
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      kind text NOT NULL CHECK (kind IN ('sale','credit_note','receipt')),
      fy text NOT NULL,
      prefix text NOT NULL,
      next_seq integer NOT NULL DEFAULT 1,
      PRIMARY KEY (shop_id, kind, fy)
    )""")

    x("""
    CREATE TABLE invoices (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      series_key text NOT NULL,
      fy text NOT NULL,
      seq integer NOT NULL,
      number text NOT NULL CHECK (length(number) <= 16),
      doc_type text NOT NULL CHECK (doc_type IN ('tax_invoice','bill_of_supply','cash_memo')),
      issued_at timestamptz NOT NULL DEFAULT now(),
      customer_id uuid REFERENCES customers(id) ON DELETE SET NULL,
      buyer_name text, buyer_phone text, buyer_gstin text, buyer_address text, buyer_state_code text,
      place_of_supply text NOT NULL REFERENCES gst_states(code),
      supply_type text NOT NULL CHECK (supply_type IN ('intra','inter')),
      delivery_mode text NOT NULL DEFAULT 'counter' CHECK (delivery_mode IN ('counter','dispatched')),
      delivery_address text,
      is_b2b boolean NOT NULL DEFAULT false,
      scheme text NOT NULL,
      subtotal_gross numeric(12,2) NOT NULL,
      discount_type text CHECK (discount_type IN ('flat','percent')),
      discount_value numeric(12,2) NOT NULL DEFAULT 0,
      discount_total numeric(12,2) NOT NULL,
      taxable_total numeric(12,2) NOT NULL,
      cgst_total numeric(12,2) NOT NULL, sgst_total numeric(12,2) NOT NULL,
      igst_total numeric(12,2) NOT NULL, cess_total numeric(12,2) NOT NULL,
      round_off numeric(12,2) NOT NULL,
      grand_total numeric(12,2) NOT NULL,
      paid_total numeric(12,2) NOT NULL DEFAULT 0,
      due_total numeric(12,2) NOT NULL DEFAULT 0,
      status text NOT NULL DEFAULT 'issued' CHECK (status IN ('issued','cancelled')),
      cancel_reason text, cancelled_at timestamptz, cancelled_by uuid,
      is_edited boolean NOT NULL DEFAULT false,
      handed_over_at timestamptz,
      remarks text,
      idempotency_key text NOT NULL,
      public_token text NOT NULL UNIQUE,
      created_by uuid, created_by_name text,
      created_at timestamptz NOT NULL DEFAULT now(),
      CHECK (grand_total = taxable_total + cgst_total + sgst_total + igst_total + cess_total + round_off),
      CHECK (due_total >= 0 AND paid_total >= 0)
    )""")
    x("CREATE UNIQUE INDEX invoices_number ON invoices (series_key, fy, number)")
    x("CREATE UNIQUE INDEX invoices_idem ON invoices (shop_id, idempotency_key)")
    x("CREATE INDEX invoices_shop_issued ON invoices (shop_id, issued_at DESC)")
    x("CREATE INDEX invoices_customer ON invoices (customer_id)")

    x("""
    CREATE TABLE invoice_lines (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      invoice_id uuid NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
      line_no integer NOT NULL,
      variant_id uuid REFERENCES product_variants(id) ON DELETE SET NULL,
      name text NOT NULL, variant_name text, hsn_code text, unit_code text NOT NULL,
      qty numeric(12,3) NOT NULL CHECK (qty > 0),
      unit_price numeric(12,2) NOT NULL,
      price_includes_tax boolean NOT NULL,
      gross numeric(12,2) NOT NULL, line_discount numeric(12,2) NOT NULL, invoice_discount_share numeric(12,2) NOT NULL,
      taxable numeric(12,2) NOT NULL, tax_rate numeric(5,2) NOT NULL, cess_rate numeric(5,2) NOT NULL,
      cgst numeric(12,2) NOT NULL, sgst numeric(12,2) NOT NULL, igst numeric(12,2) NOT NULL, cess numeric(12,2) NOT NULL,
      line_total numeric(12,2) NOT NULL,
      cost_price numeric(12,2) NOT NULL DEFAULT 0,
      returned_qty numeric(12,3) NOT NULL DEFAULT 0
    )""")
    x("CREATE INDEX invoice_lines_invoice ON invoice_lines (invoice_id, line_no)")

    x("""
    CREATE TABLE payments (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      direction text NOT NULL CHECK (direction IN ('in','out')),
      method text NOT NULL CHECK (method IN ('cash','upi','card','bank','cheque','store_credit','other')),
      amount numeric(12,2) NOT NULL CHECK (amount > 0),
      reference text,
      party_type text, party_id uuid,
      applies_to_type text, applies_to_id uuid,
      status text NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed','pending_approval','rejected','reversed')),
      received_by uuid,
      occurred_at timestamptz NOT NULL DEFAULT now()
    )""")
    x("CREATE INDEX payments_applies ON payments (applies_to_type, applies_to_id)")
    x("CREATE INDEX payments_shop_time ON payments (shop_id, occurred_at DESC)")

    x("""
    CREATE TABLE held_bills (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      created_by uuid, created_by_name text,
      label text NOT NULL,
      payload jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")

    x("""
    CREATE TABLE snap_scans (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      user_id uuid, identified_name text, succeeded boolean NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")

    for t in (
        "customers",
        "doc_series",
        "invoices",
        "invoice_lines",
        "payments",
        "held_bills",
        "snap_scans",
    ):
        for sql in enable_rls(t, tenant_predicate()):
            x(sql)
    # Invoices are never deleted (cancel keeps the number); lines/payments only change via the service.
    x("REVOKE DELETE ON invoices FROM anylo_app")


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS snap_scans, held_bills, payments, invoice_lines, invoices, doc_series, customers CASCADE"
    )

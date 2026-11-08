"""catalogue and stock: categories, products, variants, stock movements

Revision ID: 0004
Revises: 0003
"""

from alembic import op

from app.rls import enable_rls, tenant_predicate

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    x = op.execute
    # Per-shop counters for auto SKU (AN-000001) and internal EAN-13 barcodes (prefix 2).
    x("ALTER TABLE shops ADD COLUMN next_sku_seq integer NOT NULL DEFAULT 1")
    x("ALTER TABLE shops ADD COLUMN next_ean_seq bigint NOT NULL DEFAULT 1")

    x("""
    CREATE TABLE categories (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      name text NOT NULL CHECK (length(trim(name)) > 0),
      sort_order integer NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    x("CREATE UNIQUE INDEX categories_shop_name ON categories (shop_id, lower(name))")

    x("""
    CREATE TABLE products (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      category_id uuid REFERENCES categories(id) ON DELETE SET NULL,
      name text NOT NULL CHECK (length(trim(name)) > 0),
      description text,
      brand text,
      hsn_code text CHECK (hsn_code ~ '^[0-9]{4,8}$'),
      is_service boolean NOT NULL DEFAULT false,
      tax_rate_id uuid REFERENCES gst_rates(id),
      cess_rate numeric(5,2) NOT NULL DEFAULT 0 CHECK (cess_rate >= 0),
      price_includes_tax boolean NOT NULL DEFAULT true,
      unit_code text NOT NULL DEFAULT 'NOS' REFERENCES units(code),
      track_stock boolean NOT NULL DEFAULT true,
      photo_path text,
      deleted_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    x("CREATE INDEX products_shop ON products (shop_id) WHERE deleted_at IS NULL")
    x("CREATE INDEX products_name_trgm ON products USING gin (name gin_trgm_ops)")
    x(
        "CREATE TRIGGER products_touch BEFORE UPDATE ON products FOR EACH ROW EXECUTE FUNCTION touch_updated_at()"
    )

    x("""
    CREATE TABLE product_variants (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
      name text,
      sku text NOT NULL,
      barcode text,
      mrp numeric(12,2) CHECK (mrp >= 0),
      sale_price numeric(12,2) NOT NULL CHECK (sale_price >= 0),
      cost_price numeric(12,2) NOT NULL DEFAULT 0 CHECK (cost_price >= 0),
      reorder_level numeric(12,3) NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
      stock_qty numeric(12,3) NOT NULL DEFAULT 0,
      is_active boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      -- Legal Metrology: never sell above printed MRP (docs/06-gst.md CA note F16).
      CHECK (mrp IS NULL OR sale_price <= mrp)
    )""")
    x("CREATE UNIQUE INDEX variants_shop_sku ON product_variants (shop_id, lower(sku))")
    x(
        "CREATE UNIQUE INDEX variants_shop_barcode ON product_variants (shop_id, barcode) WHERE barcode IS NOT NULL"
    )
    x("CREATE INDEX variants_product ON product_variants (product_id)")
    x(
        "CREATE TRIGGER variants_touch BEFORE UPDATE ON product_variants FOR EACH ROW EXECUTE FUNCTION touch_updated_at()"
    )

    # Append-only ledger; product_variants.stock_qty is a cache kept in the same transaction.
    x("""
    CREATE TABLE stock_movements (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      variant_id uuid NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
      kind text NOT NULL CHECK (kind IN ('opening','purchase','sale','sale_return','purchase_return',
        'adjustment','damage','transfer_in','transfer_out')),
      qty numeric(12,3) NOT NULL CHECK (qty <> 0),
      unit_cost numeric(12,2) NOT NULL DEFAULT 0,
      ref_type text, ref_id text, reason text,
      created_by uuid,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    x("CREATE INDEX stock_movements_variant ON stock_movements (variant_id, created_at DESC)")
    x("CREATE INDEX stock_movements_shop ON stock_movements (shop_id, created_at DESC)")

    for t in ("categories", "products", "product_variants", "stock_movements"):
        for sql in enable_rls(t, tenant_predicate()):
            x(sql)
    x("REVOKE UPDATE, DELETE ON stock_movements FROM anylo_app")


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS stock_movements, product_variants, products, categories CASCADE"
    )
    op.execute(
        "ALTER TABLE shops DROP COLUMN IF EXISTS next_sku_seq, DROP COLUMN IF EXISTS next_ean_seq"
    )

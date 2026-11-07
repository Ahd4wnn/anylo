"""core tenancy: reference data, shops, tax profiles, users, owners, sessions

Revision ID: 0001
Revises:
"""

from alembic import op

from app.rls import ROLE, SHOP, USER, enable_rls, owner_shops, tenant_predicate
from app.services.gst.india import STATES, UTGST_STATES

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UNITS = [
    ("NOS", "Numbers", False),
    ("PCS", "Pieces", False),
    ("KGS", "Kilograms", True),
    ("GMS", "Grams", True),
    ("LTR", "Litres", True),
    ("MLT", "Millilitres", True),
    ("MTR", "Metres", True),
    ("BOX", "Box", False),
    ("PAC", "Packs", False),
    ("DOZ", "Dozens", False),
    ("SET", "Sets", False),
    ("PRS", "Pairs", False),
    ("BAG", "Bags", False),
    ("BTL", "Bottles", False),
    ("ROL", "Rolls", False),
]
# docs/06-gst.md §3 (CA-reviewed 2026-11-08)
RATES = [
    ("Nil", "0", "nil", "2017-07-01", None),
    ("Exempt", "0", "exempt", "2017-07-01", None),
    ("Non-GST", "0", "non_gst", "2017-07-01", None),
    ("0.25%", "0.25", "taxable", "2017-07-01", None),
    ("1.5%", "1.5", "taxable", "2017-07-01", None),
    ("3%", "3", "taxable", "2017-07-01", None),
    ("5%", "5", "taxable", "2017-07-01", None),
    ("18%", "18", "taxable", "2017-07-01", None),
    ("40%", "40", "taxable", "2025-09-22", None),
    ("12% (legacy)", "12", "taxable", "2017-07-01", "2025-09-21"),
    ("28% (legacy)", "28", "taxable", "2017-07-01", "2026-01-31"),
]


def upgrade() -> None:
    x = op.execute
    x("""
    CREATE FUNCTION touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN NEW.updated_at = now(); RETURN NEW; END $$;
    """)

    # --- reference data (readable by everyone, written only by migrations/admin) ---
    x("CREATE TABLE gst_states (code text PRIMARY KEY, name text NOT NULL, is_ut boolean NOT NULL)")
    x(
        "INSERT INTO gst_states VALUES "
        + ", ".join(
            f"('{c}', '{n.replace(chr(39), chr(39) * 2)}', {str(c in UTGST_STATES).lower()})"
            for c, n in STATES.items()
        )
    )
    x("""
    CREATE TABLE gst_rates (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      label text NOT NULL,
      rate numeric(5,2) NOT NULL CHECK (rate >= 0),
      kind text NOT NULL CHECK (kind IN ('taxable','nil','exempt','non_gst')),
      effective_from date NOT NULL,
      effective_to date,
      is_active boolean GENERATED ALWAYS AS (effective_to IS NULL) STORED
    )""")
    x(
        "INSERT INTO gst_rates (label, rate, kind, effective_from, effective_to) VALUES "
        + ", ".join(
            f"('{lbl}', {r}, '{k}', '{f}', {repr(t) if t else 'NULL'})" for lbl, r, k, f, t in RATES
        )
    )
    x(
        "CREATE TABLE units (code text PRIMARY KEY, label text NOT NULL, allows_decimal boolean NOT NULL)"
    )
    x(
        "INSERT INTO units VALUES "
        + ", ".join(f"('{c}', '{lbl}', {str(d).lower()})" for c, lbl, d in UNITS)
    )
    x("GRANT SELECT ON gst_states, gst_rates, units TO anylo_app")

    # --- shops ---
    x("""
    CREATE TABLE shops (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      name text NOT NULL CHECK (length(trim(name)) > 0),
      business_type text NOT NULL DEFAULT 'general' CHECK (business_type IN
        ('general','grocery','apparel','electronics','hardware','pharmacy','stationery','nursery','other')),
      phone text, email citext,
      address_line1 text, address_line2 text, city text, pincode text CHECK (pincode ~ '^[1-9][0-9]{5}$'),
      state_code text NOT NULL REFERENCES gst_states(code),
      timezone text NOT NULL DEFAULT 'Asia/Kolkata',
      logo_path text,
      upi_vpa text, upi_payee_name text,
      settings jsonb NOT NULL DEFAULT '{}'::jsonb,
      is_active boolean NOT NULL DEFAULT true,
      onboarding_completed_at timestamptz,
      deleted_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    x(
        "CREATE TRIGGER shops_touch BEFORE UPDATE ON shops FOR EACH ROW EXECUTE FUNCTION touch_updated_at()"
    )

    x("""
    CREATE TABLE shop_tax_profiles (
      shop_id uuid PRIMARY KEY REFERENCES shops(id) ON DELETE CASCADE,
      gst_scheme text NOT NULL DEFAULT 'unregistered' CHECK (gst_scheme IN ('regular','composition','unregistered')),
      gstin text CHECK (gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'),
      legal_name text, trade_name text,
      composition_rate numeric(5,2),
      prices_include_tax boolean NOT NULL DEFAULT true,
      hsn_digits_required smallint NOT NULL DEFAULT 4 CHECK (hsn_digits_required IN (4, 6)),
      invoice_round_off boolean NOT NULL DEFAULT true,
      einvoice_applicable boolean NOT NULL DEFAULT false,
      filing_frequency text NOT NULL DEFAULT 'monthly' CHECK (filing_frequency IN ('monthly','qrmp')),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CHECK (gst_scheme = 'unregistered' OR gstin IS NOT NULL)
    )""")
    x(
        "CREATE UNIQUE INDEX shop_tax_profiles_gstin ON shop_tax_profiles (gstin) WHERE gstin IS NOT NULL"
    )
    x(
        "CREATE TRIGGER shop_tax_touch BEFORE UPDATE ON shop_tax_profiles FOR EACH ROW EXECUTE FUNCTION touch_updated_at()"
    )

    # --- users ---
    x("""
    CREATE TABLE users (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      email citext NOT NULL UNIQUE,
      phone text CHECK (phone ~ '^[6-9][0-9]{9}$'),
      full_name text NOT NULL,
      password_hash text NOT NULL,
      pin_hash text,
      role text NOT NULL CHECK (role IN ('admin','support','owner','manager','salesperson')),
      shop_id uuid REFERENCES shops(id) ON DELETE CASCADE,
      is_active boolean NOT NULL DEFAULT true,
      must_change_password boolean NOT NULL DEFAULT false,
      token_version integer NOT NULL DEFAULT 0,
      preferred_language text NOT NULL DEFAULT 'en' CHECK (preferred_language IN ('en','hi','ml','ta','kn')),
      last_login_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CHECK ((role IN ('manager','salesperson')) = (shop_id IS NOT NULL))
    )""")
    x("CREATE UNIQUE INDEX users_phone ON users (phone) WHERE phone IS NOT NULL")
    x("CREATE INDEX users_shop ON users (shop_id)")
    x(
        "CREATE TRIGGER users_touch BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION touch_updated_at()"
    )

    x("""
    CREATE TABLE shop_owners (
      shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
      owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (shop_id, owner_id)
    )""")
    x("CREATE INDEX shop_owners_owner ON shop_owners (owner_id)")

    x("""
    CREATE TABLE auth_sessions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      family_id uuid NOT NULL,
      refresh_hash text NOT NULL UNIQUE,
      device_label text, platform text CHECK (platform IN ('web','android','ios')),
      created_at timestamptz NOT NULL DEFAULT now(),
      last_used_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL,
      revoked_at timestamptz
    )""")
    x("CREATE INDEX auth_sessions_user ON auth_sessions (user_id)")
    x("CREATE INDEX auth_sessions_family ON auth_sessions (family_id)")

    # --- row-level security ---
    platform = f"{ROLE} IN ('admin','system','support')"
    for sql in enable_rls("shops", tenant_predicate("id")):
        x(sql)
    for sql in enable_rls("shop_tax_profiles", tenant_predicate()):
        x(sql)
    for sql in enable_rls(
        "users",
        f"{ROLE} IN ('admin','system') OR id = {USER} OR shop_id = {SHOP}"
        f" OR ({ROLE} = 'owner' AND shop_id IN ({owner_shops()}))"
        f" OR ({ROLE} = 'support' AND role <> 'admin')",
    ):
        x(sql)
    for sql in enable_rls(
        "shop_owners",
        f"{platform} OR owner_id = {USER} OR shop_id = {SHOP}",
        write_predicate=platform,
    ):
        x(sql)
    for sql in enable_rls("auth_sessions", f"{ROLE} IN ('admin','system') OR user_id = {USER}"):
        x(sql)


def downgrade() -> None:
    for t in (
        "auth_sessions",
        "shop_owners",
        "users",
        "shop_tax_profiles",
        "shops",
        "units",
        "gst_rates",
        "gst_states",
    ):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS touch_updated_at()")

"""SQL builders for row-level security, used by every migration (docs/02-architecture.md §4)."""

ROLE = "current_setting('app.role', true)"
SHOP = "NULLIF(current_setting('app.shop_id', true), '')::uuid"
USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"


def owner_shops() -> str:
    return f"SELECT so.shop_id FROM shop_owners so WHERE so.owner_id = {USER}"


def tenant_predicate(column: str = "shop_id", *, pii: bool = False) -> str:
    """Platform roles, the active shop, or any shop the owner is linked to. PII tables exclude support."""
    platform = "'admin','system'" if pii else "'admin','system','support'"
    return (
        f"{ROLE} IN ({platform}) OR {column} = {SHOP} "
        f"OR ({ROLE} = 'owner' AND {column} IN ({owner_shops()}))"
    )


def enable_rls(table: str, predicate: str, *, write_predicate: str | None = None) -> list[str]:
    w = write_predicate or predicate
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {table}_isolation ON {table} USING ({predicate}) WITH CHECK ({w})",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO anylo_app",
    ]

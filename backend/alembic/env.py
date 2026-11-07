import os

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings

# Migrations run as the schema owner; ALEMBIC_URL lets tests target anylo_test.
url = os.environ.get("ALEMBIC_URL") or get_settings().database_url_owner


def run() -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    run()

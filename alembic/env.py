"""Alembic environment — async-compatible, reads URL from app.config.settings.

Usage
-----
New installation (tables don't exist yet):
    alembic upgrade head

Existing installation (tables created by init_db):
    alembic stamp head      # marks DB as already at baseline — skips DDL
    # future migrations run normally from here

Offline SQL script generation:
    alembic upgrade head --sql > migration.sql
"""
from __future__ import annotations

import asyncio
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

# ── App imports ────────────────────────────────────────────────────────────────
# Import models so they are registered with Base.metadata before autogenerate
# or create_all comparisons are made.
import app.models  # noqa: F401  — side-effect import registers all ORM models
from app.config import settings
from app.database import Base

# ── Alembic config ─────────────────────────────────────────────────────────────
config = context.config
# Override the placeholder URL with the live app URL at runtime.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

target_metadata = Base.metadata


# ── Offline mode (SQL script generation) ──────────────────────────────────────

def run_migrations_offline() -> None:
    """Generate a SQL script without connecting to the database.

    The asyncpg driver prefix is stripped so SQLAlchemy uses the standard
    psycopg2 dialect for DDL rendering — the output is still valid Postgres SQL.
    """
    url = settings.DATABASE_URL.replace("+asyncpg", "")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (direct database connection) ──────────────────────────────────

def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,   # each migration run gets a fresh connection
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

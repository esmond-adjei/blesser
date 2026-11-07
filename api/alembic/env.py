"""Alembic environment: async engine, metadata from feature models."""

import asyncio

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

import api.models as _models  # noqa: F401 - register every table on Base.metadata
from alembic import context
from api.core.config import settings
from api.core.db import Base

config = context.config

url = config.get_main_option("sqlalchemy.url")
if not url or url.startswith("driver://"):
    url = settings.database_url
    config.set_main_option("sqlalchemy.url", url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

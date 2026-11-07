"""Scratch databases on the suite's Postgres server (override with TEST_DATABASE_URL)."""

import asyncio
import contextlib
import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import asyncpg
from alembic.config import Config

from alembic import command

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://blesser:blesser@localhost:5432/blesser_test",
)


def _dsn(db_url: str) -> str:
    """Plain asyncpg DSN (SQLAlchemy's +asyncpg driver prefix is its own)."""
    parts = urlsplit(db_url)
    return urlunsplit(("postgresql", parts.netloc, parts.path, "", ""))


def _run(coro):
    return asyncio.run(coro)


async def _admin_execute(sql: str) -> None:
    parts = urlsplit(TEST_DATABASE_URL)
    admin = urlunsplit(("postgresql", parts.netloc, "/postgres", "", ""))
    conn = await asyncpg.connect(admin)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@contextlib.contextmanager
def _scratch_db():
    name = f"blesser_mig_{uuid.uuid4().hex[:8]}"
    _run(_admin_execute(f'CREATE DATABASE "{name}"'))
    try:
        parts = urlsplit(TEST_DATABASE_URL)
        yield urlunsplit((parts.scheme, parts.netloc, f"/{name}", "", ""))
    finally:
        _run(_admin_execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def _cfg(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


async def _fetch(url: str, sql: str):
    conn = await asyncpg.connect(_dsn(url))
    try:
        return await conn.fetch(sql)
    finally:
        await conn.close()


def _tables(url: str) -> list[str]:
    rows = _run(_fetch(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    return sorted(r["tablename"] for r in rows)


EXPECTED_TABLES = [
    "alembic_version",
    "applications",
    "auth_email_tokens",
    "auth_refresh_tokens",
    "calendar_feeds",
    "notification_preferences",
    "notifications",
    "opportunities",
    "push_subscriptions",
    "scan_tasks",
    "scans",
    "todos",
    "user_identities",
    "users",
    "worker_heartbeats",
]


def test_fresh_upgrade_builds_full_schema():
    with _scratch_db() as url:
        command.upgrade(_cfg(url), "head")
        assert _tables(url) == EXPECTED_TABLES


def test_models_and_migrations_agree():
    """A model change without a migration fails here (same check as `alembic check`)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy.ext.asyncio import create_async_engine

    import api.models  # noqa: F401
    from api.core.db import Base

    async def diff(url: str):
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(
                    lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
                )
        finally:
            await engine.dispose()

    with _scratch_db() as url:
        command.upgrade(_cfg(url), "head")
        assert _run(diff(url)) == []


def test_downgrade_upgrade_cycle():
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        assert _tables(url) == ["alembic_version"]
        command.upgrade(cfg, "head")
        assert _tables(url) == EXPECTED_TABLES

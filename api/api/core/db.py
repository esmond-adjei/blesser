import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from api.core.config import settings


class Base(DeclarativeBase):
    pass


if not settings.database_url.startswith("postgresql"):
    raise RuntimeError(
        "DATABASE_URL must be a Postgres URL (postgresql+asyncpg://...). "
        "SQLite is not supported."
    )

# DB_NULL_POOL=1: no pooling. Tests use many event loops and pooled asyncpg
# connections are bound to the loop that opened them.
_use_null_pool = os.environ.get("DB_NULL_POOL", "").lower() in ("1", "true")
engine_kwargs: dict = {"echo": False}
if _use_null_pool:
    engine_kwargs["poolclass"] = NullPool
else:
    engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )
engine = create_async_engine(settings.database_url, **engine_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def listener_dsn() -> str:
    """Plain asyncpg DSN for a LISTEN connection, which the SSE feed holds outside the pool."""
    parts = urlsplit(settings.database_url)
    return urlunsplit(("postgresql", parts.netloc, parts.path, "", ""))


def like_pattern(text: str) -> str:
    """Substring LIKE pattern with the wildcards escaped."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _upgrade_head() -> None:
    from alembic.config import Config

    from alembic import command

    root = Path(__file__).resolve().parent.parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


async def init_db() -> None:
    # Apply migrations on boot so deploys never run against a stale schema.
    try:
        await asyncio.to_thread(_upgrade_head)
    except Exception as exc:
        raise RuntimeError(
            "Postgres migration failed. Databases created before Alembic "
            "need their baseline stamped first: alembic stamp 001 "
            "(see README migrations section)."
        ) from exc


async def get_session():
    async with SessionLocal() as session:
        yield session

"""Use a scratch Postgres database; this must run before any `import api.*`, which builds the engine at import time."""

import asyncio
import os
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

import pytest

TEST_USER_ID = "test-user-0000"
TEST_USER_EMAIL = "test@example.com"

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://blesser:blesser@localhost:5432/blesser_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# No pooling: asyncpg connections stay bound to the event loop that opened them.
os.environ["DB_NULL_POOL"] = "1"
# Never send real mail from tests, whatever .env says.
os.environ["MAIL_BACKEND"] = "console"


def _admin_dsn(db_url: str) -> str:
    """asyncpg DSN for the server's maintenance database (same credentials)."""
    parts = urlsplit(db_url)
    return urlunsplit(("postgresql", parts.netloc, "/postgres", "", ""))


async def _recreate_test_db() -> None:
    import asyncpg

    name = urlsplit(TEST_DATABASE_URL).path.lstrip("/")
    conn = await asyncpg.connect(_admin_dsn(TEST_DATABASE_URL))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """Recreate and migrate the scratch database once per session."""
    asyncio.run(_recreate_test_db())
    from api.core.db import init_db

    asyncio.run(init_db())


@pytest.fixture(autouse=True)
def _authenticated_test_user(request):
    """Run every test as one fixed account; `real_auth` tests opt out."""
    if request.node.get_closest_marker("real_auth") is not None:
        yield
        return

    from api.auth import models as auth_models
    from api.auth import schemas as auth_schemas
    from api.auth.routes import get_current_user
    from api.core.db import SessionLocal
    from api.main import app

    async def _ensure_user():
        async with SessionLocal() as session:
            user = await session.get(auth_models.User, TEST_USER_ID)
            if user is None:
                session.add(
                    auth_models.User(
                        id=TEST_USER_ID,
                        email=TEST_USER_EMAIL,
                        password_hash="not-a-real-hash",
                        email_verified_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                )
            else:
                user.email_verified_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()

    asyncio.run(_ensure_user())
    app.dependency_overrides[get_current_user] = lambda: auth_schemas.UserOut(
        id=TEST_USER_ID, email=TEST_USER_EMAIL, created_at=datetime.now(UTC)
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def _robots_off(request, monkeypatch):
    """robots.txt checks add a request per origin that mocked transports don't expect."""
    from api import web

    if request.node.get_closest_marker("robots") is None:
        from api.core.config import settings

        monkeypatch.setattr(settings, "respect_robots_txt", False)
    web._ROBOTS.clear()


@pytest.fixture(autouse=True)
def _cold_caches_and_clients():
    """Process-wide caches and HTTP clients would leak between tests (and event loops)."""
    from api import web
    from api.core.ttlcache import clear_all

    clear_all()
    web._CACHE.clear()
    web._search_client = web._fetch_client = None
    web._SEARCH_SEM = web._FETCH_SEM = None
    yield
    web._search_client = web._fetch_client = None


@pytest.fixture(autouse=True)
def _rate_limits(request, monkeypatch):
    """Per-account throttles are off for the suite; `rate_limits` tests turn them on."""
    from api.core.config import settings
    from api.core.ratelimit import limiter

    limiter.reset()
    enabled = request.node.get_closest_marker("rate_limits") is not None
    monkeypatch.setattr(settings, "rate_limits_enabled", enabled)
    yield
    limiter.reset()

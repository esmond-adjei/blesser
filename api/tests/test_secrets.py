import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import delete, text

from api.core import secrets
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.todos.models import CalendarFeed
from tests.conftest import TEST_USER_ID


def _reset_feed():
    async def go():
        async with SessionLocal() as session:
            await session.execute(delete(CalendarFeed).where(CalendarFeed.user_id == TEST_USER_ID))
            await session.commit()

    asyncio.run(go())


def _raw_token() -> str:
    async def go():
        async with SessionLocal() as session:
            return (
                await session.execute(
                    text("SELECT token FROM calendar_feeds WHERE user_id = :u"), {"u": TEST_USER_ID}
                )
            ).scalar_one()

    return asyncio.run(go())


def test_feed_token_is_ciphertext_in_the_db_and_plaintext_to_the_app(monkeypatch):
    monkeypatch.setattr(settings, "auth_secret", "test-auth-secret")
    _reset_feed()
    url = TestClient(app).get("/api/calendar/feed").json()["url"]
    token = url.rsplit("/", 1)[1].removesuffix(".ics")
    raw = _raw_token()
    assert raw.startswith("enc:v1:") and token not in raw
    assert TestClient(app).get("/api/calendar/feed").json()["url"] == url
    _reset_feed()


def test_round_trip_and_legacy_plaintext(monkeypatch):
    monkeypatch.setattr(settings, "auth_secret", "test-auth-secret")
    sealed = secrets.encrypt("value")
    assert sealed.startswith(secrets.PREFIX)
    assert secrets.decrypt(sealed) == "value"
    assert secrets.decrypt("plain") == "plain"


def test_without_any_key_values_stay_plaintext(monkeypatch):
    monkeypatch.setattr(settings, "auth_secret", "")
    monkeypatch.setattr(settings, "secrets_key", "")
    assert secrets.encrypt("value") == "value"

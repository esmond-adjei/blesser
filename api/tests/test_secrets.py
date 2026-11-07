import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import text

from api.core import secrets
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.providers import service as providers_service
from tests.conftest import TEST_USER_ID


def _raw_key(provider: str) -> str:
    async def go():
        async with SessionLocal() as session:
            return (
                await session.execute(
                    text(
                        "SELECT api_key FROM provider_configs WHERE user_id = :u AND provider = :p"
                    ),
                    {"u": TEST_USER_ID, "p": provider},
                )
            ).scalar_one()

    return asyncio.run(go())


def test_keys_are_ciphertext_in_the_db_and_plaintext_to_the_app(monkeypatch):
    monkeypatch.setattr(settings, "auth_secret", "test-auth-secret")
    with TestClient(app) as client:
        r = client.patch(
            "/api/providers/openai", json={"model": "gpt-x", "api_key": "test-key-placeholder"}
        )
        assert r.status_code == 200, r.text
        assert "test-key-placeholder" not in r.text
    raw = _raw_key("openai")
    assert raw.startswith("enc:v1:") and "test-key-placeholder" not in raw

    async def resolved():
        async with SessionLocal() as session:
            return await providers_service.resolve_llm_kwargs(
                session, TEST_USER_ID, "openai"
            )

    assert asyncio.run(resolved())["api_key"] == "test-key-placeholder"


def test_legacy_plaintext_reads_and_the_script_encrypts_it(monkeypatch):
    monkeypatch.setattr(settings, "auth_secret", "test-auth-secret")
    with TestClient(app) as client:
        client.patch(
            "/api/providers/gemini", json={"model": "g", "api_key": "placeholder"}
        )

    async def plant():
        async with SessionLocal() as session:
            await session.execute(
                text(
                    "UPDATE provider_configs SET api_key = 'legacy-key' WHERE user_id = :u AND provider = 'gemini'"
                ),
                {"u": TEST_USER_ID},
            )
            await session.commit()
            return await providers_service.resolve_llm_kwargs(
                session, TEST_USER_ID, "gemini"
            )

    assert asyncio.run(plant())["api_key"] == "legacy-key"
    from scripts import encrypt_secrets

    asyncio.run(encrypt_secrets.main())
    assert _raw_key("gemini").startswith("enc:v1:")
    asyncio.run(encrypt_secrets.main())  # idempotent


def test_without_any_key_values_stay_plaintext(monkeypatch):
    monkeypatch.setattr(settings, "auth_secret", "")
    monkeypatch.setattr(settings, "secrets_key", "")
    assert secrets.encrypt("abc") == "abc"

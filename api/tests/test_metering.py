import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.agent.llm.base import LLMResponse
from api.auth import models as auth_models
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.metering import service as metering
from api.metering.models import UsageDaily
from tests.conftest import TEST_USER_ID


def _wipe():
    async def go():
        async with SessionLocal() as session:
            await session.execute(delete(UsageDaily))
            await session.commit()

    asyncio.run(go())


class _Provider:
    name = "anthropic"
    model = "claude-test"

    async def chat_stream(self, messages, system, tools, max_tokens=4096):
        yield {"type": "token", "text": "Hi."}
        yield {
            "type": "done",
            "response": LLMResponse(
                text="Hi.",
                tool_calls=[],
                usage={"input_tokens": 120, "output_tokens": 30},
            ),
        }


def test_chat_turns_are_metered_and_aggregate_into_one_row(monkeypatch):
    _wipe()
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda **_: _Provider())
    with TestClient(app) as client:
        conv = client.post("/api/assistant/conversations").json()["id"]
        for _ in range(2):
            client.post(
                f"/api/assistant/conversations/{conv}/chat", json={"content": "hello"}
            )
        usage = client.get("/api/usage", params={"days": 7}).json()
    assert usage["totals"] == {"calls": 2, "input_tokens": 240, "output_tokens": 60}
    assert usage["by_feature"] == [
        {
            "feature": "chat",
            "provider": "anthropic",
            "model": "claude-test",
            "calls": 2,
            "input_tokens": 240,
            "output_tokens": 60,
        }
    ]
    assert len(usage["days"]) == 7 and usage["days"][-1]["calls"] == 2
    assert [(r["feature"], r["calls"], r["tokens"]) for r in usage["by_day_feature"]] == [("chat", 2, 300)]
    assert usage["previous"] == {"calls": 0, "input_tokens": 0, "output_tokens": 0}


def _set_verified(verified: bool) -> None:
    async def go():
        async with SessionLocal() as session:
            user = await session.get(auth_models.User, TEST_USER_ID)
            assert user is not None
            user.email_verified_at = (
                datetime.now(UTC).replace(tzinfo=None) if verified else None
            )
            await session.commit()

    asyncio.run(go())


def test_ops_view_is_admin_only(monkeypatch):
    _wipe()
    asyncio.run(metering.record(TEST_USER_ID, "research", "openai", "gpt-x", 10, 5))
    _set_verified(True)
    try:
        with TestClient(app) as client:
            assert client.get("/api/ops/usage").status_code == 403
            monkeypatch.setattr(
                settings, "ops_admin_emails", "someone@x.com, Test@Example.com"
            )
            body = client.get("/api/ops/usage").json()
    finally:
        _set_verified(False)
    assert body["totals"]["calls"] == 1
    assert body["top_accounts"][0] == {
        "email": "test@example.com",
        "calls": 1,
        "tokens": 15,
    }


def test_unverified_admin_address_is_refused(monkeypatch):
    _set_verified(False)
    monkeypatch.setattr(settings, "ops_admin_emails", "TEST@example.com")
    with TestClient(app) as client:
        assert client.get("/api/ops/usage").status_code == 403


def test_retention_prunes_old_rollups(monkeypatch):
    _wipe()

    async def go():
        today = metering._today()
        async with SessionLocal() as session:
            for age in (0, 500):
                session.add(
                    UsageDaily(
                        user_id=TEST_USER_ID,
                        day=today - timedelta(days=age),
                        feature="chat",
                        provider="p",
                        model="m",
                        calls=1,
                        input_tokens=0,
                        output_tokens=0,
                    )
                )
            await session.commit()
        return await metering.prune(400)

    assert asyncio.run(go()) == 1


def test_metering_failure_never_breaks_the_call(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(metering, "SessionLocal", boom)
    asyncio.run(metering.record(TEST_USER_ID, "chat", "p", "m"))  # must not raise

import asyncio
from datetime import UTC, datetime

import anyio
from sqlalchemy import select, text

from api.agent.llm.base import LLMResponse
from api.core.db import SessionLocal
from api.metering.models import UsageDaily
from api.metering.service import RESERVED_FEATURE
from tests.conftest import TEST_USER_ID
from tests.test_assistant import _client


async def _open_transactions() -> int:
    """Other sessions on this database sitting idle in a transaction."""
    async with SessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND state LIKE 'idle in transaction%' "
                    "AND pid <> pg_backend_pid()"
                )
            )
        ).scalar_one()


class ProbeProvider:
    """Streams a few tokens, noting the database's state meanwhile."""

    def __init__(self):
        self.open_during_stream: list[int] = []

    async def chat_stream(self, messages, system, tools, max_tokens=4096):
        for chunk in ["one ", "two ", "three"]:
            self.open_during_stream.append(await _open_transactions())
            await asyncio.sleep(0)
            yield {"type": "token", "text": chunk}
        yield {"type": "done", "response": LLMResponse(text="one two three", tool_calls=[])}


def _conversation() -> str:
    with _client() as client:
        return client.post("/api/assistant/conversations").json()["id"]


async def _reserved_today() -> int:
    async with SessionLocal() as session:
        value = (
            await session.execute(
                select(UsageDaily.input_tokens).where(
                    UsageDaily.user_id == TEST_USER_ID,
                    UsageDaily.feature == RESERVED_FEATURE,
                    UsageDaily.day == datetime.now(UTC).date(),
                )
            )
        ).scalar_one_or_none()
        return value or 0


def test_no_transaction_is_open_while_the_model_streams(monkeypatch):
    import api.assistant.service as gradis

    provider = ProbeProvider()
    monkeypatch.setattr(gradis, "get_provider", lambda **_: provider)
    conv_id = _conversation()

    async def go():
        return [
            e["event"]
            async for e in gradis.begin_streaming_turn(TEST_USER_ID, conv_id, "hello")
        ]

    kinds = asyncio.run(go())
    assert kinds[-1] == "done"
    assert provider.open_during_stream == [0, 0, 0]


def test_hanging_up_mid_reply_releases_everything(monkeypatch):
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda **_: ProbeProvider())
    conv_id = _conversation()

    async def go():
        before = await _reserved_today()
        # What Starlette does when the client goes: cancel the request's
        # scope, which cancels every await in it, cleanup included.
        with anyio.CancelScope() as scope:
            async for event in gradis.begin_streaming_turn(TEST_USER_ID, conv_id, "hello"):
                if event["event"] == "token":
                    scope.cancel()
        return before, await _reserved_today(), await _open_transactions()

    before, after, open_transactions = asyncio.run(go())
    assert after == before
    assert open_transactions == 0
    assert not gradis.turn_running(conv_id)

import asyncio
from datetime import date

import pytest

from api.assistant import live, tools
from api.assistant.sources import SourceRegistry


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    yield


@pytest.fixture(autouse=True)
def _authenticated_test_user():
    yield


def test_deadline_markers_resolve_only_against_current_tool_data():
    registry = SourceRegistry()
    key = registry.register(
        "application",
        {"id": "app-1", "title": "Seed Fund", "deadline_date": date(2040, 9, 8)},
    )
    assert (
        registry.register(
            "application",
            {"id": "app-1", "title": "Seed Fund", "deadline_date": date(2040, 9, 8)},
        )
        == key
    )
    reply, sources, deadlines = registry.render(
        f"Seed Fund closes on [deadline:{key}].\nIt also closes in three weeks.\nUnknown: [deadline:s2] [s400]."
    )
    assert reply == "Seed Fund closes on 8 Sep 2040.\nUnknown: No deadline confirmed."
    assert [row["id"] for row in sources] == ["app-1"]
    assert deadlines


def test_stored_trace_without_kind_still_parses_as_tool_steps():
    from api.assistant.schemas import MessageOut
    from api.core.time import utcnow_naive

    message = MessageOut(
        id="message-id",
        role="assistant",
        content="A reply",
        trace=[
            {
                "tool": "search_catalog",
                "label": "Searched the Blesser catalog",
                "ok": True,
                "note": "I'll look.",
            }
        ],
        sources=[],
        cited_deadlines=False,
        created_at=utcnow_naive(),
    )
    assert message.trace[0].kind == "tool"
    assert message.model_dump(mode="json")["trace"][0]["kind"] == "tool"


def test_tools_only_offer_web_after_catalog_and_writes_after_enable():
    def offered(**flags):
        return {d["name"] for d in tools.definitions(**flags)}

    initial = offered(catalog_checked=False, changes_enabled=False, web_allowed=True)
    assert "search_catalog" in initial
    assert "search_web" not in initial
    assert not tools.WRITES & initial
    later = offered(catalog_checked=True, changes_enabled=True, web_allowed=True)
    assert "search_web" in later
    assert tools.WRITES <= later
    private = offered(catalog_checked=True, changes_enabled=False, web_allowed=False)
    assert "search_web" not in private


async def _test_live_turn_survives_a_disconnect_and_replays_to_its_owner():
    release = asyncio.Event()

    async def events():
        yield {"event": "status", "message": "Checking"}
        await release.wait()
        yield {"event": "done"}

    turn = live.start("turn-1", "owner", events())
    reader = turn.follow()
    assert (await anext(reader))["event"] == "status"
    await reader.aclose()
    assert live.get("turn-1", "out-of-scope") is None
    assert live.get("turn-1", "owner") is turn
    release.set()
    assert [e["event"] async for e in turn.follow()] == ["status", "done"]
    assert live.get("turn-1", "owner") is None


async def _test_stop_emits_a_terminal_event_and_does_cleanup():
    closed = asyncio.Event()

    async def events():
        try:
            yield {"event": "status", "message": "Checking"}
            await asyncio.Event().wait()
        finally:
            closed.set()

    turn = live.start("turn-2", "owner", events())
    reader = turn.follow()
    assert (await anext(reader))["event"] == "status"
    assert not await live.stop("turn-2", "out-of-scope")
    assert await live.stop("turn-2", "owner")
    assert [e["event"] async for e in reader] == ["stopped"]
    assert closed.is_set()


async def _test_streamed_turn_replays_tool_calls_and_publishes_grounded_answer(
    monkeypatch,
):
    from api.agent.llm.base import LLMResponse, ToolCall
    from api.assistant import service
    from api.assistant.schemas import MessageOut
    from api.core.time import utcnow_naive

    def message(role, content, trace=(), sources=(), cited_deadlines=False):
        return MessageOut(
            id=role,
            role=role,
            content=content,
            trace=list(trace),
            sources=list(sources),
            cited_deadlines=cited_deadlines,
            created_at=utcnow_naive(),
        )

    async def begin(chat_id, user_id, lease, content):
        return message("user", content), [], False

    async def read(user_id, name, args, registry):
        assert (user_id, name, args.query) == (
            "member-id",
            "search_catalog",
            "seed fund",
        )
        key = registry.register(
            "application",
            {"id": "record", "title": "Seed Fund", "deadline_date": date(2040, 9, 8)},
        )
        return {"source": key, "deadline": "8 Sep 2040"}, 1

    async def save(chat_id, user_id, lease, content, trace, sources, cited_deadlines):
        return message("assistant", content, trace, sources, cited_deadlines)

    async def release(chat_id, lease):
        assert (chat_id, lease) == ("chat-id", "lease-id")

    class Provider:
        async def chat(self, *, messages, **kwargs):
            if messages[-1]["role"] == "user":
                return LLMResponse(
                    text="I'll check the catalog.",
                    reasoning="I should look in the catalog before answering.",
                    tool_calls=[
                        ToolCall("lookup", "search_catalog", {"query": "seed fund"})
                    ],
                )
            assert (
                messages[-2]["tool_calls"][0]["id"]
                == messages[-1]["tool_call_id"]
                == "lookup"
            )
            return LLMResponse(
                text="Seed Fund closes on [deadline:s1].\nAnother deadline is tomorrow."
            )

    monkeypatch.setattr(service, "_begin", begin)
    monkeypatch.setattr(service, "_read", read)
    monkeypatch.setattr(service, "_save_reply", save)
    monkeypatch.setattr(service.conversations, "release", release)
    monkeypatch.setattr(service, "get_provider", Provider)

    events = [
        e
        async for e in service.chat_turn(
            "chat-id", "member-id", "lease-id", "When does Seed Fund close?"
        )
    ]
    assert [e["event"] for e in events] == [
        "user_message",
        "status",
        "reasoning",
        "commentary",
        "tool_start",
        "tool_result",
        "status",
        "token",
        "message",
        "done",
    ]
    assert events[2] == {
        "event": "reasoning",
        "text": "I should look in the catalog before answering.",
    }
    assert events[3] == {
        "event": "commentary",
        "text": "I'll check the catalog.",
    }
    assert events[-3]["text"] == "Seed Fund closes on 8 Sep 2040."
    reply = events[-2]["message"]
    assert reply["trace"][0] == {
        "kind": "thought",
        "text": "I should look in the catalog before answering.",
    }
    assert reply["trace"][1] == {
        "kind": "commentary",
        "text": "I'll check the catalog.",
    }
    assert reply["trace"][2]["kind"] == "tool"
    assert reply["trace"][2]["label"] == "Searched the Blesser catalog, 1 match"
    assert reply["sources"][0]["id"] == "record"
    assert reply["cited_deadlines"]


def test_live_turn_survives_a_disconnect_and_replays_to_its_owner():
    asyncio.run(_test_live_turn_survives_a_disconnect_and_replays_to_its_owner())


def test_stop_emits_a_terminal_event_and_does_cleanup():
    asyncio.run(_test_stop_emits_a_terminal_event_and_does_cleanup())


def test_streamed_turn_replays_tool_calls_and_publishes_grounded_answer(monkeypatch):
    asyncio.run(_test_streamed_turn_replays_tool_calls_and_publishes_grounded_answer(monkeypatch))

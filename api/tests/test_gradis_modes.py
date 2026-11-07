import asyncio

import pytest
from sqlalchemy import delete

from api.agent.llm.base import LLMResponse, ToolCall
from api.agents import models as agents_models
from api.assistant import modes as gradis_modes
from api.assistant import tools as assistant_tools
from api.core.db import SessionLocal
from tests.test_assistant import ScriptProvider, _client, _transcript, _turn


@pytest.fixture(autouse=True)
def _clean_registry():
    """Tool switches live in the shared DB: start and end with defaults."""

    async def _wipe():
        async with SessionLocal() as session:
            await session.execute(delete(agents_models.AgentTool))
            await session.commit()

    asyncio.run(_wipe())
    yield
    asyncio.run(_wipe())


class OfferedProvider:
    """Answers at once, recording the tool names each call was offered and the system prompt."""

    def __init__(self):
        self.offered: list[list[str]] = []
        self.systems: list[str] = []

    async def chat_stream(self, messages, system, tools, max_tokens=4096):
        self.offered.append([t["name"] for t in tools])
        self.systems.append(system)
        yield {"type": "token", "text": "ok"}
        yield {"type": "done", "response": LLMResponse(text="ok", tool_calls=[])}


def _offered(monkeypatch, mode: str | None) -> OfferedProvider:
    import api.assistant.service as gradis

    provider = OfferedProvider()
    monkeypatch.setattr(gradis, "get_provider", lambda: provider)
    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        _turn(client, conv_id, "hello there", **({"mode": mode} if mode else {}))
    return provider


ALL_TOOLS = {d["name"] for d in assistant_tools.ASSISTANT_DEFINITIONS}
#: Legacy CV tools only join a chat that already called them.
FRESH = ALL_TOOLS - assistant_tools.LEGACY_TOOLS


def test_read_bundle_is_derived_from_the_write_list():
    reads = gradis_modes.READ_TOOLS
    assert "list_runs" in reads and "search_web" in reads and "cv_read" in reads
    assert not reads & assistant_tools.WRITE_TOOLS
    assert "cv_suggest_changes" not in reads and "suggest_changes" not in reads
    assert reads | assistant_tools.WRITE_TOOLS | gradis_modes.SUGGEST_TOOLS == ALL_TOOLS


def test_only_chat_and_agent_modes_exist():
    assert set(gradis_modes.MODES) == {"chat", "agent"}


def test_chat_mode_offers_exactly_the_reads(monkeypatch):
    provider = _offered(monkeypatch, "chat")
    assert set(provider.offered[0]) == set(gradis_modes.READ_TOOLS) & FRESH
    assert "Mode: Chat" in provider.systems[0]
    assert "Agent mode can make it" in provider.systems[0]
    assert "cv_suggest_changes" not in provider.offered[0]
    assert "suggest_changes" not in provider.offered[0]
    assert assistant_tools.ENABLE_CHANGES not in provider.offered[0]


def test_agent_mode_includes_suggestions_and_approval(monkeypatch):
    provider = _offered(monkeypatch, "agent")
    assert "suggest_changes" in provider.offered[0]
    assert "cv_suggest_changes" not in provider.offered[0]
    assert assistant_tools.ENABLE_CHANGES in provider.offered[0]


def test_default_is_agent_with_current_behaviour(monkeypatch):
    provider = _offered(monkeypatch, None)
    assert set(provider.offered[0]) == (FRESH - assistant_tools.WRITE_TOOLS) | {
        assistant_tools.ENABLE_CHANGES
    }
    assert "## Mode:" not in provider.systems[0]


def test_user_disabled_tool_stays_off_in_agent_and_chat(monkeypatch):
    with _client() as client:
        assert (
            client.patch("/api/agent/tools/assistant/list_tasks", json={"enabled": False}).status_code
            == 200
        )
    for mode in ("agent", "chat"):
        provider = _offered(monkeypatch, mode)
        assert "list_tasks" not in provider.offered[0]
        assert "list_runs" in provider.offered[0]


@pytest.mark.parametrize("tool, arguments", [
    ("save_program", {"run_id": "r", "school_name": "S", "program_name": "P"}),
    ("cv_suggest_changes", {"document_id": "cv1", "suggestions": []}),
])
def test_out_of_mode_call_is_refused_not_run(monkeypatch, tool, arguments):
    import api.assistant.service as gradis

    provider = ScriptProvider(
        [
            ([], [ToolCall(id="w1", name=tool, arguments=arguments)]),
            (["I can't save in this mode."], []),
        ]
    )
    monkeypatch.setattr(gradis, "get_provider", lambda: provider)
    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        events = _turn(client, conv_id, "save it", mode="chat")
        kinds = [k for k, _ in events]
        assert "confirm_required" not in kinds and "tool_start" not in kinds
        [result] = [p for k, p in events if k == "tool_result"]
        assert result["tool"] == tool and result["ok"] is False
        assert "Chat mode" in result["preview"]
        assert events[-1][0] == "done"
        user = [m for m in _transcript(client, conv_id) if m["role"] == "user"]
        assert user[0]["mode"] == "chat"


def test_default_mode_is_stored_on_the_user_message(monkeypatch):
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: ScriptProvider([(["hi"], [])]))
    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        _turn(client, conv_id, "hello")
        [user] = [m for m in _transcript(client, conv_id) if m["role"] == "user"]
    assert user["mode"] == "agent"


@pytest.mark.parametrize("mode", ["ask", "assist", "godmode"])
def test_invalid_mode_is_rejected(mode):
    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        resp = client.post(
            f"/api/assistant/conversations/{conv_id}/chat",
            json={"content": "hi", "mode": mode},
        )
        assert resp.status_code == 422
        resp = client.post(
            f"/api/assistant/conversations/{conv_id}/confirm",
            json={"call_id": "x", "approved": True, "mode": mode},
        )
        assert resp.status_code == 422

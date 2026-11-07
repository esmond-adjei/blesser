from fastapi.testclient import TestClient

from api.agent.llm.base import LLMResponse, ToolCall


def _client():
    from api.main import app

    return TestClient(app)


def _sse_events(text: str) -> list[tuple[str, dict]]:
    """Parse an SSE stream body into (event, payload) pairs."""
    import json

    out = []
    for frame in text.split("\n\n"):
        name, data = None, None
        for line in frame.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        if name and data:
            out.append((name, json.loads(data)))
    return out


class ScriptProvider:
    """Canned provider: each chat_stream call pops one (chunks, calls) step."""

    def __init__(self, steps):
        self.steps = list(steps)
        # Provider-format history per call, to assert what a replacement turn replayed.
        self.seen: list[list[dict]] = []

    async def chat(self, messages, system, tools, max_tokens=4096):
        chunks, calls = self.steps.pop(0)
        return LLMResponse(text="".join(chunks), tool_calls=list(calls))

    async def chat_stream(self, messages, system, tools, max_tokens=4096):
        self.seen.append([dict(m) for m in messages])
        chunks, calls = self.steps.pop(0)
        for chunk in chunks:
            yield {"type": "token", "text": chunk}
        yield {
            "type": "done",
            "response": LLMResponse(text="".join(chunks), tool_calls=list(calls)),
        }


def test_tools_list_endpoint():
    with _client() as client:
        resp = client.get("/api/assistant/tools")
    assert resp.status_code == 200, resp.text
    names = {t["name"] for t in resp.json()["tools"]}
    assert {"list_runs", "list_candidates", "search_web", "review_candidate"} <= names
    assert {
        "cv_list_documents",
        "cv_read",
        "cv_get_application_context",
        "cv_suggest_changes",
        "cv_list_suggestions",
    } <= names


def test_stateless_chat_route_is_gone():
    with _client() as client:
        resp = client.post(
            "/api/assistant/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code in (404, 405)


def test_invoke_refuses_confirm_tools_unless_approved():
    import asyncio

    from api.assistant import tools as assistant_tools
    from api.assistant.tools import CONFIRM_TOOLS
    from api.core.db import SessionLocal
    from tests.conftest import TEST_USER_ID

    with _client() as client:
        app_id = _seed_application(client)

    async def check():
        async with SessionLocal() as session:
            for name in CONFIRM_TOOLS:
                refused = await assistant_tools.invoke(name, {}, session, TEST_USER_ID)
                assert "confirmation" in refused.get("error", ""), name
            refused = await assistant_tools.invoke(
                "update_application",
                {"application_id": app_id, "status": "applying"},
                session,
                TEST_USER_ID,
            )
            assert "confirmation" in refused["error"]
            ran = await assistant_tools.invoke(
                "update_application",
                {"application_id": app_id, "status": "applying"},
                session,
                TEST_USER_ID,
                approved=True,
            )
            assert "error" not in ran, ran
            assert "error" not in await assistant_tools.invoke(
                "list_runs", {}, session, TEST_USER_ID
            )

    asyncio.run(check())


def test_chat_turn_calls_tools_then_answers(monkeypatch):
    provider = ScriptProvider(
        [
            (
                ["Let me look that up."],
                [ToolCall(id="c1", name="list_runs", arguments={})],
            ),
            (["You have no runs yet."], []),
        ]
    )
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        resp = client.post(
            f"/api/assistant/conversations/{conv_id}/chat",
            json={"content": "what runs do I have?", "context": {"page": "/new"}},
        )
    assert resp.status_code == 200, resp.text
    events = _sse_events(resp.text)
    results = [p for k, p in events if k == "tool_result"]
    assert [r["tool"] for r in results] == ["list_runs"]
    assert results[0]["ok"] is True
    assert events[-1][0] == "done" and events[-1][1]["turns"] == 2


def test_chat_unknown_tool_surfaces_error(monkeypatch):
    provider = ScriptProvider(
        [
            ([], [ToolCall(id="c1", name="no_such_tool", arguments={})]),
            (["That tool does not exist."], []),
        ]
    )
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        resp = client.post(
            f"/api/assistant/conversations/{conv_id}/chat", json={"content": "hi"}
        )
    assert resp.status_code == 200, resp.text
    [result] = [p for k, p in _sse_events(resp.text) if k == "tool_result"]
    assert result["ok"] is False
    assert "Unknown tool" in result["preview"]


def test_confirm_tools_cover_all_writes():
    from api.assistant.tools import CONFIRM_TOOLS, HANDLERS, describe_call

    # CV suggestions change nothing until accepted, so they never ask for approval.
    writes = {
        name
        for name in HANDLERS
        if name.split("_")[0] in {"save", "create", "update", "delete", "set", "review"}
    }
    assert CONFIRM_TOOLS == writes
    assert "cv_suggest_changes" not in CONFIRM_TOOLS
    assert "Stanford" in describe_call("save_program", {"school_name": "Stanford"})
    assert describe_call("review_candidate", {"approved": True}).startswith("Approve")


def test_conversation_crud():
    with _client() as client:
        created = client.post("/api/assistant/conversations")
        assert created.status_code == 200, created.text
        conv_id = created.json()["id"]

        listed = client.get("/api/assistant/conversations")
        assert listed.status_code == 200
        assert any(c["id"] == conv_id for c in listed.json())

        got = client.get(f"/api/assistant/conversations/{conv_id}")
        assert got.status_code == 200
        assert got.json()["messages"] == []
        assert got.json()["pending_call"] is None

        renamed = client.patch(
            f"/api/assistant/conversations/{conv_id}", json={"title": "My plan"}
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["title"] == "My plan"
        assert (
            client.patch(
                f"/api/assistant/conversations/{conv_id}", json={"title": "  "}
            ).status_code
            == 400
        )

        deleted = client.delete(f"/api/assistant/conversations/{conv_id}")
        assert deleted.status_code == 200
        assert client.get(f"/api/assistant/conversations/{conv_id}").status_code == 404


def test_streaming_chat_streams_tokens_and_persists(monkeypatch):

    provider = ScriptProvider(
        [
            (["You ", "have ", "no runs."], []),
        ]
    )
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        resp = client.post(
            f"/api/assistant/conversations/{conv_id}/chat",
            json={"content": "hello", "context": {"page": "/new"}},
        )
        assert resp.status_code == 200, resp.text
        events = _sse_events(resp.text)
        kinds = [k for k, _ in events]
        assert "token" in kinds, resp.text
        assert "".join(p["text"] for k, p in events if k == "token") == (
            "You have no runs."
        )
        assert kinds[-1] == "done"

        got = client.get(f"/api/assistant/conversations/{conv_id}").json()
        roles = [m["role"] for m in got["messages"]]
        assert roles == ["user", "assistant"]
        assert got["messages"][1]["content"] == "You have no runs."


def _seed_application(client) -> str:
    resp = client.post(
        "/api/applications",
        json={"school": "Flow University", "program": "PhD in Robotics"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_write_tool_pauses_for_confirm_then_applies(monkeypatch):

    app_id = None
    with _client() as client:
        app_id = _seed_application(client)
        provider = ScriptProvider(
            [
                (
                    [],
                    [
                        ToolCall(
                            id="c1",
                            name="update_application",
                            arguments={
                                "application_id": app_id,
                                "status": "applying",
                            },
                        )
                    ],
                ),
                (["Status updated."], []),
            ]
        )
        import api.assistant.service as gradis

        monkeypatch.setattr(gradis, "get_provider", lambda: provider)

        conv_id = client.post("/api/assistant/conversations").json()["id"]
        resp = client.post(
            f"/api/assistant/conversations/{conv_id}/chat",
            json={"content": "mark my application as applying"},
        )
        assert resp.status_code == 200, resp.text
        events = _sse_events(resp.text)
        confirms = [p for k, p in events if k == "confirm_required"]
        assert len(confirms) == 1
        call = confirms[0]["call"]
        assert call["tool"] == "update_application"
        assert "Update application" in call["summary"]

        assert client.get(f"/api/applications/{app_id}").json()["status"] != "applying"
        assert (
            client.post(
                f"/api/assistant/conversations/{conv_id}/chat",
                json={"content": "something else"},
            ).status_code
            == 409
        )

        approved = client.post(
            f"/api/assistant/conversations/{conv_id}/confirm",
            json={"call_id": call["id"], "approved": True},
        )
        assert approved.status_code == 200, approved.text
        kinds = [k for k, _ in _sse_events(approved.text)]
        assert "tool_result" in kinds and kinds[-1] == "done"

        assert client.get(f"/api/applications/{app_id}").json()["status"] == "applying"


def test_denied_write_leaves_state_untouched(monkeypatch):

    with _client() as client:
        app_id = _seed_application(client)
        provider = ScriptProvider(
            [
                (
                    [],
                    [
                        ToolCall(
                            id="c9",
                            name="update_application",
                            arguments={
                                "application_id": app_id,
                                "status": "applying",
                            },
                        )
                    ],
                ),
                (["Understood, leaving it."], []),
            ]
        )
        import api.assistant.service as gradis

        monkeypatch.setattr(gradis, "get_provider", lambda: provider)

        conv_id = client.post("/api/assistant/conversations").json()["id"]
        resp = client.post(
            f"/api/assistant/conversations/{conv_id}/chat",
            json={"content": "mark my application as applying"},
        )
        call = next(p for k, p in _sse_events(resp.text) if k == "confirm_required")[
            "call"
        ]
        denied = client.post(
            f"/api/assistant/conversations/{conv_id}/confirm",
            json={"call_id": call["id"], "approved": False},
        )
        assert denied.status_code == 200, denied.text
        events = _sse_events(denied.text)
        results = [p for k, p in events if k == "tool_result"]
        assert results and results[0]["ok"] is False

        assert client.get(f"/api/applications/{app_id}").json()["status"] != "applying"
        assert (
            client.post(
                f"/api/assistant/conversations/{conv_id}/confirm",
                json={"call_id": call["id"], "approved": True},
            ).status_code
            == 404
        )


def test_provider_catalog_lists_defaults_and_system():
    with _client() as client:
        resp = client.get("/api/providers/catalog")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_name = {p["provider"]: p for p in body["providers"]}
    from api.agent.llm.factory import SUPPORTED_PROVIDERS

    assert set(by_name) == set(SUPPORTED_PROVIDERS)
    assert by_name["ollama"]["default_model"] == "llama3.1"
    assert by_name["ollama"]["default_base_url"] == "http://localhost:11434/v1"
    assert by_name["openai"]["default_base_url"] == "https://api.openai.com/v1"
    assert by_name["openai-compatible"]["base_url_required"] is True
    assert by_name["anthropic"]["default_base_url"] == ""
    assert body["system"]["provider"]
    assert body["system"]["model"]


def _stub_provider(captured):
    class StubProvider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            return LLMResponse(text="stubbed reply", tool_calls=[])

        async def chat_stream(self, messages, system, tools, max_tokens=4096):
            yield {"type": "token", "text": "stubbed reply"}
            yield {
                "type": "done",
                "response": LLMResponse(text="stubbed reply", tool_calls=[]),
            }

    def factory(**kwargs):
        captured.update(kwargs)
        return StubProvider()

    return factory


def test_chat_model_override_uses_configured_row(monkeypatch):
    import api.assistant.service as gradis

    captured = {}
    monkeypatch.setattr(gradis, "get_provider", _stub_provider(captured))

    with _client() as client:
        patched = client.patch(
            "/api/providers/ollama",
            json={"model": "qwen3:8b", "api_key": "test-key"},
        )
        assert patched.status_code == 200, patched.text
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        resp = client.post(
            f"/api/assistant/conversations/{conv_id}/chat",
            json={"content": "hi", "model": {"provider": "ollama"}},
        )
    assert resp.status_code == 200, resp.text
    [message] = [p for k, p in _sse_events(resp.text) if k == "message"]
    assert message["message"]["content"] == "stubbed reply"
    assert captured.get("provider") == "ollama"
    assert captured.get("model") == "qwen3:8b"
    assert captured.get("api_key") == "test-key"
    assert captured.get("base_url") == "http://localhost:11434/v1"


def test_chat_model_override_rejects_unknown_and_unconfigured():
    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        url = f"/api/assistant/conversations/{conv_id}/chat"
        for pick in ("nope", "gemini"):
            resp = client.post(url, json={"content": "hi", "model": {"provider": pick}})
            if resp.status_code == 200:
                kinds = [k for k, _ in _sse_events(resp.text)]
                assert "error" in kinds and "message" not in kinds, pick
            else:
                assert resp.status_code == 400, resp.text


def test_chat_model_system_forces_environment(monkeypatch):
    import api.assistant.service as gradis

    captured = {}
    monkeypatch.setattr(gradis, "get_provider", _stub_provider(captured))

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        resp = client.post(
            f"/api/assistant/conversations/{conv_id}/chat",
            json={"content": "hi", "model": {"provider": "system"}},
        )
    assert resp.status_code == 200, resp.text
    # No registry overrides: the factory falls back to environment config.
    assert "model" not in captured or captured.get("provider") != "ollama"


def test_streaming_chat_honors_model_override(monkeypatch):
    import api.assistant.service as gradis

    captured = {}
    monkeypatch.setattr(gradis, "get_provider", _stub_provider(captured))

    with _client() as client:
        patched = client.patch(
            "/api/providers/openai",
            json={"model": "gpt-4o-mini", "api_key": "test-key"},
        )
        assert patched.status_code == 200, patched.text
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        resp = client.post(
            f"/api/assistant/conversations/{conv_id}/chat",
            json={"content": "hi", "model": {"provider": "openai"}},
        )
    assert resp.status_code == 200, resp.text
    assert captured.get("provider") == "openai"
    assert captured.get("model") == "gpt-4o-mini"


def test_conversation_search_matches_title_and_message_content(monkeypatch):
    provider = ScriptProvider([(["Try the ETH robotics lab."], [])])
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        by_content = client.post("/api/assistant/conversations").json()["id"]
        client.post(
            f"/api/assistant/conversations/{by_content}/chat",
            json={"content": "quadruped locomotion labs?", "context": {}},
        )
        by_title = client.post("/api/assistant/conversations").json()["id"]
        client.patch(
            f"/api/assistant/conversations/{by_title}", json={"title": "Funding 100%"}
        )

        def ids(q: str) -> set[str]:
            resp = client.get("/api/assistant/conversations", params={"q": q})
            assert resp.status_code == 200, resp.text
            return {c["id"] for c in resp.json()}

        assert by_content in ids("QUADRUPED")  # user message, case-insensitive
        assert by_content in ids("robotics lab")
        assert by_title in ids("funding")
        assert by_content not in ids("funding")
        # LIKE wildcards are literal: "%" only matches a real percent sign.
        assert ids("100%") == {by_title}
        assert by_title not in ids("_unding")
        assert {by_content, by_title} <= ids("  ")


class FlakyProvider(ScriptProvider):
    """First chat_stream call blows up mid-turn; later calls follow the script."""

    def __init__(self, steps):
        super().__init__(steps)
        self.failed = False

    async def chat_stream(self, messages, system, tools, max_tokens=4096):
        if not self.failed:
            self.failed = True
            raise RuntimeError("provider exploded")
        async for event in super().chat_stream(messages, system, tools, max_tokens):
            yield event


def test_retry_reuses_failed_turn_without_duplicating_user_message(monkeypatch):
    provider = FlakyProvider([(["Recovered."], [])])
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        url = f"/api/assistant/conversations/{conv_id}/chat"
        body = {"content": "find labs", "context": {"page": "/"}}

        failed = _sse_events(client.post(url, json=body).text)
        assert any(k == "error" for k, _ in failed)
        after_fail = client.get(f"/api/assistant/conversations/{conv_id}").json()
        assert [m["role"] for m in after_fail["messages"]] == ["user"]

        retried = _sse_events(client.post(url, json={**body, "retry": True}).text)
        assert [k for k, _ in retried][-1] == "done"
        got = client.get(f"/api/assistant/conversations/{conv_id}").json()
        assert [(m["role"], m["content"]) for m in got["messages"]] == [
            ("user", "find labs"),
            ("assistant", "Recovered."),
        ]


def test_retry_on_answered_turn_is_a_normal_send(monkeypatch):
    provider = ScriptProvider([(["One."], []), (["Two."], [])])
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        url = f"/api/assistant/conversations/{conv_id}/chat"
        client.post(url, json={"content": "hi"})
        # Nothing failed, so a stray retry must not hijack the answered turn.
        client.post(url, json={"content": "hi", "retry": True})
        roles = [
            m["role"]
            for m in client.get(f"/api/assistant/conversations/{conv_id}").json()[
                "messages"
            ]
        ]
        assert roles == ["user", "assistant", "user", "assistant"]


def _turn(client, conv_id: str, content: str, **extra) -> list[tuple[str, dict]]:
    resp = client.post(
        f"/api/assistant/conversations/{conv_id}/chat",
        json={"content": content, **extra},
    )
    assert resp.status_code == 200, resp.text
    return _sse_events(resp.text)


def _transcript(client, conv_id: str) -> list[dict]:
    resp = client.get(f"/api/assistant/conversations/{conv_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()["messages"]


def test_regenerate_replaces_reply_without_duplicating_turns(monkeypatch):
    provider = ScriptProvider([(["First answer."], []), (["Second answer."], [])])
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        _turn(client, conv_id, "first question")
        [user] = [m for m in _transcript(client, conv_id) if m["role"] == "user"]

        events = _turn(client, conv_id, "first question", replace_message_id=user["id"])

        assert events[-1][0] == "done"
        assert [(m["role"], m["content"]) for m in _transcript(client, conv_id)] == [
            ("user", "first question"),
            ("assistant", "Second answer."),
        ]
        sent = provider.seen[-1]
        assert sent == [{"role": "user", "content": "first question"}]


def test_edit_earlier_prompt_drops_later_turns(monkeypatch):
    provider = ScriptProvider([(["a1"], []), (["b1"], []), (["a2"], [])])
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        _turn(client, conv_id, "alpha")
        _turn(client, conv_id, "beta")
        first_user = _transcript(client, conv_id)[0]

        _turn(client, conv_id, "alpha edited", replace_message_id=first_user["id"])

        assert [(m["role"], m["content"]) for m in _transcript(client, conv_id)] == [
            ("user", "alpha edited"),
            ("assistant", "a2"),
        ]
        assert provider.seen[-1] == [{"role": "user", "content": "alpha edited"}]
        # The first prompt names the chat, so an edit renames it too.
        assert client.get(f"/api/assistant/conversations/{conv_id}").json()["title"] == (
            "alpha edited"
        )


def test_edit_second_prompt_keeps_the_earlier_turn(monkeypatch):
    provider = ScriptProvider([(["a1"], []), (["b1"], []), (["b2"], [])])
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        _turn(client, conv_id, "alpha")
        _turn(client, conv_id, "beta")
        second_user = _transcript(client, conv_id)[2]

        _turn(client, conv_id, "beta edited", replace_message_id=second_user["id"])

        assert [(m["role"], m["content"]) for m in _transcript(client, conv_id)] == [
            ("user", "alpha"),
            ("assistant", "a1"),
            ("user", "beta edited"),
            ("assistant", "b2"),
        ]
        assert provider.seen[-1] == [
            {"role": "user", "content": "alpha"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "beta edited"},
        ]


def test_replace_refuses_assistant_and_unknown_messages(monkeypatch):
    provider = ScriptProvider([(["answer"], [])])
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        _turn(client, conv_id, "hello")
        assistant = next(
            m for m in _transcript(client, conv_id) if m["role"] == "assistant"
        )

        for target in (assistant["id"], "does-not-exist"):
            events = _turn(client, conv_id, "hi", replace_message_id=target)
            assert [k for k, _ in events] == ["error"], target

        assert [(m["role"], m["content"]) for m in _transcript(client, conv_id)] == [
            ("user", "hello"),
            ("assistant", "answer"),
        ]


def _shape(segments: list[dict]) -> list[tuple]:
    """(kind, tool, turn) per entry of a turn log."""
    return [(s.get("kind"), s.get("tool"), s.get("turn")) for s in segments]


def test_turn_log_interleaves_model_text_and_tool_calls(monkeypatch):
    provider = ScriptProvider(
        [
            (
                ["Let me look that up."],
                [ToolCall(id="c1", name="list_runs", arguments={})],
            ),
            (["You have no runs yet."], []),
        ]
    )
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        events = _turn(client, conv_id, "any runs?")

        starts = [p for k, p in events if k == "tool_start"]
        assert starts[0]["turn"] == 1
        results = [p for k, p in events if k == "tool_result"]
        assert results[0]["turn"] == 1

        [assistant] = [
            m for m in _transcript(client, conv_id) if m["role"] == "assistant"
        ]
        assert _shape(assistant["segments"]) == [
            ("turn", None, 1),
            (None, "list_runs", 1),
            ("turn", None, 2),
        ]
        assert assistant["segments"][0]["note"] == "Let me look that up."
        assert assistant["segments"][2]["note"] == "You have no runs yet."
        assert assistant["segments"][1]["ok"] is True
        assert assistant["content"] == "You have no runs yet."
        # The flat tool list still drives the saved-record cards.
        assert [t["tool"] for t in assistant["tools"]] == ["list_runs"]


def test_running_out_of_steps_says_so(monkeypatch):
    import api.assistant.service as gradis

    provider = ScriptProvider([(["Checking."], [ToolCall(id="c1", name="list_runs", arguments={})])])
    monkeypatch.setattr(gradis, "get_provider", lambda: provider)
    monkeypatch.setattr(gradis, "MAX_CHAT_TURNS", 1)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        _turn(client, conv_id, "any runs?")
        [assistant] = [m for m in _transcript(client, conv_id) if m["role"] == "assistant"]
        assert assistant["content"].startswith("I ran out of steps")


def test_permission_pause_keeps_the_output_and_merges_it_into_the_reply(
    monkeypatch,
):
    with _client() as client:
        app_id = _seed_application(client)
        provider = ScriptProvider(
            [
                (
                    ["Let me check your applications first."],
                    [ToolCall(id="c1", name="list_applications", arguments={})],
                ),
                (
                    ["I will mark the Flow University application as applying."],
                    [
                        ToolCall(
                            id="c2",
                            name="update_application",
                            arguments={
                                "application_id": app_id,
                                "status": "applying",
                            },
                        )
                    ],
                ),
                (["Done — the application is now applying."], []),
            ]
        )
        import api.assistant.service as gradis

        monkeypatch.setattr(gradis, "get_provider", lambda: provider)

        conv_id = client.post("/api/assistant/conversations").json()["id"]
        events = _turn(client, conv_id, "mark my application as applying")

        confirm = next(p for k, p in events if k == "confirm_required")
        call = confirm["call"]
        assert call["tool"] == "update_application"
        assert call["turn"] == 2
        # The call carries the log so far, so the client can show it while it waits.
        assert _shape(call["segments"]) == [
            ("turn", None, 1),
            (None, "list_applications", 1),
            ("turn", None, 2),
        ]
        pending = client.get(f"/api/assistant/conversations/{conv_id}").json()[
            "pending_call"
        ]
        assert _shape(pending["segments"]) == _shape(call["segments"])

        # The turn is not finished, so nothing is in the transcript yet.
        assert [m["role"] for m in _transcript(client, conv_id)] == ["user"]

        approved = client.post(
            f"/api/assistant/conversations/{conv_id}/confirm",
            json={"call_id": call["id"], "approved": True},
        )
        assert approved.status_code == 200, approved.text
        assert [k for k, _ in _sse_events(approved.text)][-1] == "done"

        [assistant] = [
            m for m in _transcript(client, conv_id) if m["role"] == "assistant"
        ]
        assert assistant["content"] == "Done — the application is now applying."
        assert _shape(assistant["segments"]) == [
            ("turn", None, 1),
            (None, "list_applications", 1),
            ("turn", None, 2),
            (None, "update_application", 2),
            ("turn", None, 3),
        ]
        assert [t["tool"] for t in assistant["tools"]] == [
            "list_applications",
            "update_application",
        ]
        assert [m["role"] for m in provider.seen[-1]] == [
            "user",
            "assistant",
            "tool",
            "assistant",
            "tool",
        ]


def test_denied_permission_still_keeps_the_output(monkeypatch):
    with _client() as client:
        app_id = _seed_application(client)
        provider = ScriptProvider(
            [
                (
                    ["I will mark the application as applying."],
                    [
                        ToolCall(
                            id="c9",
                            name="update_application",
                            arguments={
                                "application_id": app_id,
                                "status": "applying",
                            },
                        )
                    ],
                ),
                (["Understood, leaving it."], []),
            ]
        )
        import api.assistant.service as gradis

        monkeypatch.setattr(gradis, "get_provider", lambda: provider)

        conv_id = client.post("/api/assistant/conversations").json()["id"]
        events = _turn(client, conv_id, "mark my application as applying")
        call = next(p for k, p in events if k == "confirm_required")["call"]

        denied = client.post(
            f"/api/assistant/conversations/{conv_id}/confirm",
            json={"call_id": call["id"], "approved": False},
        )
        assert denied.status_code == 200, denied.text

        [assistant] = [
            m for m in _transcript(client, conv_id) if m["role"] == "assistant"
        ]
        assert assistant["content"] == "Understood, leaving it."
        assert _shape(assistant["segments"]) == [
            ("turn", None, 1),
            (None, "update_application", 1),
            ("turn", None, 2),
        ]
        assert assistant["segments"][1]["ok"] is False
        assert client.get(f"/api/applications/{app_id}").json()["status"] != "applying"


class FlakyAfterApproval(ScriptProvider):
    """Canned provider that dies once, on the call after an approval."""

    def __init__(self, steps):
        super().__init__(steps)
        self.calls = 0

    async def chat_stream(self, messages, system, tools, max_tokens=4096):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("the model gave up")
        async for event in super().chat_stream(messages, system, tools, max_tokens):
            yield event


def test_turn_that_dies_after_the_approval_can_be_continued(monkeypatch):
    with _client() as client:
        app_id = _seed_application(client)
        provider = FlakyAfterApproval(
            [
                (
                    ["I will mark the application as applying."],
                    [
                        ToolCall(
                            id="c1",
                            name="update_application",
                            arguments={
                                "application_id": app_id,
                                "status": "applying",
                            },
                        )
                    ],
                ),
                (["Done — the application is now applying."], []),
            ]
        )
        import api.assistant.service as gradis

        monkeypatch.setattr(gradis, "get_provider", lambda: provider)

        conv_id = client.post("/api/assistant/conversations").json()["id"]
        events = _turn(client, conv_id, "mark my application as applying")
        call = next(p for k, p in events if k == "confirm_required")["call"]

        approved = client.post(
            f"/api/assistant/conversations/{conv_id}/confirm",
            json={"call_id": call["id"], "approved": True},
        )
        assert approved.status_code == 200, approved.text
        # The model died after the call had run.
        kinds = [k for k, _ in _sse_events(approved.text)]
        assert kinds[:2] == ["tool_start", "tool_result"]
        assert kinds[-1] == "error"
        assert client.get(f"/api/applications/{app_id}").json()["status"] == "applying"
        assert [m["role"] for m in _transcript(client, conv_id)] == ["user"]
        assert (
            client.get(f"/api/assistant/conversations/{conv_id}").json()["pending_call"]
            is None
        )

        # The client retries: carry the turn on instead of starting over.
        retried = client.post(
            f"/api/assistant/conversations/{conv_id}/chat",
            json={
                "content": "mark my application as applying",
                "continue_turn": True,
            },
        )
        assert retried.status_code == 200, retried.text
        assert [k for k, _ in _sse_events(retried.text)][-1] == "done"

        [assistant] = [
            m for m in _transcript(client, conv_id) if m["role"] == "assistant"
        ]
        assert assistant["content"] == "Done — the application is now applying."
        assert _shape(assistant["segments"]) == [
            ("turn", None, 1),
            (None, "update_application", 1),
            ("turn", None, 2),
        ]
        assert [m["role"] for m in provider.seen[-1]] == ["user", "assistant", "tool"]
        assert provider.calls == 3


def test_queued_prompt_is_answered_after_the_current_turn(monkeypatch):
    provider = ScriptProvider([(["First answer."], []), (["Second answer."], [])])
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        queued = client.post(
            f"/api/assistant/conversations/{conv_id}/queue",
            json={"content": "and then this"},
        )
        assert queued.status_code == 200, queued.text
        assert queued.json()["content"] == "and then this"

        events = _turn(client, conv_id, "first question")

        kinds = [k for k, _ in events]
        assert "user_message" in kinds
        assert kinds[-1] == "done"
        assert [p["message"]["content"] for k, p in events if k == "message"] == [
            "First answer.",
            "Second answer.",
        ]
        assert [(m["role"], m["content"]) for m in _transcript(client, conv_id)] == [
            ("user", "first question"),
            ("assistant", "First answer."),
            ("user", "and then this"),
            ("assistant", "Second answer."),
        ]
        assert provider.seen[-1] == [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "First answer."},
            {"role": "user", "content": "and then this"},
        ]


def test_urgent_prompt_reaches_the_running_turn(monkeypatch):
    provider = ScriptProvider(
        [
            (
                ["Looking into it."],
                [ToolCall(id="c1", name="list_runs", arguments={})],
            ),
            (["Done, and I used your note."], []),
        ]
    )
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        urgent = client.post(
            f"/api/assistant/conversations/{conv_id}/queue",
            json={"content": "focus on robotics labs", "urgent": True},
        )
        assert urgent.status_code == 200, urgent.text
        assert urgent.json()["urgent"] is True

        _turn(client, conv_id, "find me a lab")

        assert provider.seen[0] == [
            {"role": "user", "content": "find me a lab"},
            {"role": "user", "content": "focus on robotics labs"},
        ]
        assert [(m["role"], m["content"]) for m in _transcript(client, conv_id)] == [
            ("user", "find me a lab"),
            ("user", "focus on robotics labs"),
            ("assistant", "Done, and I used your note."),
        ]
        assert client.get(f"/api/assistant/conversations/{conv_id}").json()["queue"] == []


def test_queue_endpoints_list_promote_and_remove(monkeypatch):
    provider = ScriptProvider([(["ok"], [])])
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        first = client.post(
            f"/api/assistant/conversations/{conv_id}/queue",
            json={"content": "one"},
        ).json()
        second = client.post(
            f"/api/assistant/conversations/{conv_id}/queue",
            json={"content": "two", "urgent": True},
        ).json()

        listed = client.get(f"/api/assistant/conversations/{conv_id}").json()["queue"]
        assert [i["content"] for i in listed] == ["one", "two"]
        assert [i["urgent"] for i in listed] == [False, True]

        promoted = client.patch(
            f"/api/assistant/conversations/{conv_id}/queue/{first['id']}",
            json={"urgent": True},
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["urgent"] is True

        removed = client.delete(
            f"/api/assistant/conversations/{conv_id}/queue/{second['id']}"
        )
        assert removed.status_code == 200, removed.text
        left = client.get(f"/api/assistant/conversations/{conv_id}").json()["queue"]
        assert [(i["id"], i["urgent"]) for i in left] == [(first["id"], True)]


def test_one_turn_at_a_time(monkeypatch):
    """A second turn would interleave with the first and tangle its history."""
    import asyncio

    import httpx

    from api.main import app

    gate = asyncio.Event()

    class SlowProvider(ScriptProvider):
        async def chat_stream(self, messages, system, tools, max_tokens=4096):
            await gate.wait()
            async for event in super().chat_stream(messages, system, tools, max_tokens):
                yield event

    provider = SlowProvider([(["hi"], [])])
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            conv_id = (
                await client.post("/api/assistant/conversations")
            ).json()["id"]
            first = asyncio.create_task(
                client.post(
                    f"/api/assistant/conversations/{conv_id}/chat",
                    json={"content": "one"},
                )
            )
            await asyncio.sleep(0.2)
            second = await client.post(
                f"/api/assistant/conversations/{conv_id}/chat",
                json={"content": "two"},
            )
            assert second.status_code == 409, second.text
            gate.set()
            assert (await first).status_code == 200

    asyncio.run(run())


def test_message_without_a_turn_log_keeps_the_plain_shape(monkeypatch):
    """Messages from before the ordered log hold tool calls only."""
    import asyncio
    import json

    provider = ScriptProvider([(["answer"], [])])
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        _turn(client, conv_id, "hello")

        async def rewrite():
            from sqlalchemy import select

            from api.assistant import models as assistant_models
            from api.core.db import SessionLocal

            async with SessionLocal() as session:
                msg = (
                    (
                        await session.execute(
                            select(assistant_models.AssistantMessage).where(
                                assistant_models.AssistantMessage.conversation_id
                                == conv_id
                            )
                        )
                    )
                    .scalars()
                    .all()[-1]
                )
                msg.tool_calls_json = json.dumps(
                    [
                        {
                            "turn": 1,
                            "tool": "list_runs",
                            "input": {},
                            "result_preview": "[]",
                            "ok": True,
                        }
                    ]
                )
                await session.commit()

        asyncio.run(rewrite())

        [assistant] = [
            m for m in _transcript(client, conv_id) if m["role"] == "assistant"
        ]
        assert assistant["segments"] == []
        assert [t["tool"] for t in assistant["tools"]] == ["list_runs"]
        assert assistant["content"] == "answer"


class ThinkingProvider:
    """A thinking model: each call pops (text, truncated); records budgets."""

    def __init__(self, steps, thought=""):
        self.steps = list(steps)
        self.thought = thought
        self.budgets: list[int] = []

    async def chat_stream(self, messages, system, tools, max_tokens=4096):
        self.budgets.append(max_tokens)
        text, truncated = self.steps.pop(0)
        if self.thought:
            yield {"type": "reasoning", "text": self.thought}
        if text:
            yield {"type": "token", "text": text}
        yield {"type": "done", "response": LLMResponse(text=text, tool_calls=[], truncated=truncated, reasoning=self.thought)}


def _ask(monkeypatch, provider, prompt="Tighten my CV"):
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda **_: provider)
    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        resp = client.post(f"/api/assistant/conversations/{conv_id}/chat", json={"content": prompt})
    assert resp.status_code == 200, resp.text
    return [p for k, p in _sse_events(resp.text) if k == "message"][-1]["message"]["content"]


def test_a_reply_cut_off_while_thinking_is_asked_again_with_room(monkeypatch):
    from api.agent.llm.base import roomier
    from api.core.config import settings

    provider = ThinkingProvider([("", True), ("Here are three edits.", False)])
    assert _ask(monkeypatch, provider) == "Here are three edits."
    assert provider.budgets == [settings.llm_max_tokens, roomier(settings.llm_max_tokens)]


def test_a_reply_cut_off_twice_says_so_instead_of_having_no_answer(monkeypatch):
    import api.assistant.service as gradis

    provider = ThinkingProvider([("", True), ("", True)])
    assert _ask(monkeypatch, provider) == gradis.CUT_OFF
    assert len(provider.budgets) == 2


def test_a_cut_off_reply_that_said_something_is_kept(monkeypatch):
    provider = ThinkingProvider([("Partly answered", True)])
    assert _ask(monkeypatch, provider) == "Partly answered"
    assert len(provider.budgets) == 1


def test_the_models_thoughts_stream_and_stay_with_the_reply(monkeypatch):
    import api.assistant.service as gradis

    provider = ThinkingProvider([("", True), ("Done.", False)], thought="Weighing the summary.")
    monkeypatch.setattr(gradis, "get_provider", lambda **_: provider)
    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        resp = client.post(f"/api/assistant/conversations/{conv_id}/chat", json={"content": "Tighten it"})
        saved = client.get(f"/api/assistant/conversations/{conv_id}").json()
    events = _sse_events(resp.text)
    reasoning = [p for k, p in events if k == "reasoning"]
    # The first attempt's thoughts are dropped when it asks again.
    assert [p.get("reset", False) for p in reasoning] == [False, True, False]
    message = [p for k, p in events if k == "message"][-1]["message"]
    assert message["content"] == "Done."
    turn = [s for s in message["segments"] if s.get("kind") == "turn"]
    assert turn == [{"kind": "turn", "turn": 1, "note": "Done.", "thought": "Weighing the summary."}]
    assert saved["messages"][-1]["segments"] == message["segments"]

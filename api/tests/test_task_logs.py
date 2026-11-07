import asyncio
import json

from fastapi.testclient import TestClient

from api.core.db import SessionLocal
from api.runs import queue
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID


def _stub_provider(
    *, final_text="stub summary", tool_name="score_alignment", tool_args=None
):
    from api.agent.llm.base import LLMResponse, ToolCall

    calls = {"n": 0}

    class StubProvider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            calls["n"] += 1
            if calls["n"] == 1:
                return LLMResponse(
                    text="thinking out loud",
                    tool_calls=[
                        ToolCall(
                            id="t1", name=tool_name, arguments=tool_args or {"q": "x"}
                        )
                    ],
                )
            return LLMResponse(text=final_text, tool_calls=[])

    return StubProvider()


def test_orchestrator_emits_tool_events(monkeypatch):
    import api.agent.orchestrator as orch

    monkeypatch.setattr(orch, "get_provider", lambda: _stub_provider())

    big_result = {"data": "y" * 5000}

    # dispatch_batch is the seam: it takes [(name, arguments)] and returns results in request order.
    async def fake_dispatch(calls, ctx, task_type=None):
        assert [name for name, _ in calls] == ["score_alignment"]
        return [big_result for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)

    events = []

    async def on_event(event):
        events.append(event)

    out = asyncio.run(
        orch.run_agent_task("sys", "hello", ctx=object(), on_event=on_event)  # type: ignore[arg-type]
    )

    assert [(e.get("kind"), e.get("note")) for e in events if e.get("kind")] == [
        ("turn", "thinking out loud"),
        ("turn", "stub summary"),
    ]
    assert events[0]["kind"] == "turn"
    tool_events = [e for e in events if e.get("kind") != "turn"]
    assert len(tool_events) == 1
    event = tool_events[0]
    assert "note" not in event
    assert event["turn"] == 1
    assert event["tool"] == "score_alignment"
    assert event["input"] == {"q": "x"}
    assert event["ok"] is True
    # Preview is truncated to the char budget plus "..."; the full result stays in tool_log.
    assert len(event["result_preview"]) <= orch.RESULT_PREVIEW_CHARS + 3
    assert "yyy" in event["result_preview"]
    assert out["tool_log"][0]["turn"] == 1
    assert out["tool_log"][0]["result"] == big_result


def test_orchestrator_marks_failed_tool_calls(monkeypatch):
    import api.agent.orchestrator as orch

    monkeypatch.setattr(orch, "get_provider", lambda: _stub_provider())

    async def fake_dispatch(calls, ctx, task_type=None):
        return [{"error": "No program in context"} for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)

    events = []

    async def on_event(event):
        events.append(event)

    asyncio.run(
        orch.run_agent_task("sys", "hello", ctx=object(), on_event=on_event)  # type: ignore[arg-type]
    )
    assert [e["ok"] for e in events if e.get("kind") != "turn"] == [False]


def test_orchestrator_preserves_tool_call_extras(monkeypatch):
    """Provider-native extras (Gemini thought signatures) must be replayable next turn."""
    import api.agent.orchestrator as orch
    from api.agent.llm.base import LLMResponse, ToolCall

    sig = {"google": {"thought_signature": "sig-abc"}}
    calls = {"n": 0}

    class StubProvider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            calls["n"] += 1
            if calls["n"] == 1:
                return LLMResponse(
                    text="thinking",
                    tool_calls=[
                        ToolCall(
                            id="t1",
                            name="search_web",
                            arguments={"query": "x"},
                            extra_content=sig,
                        )
                    ],
                )
            return LLMResponse(text="final", tool_calls=[])

    async def fake_dispatch(calls, ctx, task_type=None):
        return [{"ok": True} for _ in calls]

    monkeypatch.setattr(orch, "get_provider", lambda: StubProvider())
    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)

    checkpoints: list = []

    async def on_checkpoint(messages):
        checkpoints.append(messages)

    asyncio.run(
        orch.run_agent_task("sys", "hello", ctx=object(), on_checkpoint=on_checkpoint)  # type: ignore[arg-type]
    )
    assistant = next(
        m for m in checkpoints[-1] if m.get("role") == "assistant" and m.get("tool_calls")
    )
    assert assistant["tool_calls"][0]["extra_content"] == sig


def _recording_provider(*, requires_extras: bool, replies):
    calls = {"n": 0, "seen": []}

    class StubProvider:
        requires_tool_call_extras = requires_extras

        async def chat(self, messages, system, tools, max_tokens=4096):
            calls["n"] += 1
            calls["seen"].append(messages)
            return replies[min(calls["n"] - 1, len(replies) - 1)]

    return StubProvider(), calls


def test_resume_drops_history_missing_required_extras(monkeypatch):
    """A checkpoint missing required extras restarts fresh instead of resuming to a 400."""
    import api.agent.orchestrator as orch
    from api.agent.llm.base import LLMResponse

    poisoned = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": "thinking",
            "tool_calls": [{"id": "t1", "name": "search_web", "arguments": {}}],
        },
        {"role": "tool", "tool_call_id": "t1", "name": "search_web", "content": "{}"},
    ]
    provider, calls = _recording_provider(
        requires_extras=True,
        replies=[LLMResponse(text="fresh finish", tool_calls=[])],
    )
    monkeypatch.setattr(orch, "get_provider", lambda: provider)

    out = asyncio.run(
        orch.run_agent_task("sys", "hello", ctx=object(), resume_messages=poisoned)  # type: ignore[arg-type]
    )
    assert out["final_text"] == "fresh finish"
    assert out["turns"] == 1
    first_seen = calls["seen"][0]
    assert [m.get("role") for m in first_seen] == ["user"]
    assert first_seen[0]["content"] != "go"


def test_resume_keeps_history_with_extras(monkeypatch):
    import api.agent.orchestrator as orch
    from api.agent.llm.base import LLMResponse

    sig = {"google": {"thought_signature": "sig-abc"}}
    intact = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": "thinking",
            "tool_calls": [
                {
                    "id": "t1",
                    "name": "search_web",
                    "arguments": {},
                    "extra_content": sig,
                }
            ],
        },
        {"role": "tool", "tool_call_id": "t1", "name": "search_web", "content": "{}"},
    ]
    provider, calls = _recording_provider(
        requires_extras=True,
        replies=[LLMResponse(text="resumed finish", tool_calls=[])],
    )
    monkeypatch.setattr(orch, "get_provider", lambda: provider)

    out = asyncio.run(
        orch.run_agent_task("sys", "hello", ctx=object(), resume_messages=intact)  # type: ignore[arg-type]
    )
    assert out["final_text"] == "resumed finish"
    assert calls["seen"][0] == intact


def _make_run_and_task():

    async def setup():
        async with SessionLocal() as session:
            run = Run(user_id=TEST_USER_ID, 
                region="United States",
                field="robotics",
                degree_level="phd",
                interest_statement="robots",
                status="running",
            )
            session.add(run)
            await session.flush()
            task = ResearchTask(user_id=TEST_USER_ID, run_id=run.id, task_type="discover_programs")
            session.add(task)
            await session.commit()
            return run.id, task.id

    return asyncio.run(setup())


def test_process_one_persists_trace(monkeypatch, capsys):
    import api.agent.orchestrator as orch

    run_id, task_id = _make_run_and_task()

    # save_program counts as progress for discover_programs, so no nudge.
    monkeypatch.setattr(
        orch, "get_provider", lambda: _stub_provider(tool_name="save_program")
    )

    async def fake_dispatch(calls, ctx, task_type=None):
        return [{"program_id": "p1"} for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)

    async def fake_claim(session):
        task = await session.get(ResearchTask, task_id)
        task.status = TaskStatus.running
        await session.commit()
        return task

    monkeypatch.setattr(queue, "_claim_next_task", fake_claim)

    assert asyncio.run(queue.process_one()) is True

    async def fetch():
        async with SessionLocal() as session:
            return await session.get(ResearchTask, task_id)

    task = asyncio.run(fetch())
    assert task is not None
    assert task.status == TaskStatus.done
    assert task.turns == 2
    assert task.final_text == "stub summary"
    assert task.log is not None
    events = json.loads(task.log)
    assert [e.get("kind") or e["tool"] for e in events] == [
        "turn",
        "save_program",
        "turn",
    ]
    assert events[0]["note"] == "thinking out loud"
    assert events[1]["ok"] is True
    assert all(e["at"].endswith("Z") for e in events)

    async def tool_rows():
        from sqlalchemy import func, select

        from api.runs.models import ToolCallLog

        async with SessionLocal() as session:
            return (
                await session.execute(
                    select(func.count())
                    .select_from(ToolCallLog)
                    .where(ToolCallLog.task_id == task_id)
                )
            ).scalar()

    assert asyncio.run(tool_rows()) == 1  # turn entries are trace-only

    out = capsys.readouterr().out
    assert "claimed discover_programs" in out
    assert "save_program" in out
    assert "done discover_programs" in out
    _ = run_id


def test_list_tasks_endpoint():
    from api.main import app

    async def setup():
        async with SessionLocal() as session:
            run = Run(user_id=TEST_USER_ID, 
                region="United States",
                field="robotics",
                degree_level="phd",
                interest_statement="robots",
                status="running",
            )
            session.add(run)
            await session.flush()
            task = ResearchTask(user_id=TEST_USER_ID, run_id=run.id, task_type="research_professor")
            task.status = TaskStatus.done
            task.turns = 3
            task.final_text = "found two profs"
            task.log = json.dumps([{"turn": 1, "tool": "search_web", "ok": True}])
            session.add(task)
            await session.commit()
            return run.id

    run_id = asyncio.run(setup())

    with TestClient(app) as client:
        resp = client.get(f"/api/runs/{run_id}/tasks")
        assert resp.status_code == 200, resp.text
        tasks = resp.json()
        assert len(tasks) >= 1
        ours = next(t for t in tasks if t["final_text"] == "found two profs")
        assert ours["task_type"] == "research_professor"
        assert ours["status"] == "done"
        assert ours["turns"] == 3
        assert ours["log"] == [{"turn": 1, "tool": "search_web", "ok": True}]

        assert client.get("/api/runs/does-not-exist/tasks").status_code == 404


def test_trace_events_carry_the_attempts_tokens_so_far(monkeypatch):
    import api.agent.orchestrator as orch
    from api.agent.llm.base import LLMResponse, ToolCall

    class Provider:
        n = 0

        async def chat(self, messages, system, tools, max_tokens=4096):
            Provider.n += 1
            usage = {"input_tokens": 100, "output_tokens": 10}
            if Provider.n == 1:
                return LLMResponse(text="look it up", tool_calls=[ToolCall(id="t1", name="score_alignment", arguments={})], usage=usage)
            return LLMResponse(text="done", tool_calls=[], usage=usage)

    async def fake_dispatch(calls, ctx, task_type=None):
        return [{"ok": True} for _ in calls]

    monkeypatch.setattr(orch, "get_provider", lambda: Provider())
    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)
    events = []

    async def on_event(event):
        events.append(event)

    asyncio.run(orch.run_agent_task("sys", "hello", ctx=object(), on_event=on_event))  # type: ignore[arg-type]
    assert [(e.get("kind") or e["tool"], e["tokens"]) for e in events] == [
        ("turn", 110),
        ("score_alignment", 110),
        ("turn", 220),
    ]

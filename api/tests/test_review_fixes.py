import asyncio
import json

import pytest

from api.candidates import scoring
from api.core.config import settings
from api.core.db import SessionLocal
from api.runs import queue
from api.runs.models import ResearchTask, Run, TaskStatus, ToolCallLog
from tests.conftest import TEST_USER_ID


def test_score_with_vector_mismatch_returns_none(monkeypatch):
    monkeypatch.setattr(scoring, "embed_texts", lambda texts, **_: [[0.0, 0.0, 0.0]])
    assert scoring.score_with_vector([1.0, 0.0], ["a"]) is None

    monkeypatch.setattr(scoring, "embed_texts", lambda texts, **_: [[1.0, 0.0]])
    assert scoring.score_with_vector(["not", "numbers"], ["a"]) is None  # type: ignore[list-item]


def _one_tool_stub():
    from api.agent.llm.base import LLMResponse, ToolCall

    calls = {"n": 0}

    class StubProvider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            calls["n"] += 1
            if calls["n"] == 1:
                return LLMResponse(
                    text="",
                    tool_calls=[
                        ToolCall(id="t1", name="score_alignment", arguments={})
                    ],
                )
            return LLMResponse(text="done", tool_calls=[])

    return StubProvider()


def test_resume_preserves_prior_log(monkeypatch):
    import api.agent.orchestrator as orch

    old_event = {"turn": 1, "tool": "search_web", "ok": True}

    async def setup():
        async with SessionLocal() as session:
            run = Run(user_id=TEST_USER_ID, 
                region="U",
                field="f",
                degree_level="phd",
                interest_statement="x",
                status="running",
            )
            session.add(run)
            await session.flush()
            task = ResearchTask(user_id=TEST_USER_ID, run_id=run.id, task_type="discover_programs")
            task.log = json.dumps([old_event])
            session.add(task)
            await session.commit()
            return task.id

    task_id = asyncio.run(setup())
    monkeypatch.setattr(orch, "get_provider", lambda: _one_tool_stub())

    # dispatch_batch is the seam: it takes [(name, arguments)] and returns results in request order.
    async def fake_dispatch(calls, ctx, task_type=None):
        return [{"score": 1} for _ in calls]

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
    assert task.log is not None
    events = json.loads(task.log)
    assert events[0] == old_event
    tools = [e for e in events[1:] if e.get("kind") != "turn"]
    assert [e["tool"] for e in tools] == ["score_alignment"]


@pytest.mark.parametrize("cap", [0, 1_000_000, 20_000])
def test_tool_call_log_result_json_always_valid(monkeypatch, cap):
    """Past TOOL_LOG_MAX_CHARS a result is a valid truncated envelope, not sliced JSON."""
    import api.agent.orchestrator as orch

    monkeypatch.setattr(settings, "tool_log_max_chars", cap)

    async def setup():
        async with SessionLocal() as session:
            run = Run(user_id=TEST_USER_ID, 
                region="U",
                field="f",
                degree_level="phd",
                interest_statement="x",
                status="running",
            )
            session.add(run)
            await session.flush()
            task = ResearchTask(user_id=TEST_USER_ID, run_id=run.id, task_type="discover_programs")
            session.add(task)
            await session.commit()
            return task.id

    task_id = asyncio.run(setup())
    monkeypatch.setattr(orch, "get_provider", lambda: _one_tool_stub())

    async def fake_dispatch(calls, ctx, task_type=None):
        return [{"blob": "z" * 50000} for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)

    async def fake_claim(session):
        task = await session.get(ResearchTask, task_id)
        task.status = TaskStatus.running
        await session.commit()
        return task

    monkeypatch.setattr(queue, "_claim_next_task", fake_claim)
    assert asyncio.run(queue.process_one()) is True

    async def fetch_rows():
        from sqlalchemy import select

        async with SessionLocal() as session:
            return (
                (
                    await session.execute(
                        select(ToolCallLog).where(ToolCallLog.task_id == task_id)
                    )
                )
                .scalars()
                .all()
            )

    rows = asyncio.run(fetch_rows())
    assert len(rows) == 1
    parsed = json.loads(rows[0].result_json)
    if cap == 20_000:
        assert parsed["truncated"] is True
        assert parsed["chars"] > cap
        assert len(parsed["preview"]) == cap
    else:
        assert parsed == {"blob": "z" * 50000}

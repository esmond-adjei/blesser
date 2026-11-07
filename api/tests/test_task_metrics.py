import asyncio
import types
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import api.agent.orchestrator as orch
from api.agent.llm.base import LLMResponse, ToolCall
from api.candidates.models import CandidateScore
from api.core.db import SessionLocal
from api.main import app
from api.prospects import pipeline
from api.prospects import tasks as prospect_tasks
from api.prospects.models import Professor
from api.runs import queue
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID
from tests.test_budgets import _make_program, _make_run


class _Provider:
    name = "ollama"
    model = "qwen3vl"

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, system, tools, max_tokens=4096):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                text="looking",
                tool_calls=[ToolCall(id="t1", name="score_alignment", arguments={})],
                usage={"input_tokens": 10, "output_tokens": 2, "cache_read_tokens": 4},
            )
        return LLMResponse(text="done", tool_calls=[], usage={"input_tokens": 5, "output_tokens": 1})


def test_the_agent_loop_records_the_model_and_where_time_went(monkeypatch):
    monkeypatch.setattr(orch, "get_provider", lambda **_: _Provider())

    async def tools(calls, ctx, task_type=None):
        return [{"score": 0.5} for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", tools)
    totals = {"input_tokens": 0, "output_tokens": 0}

    async def go():
        orch.task_usage.set(totals)
        return await orch.run_agent_task("sys", "go", ctx=types.SimpleNamespace())  # type: ignore[arg-type]

    asyncio.run(go())
    assert totals["provider"] == "ollama" and totals["model"] == "qwen3vl"
    assert totals["cache_read_tokens"] == 4
    assert totals["model_seconds"] > 0 and totals["tool_seconds"] > 0


def _task(**fields):
    run_id = _make_run()

    async def setup():
        async with SessionLocal() as session:
            task = ResearchTask(user_id=TEST_USER_ID, run_id=run_id, task_type="research_one_professor", **fields)
            session.add(task)
            await session.commit()
            return run_id, task.id

    return asyncio.run(setup())


def test_the_queue_stores_metrics_and_adds_them_up_over_attempts(monkeypatch):
    run_id, task_id = _task(model_seconds=2.0, tool_seconds=1.0, cache_read_tokens=3, path="agent", path_reason="resume")

    async def handler(session, task, run, **kwargs):
        orch.note_task_model(types.SimpleNamespace(name="anthropic", model="claude-x"))
        orch.add_task_time(model=1.5, tool=0.5)
        orch.set_task_path("likely")
        orch.add_task_usage({"input_tokens": 7, "output_tokens": 3, "cache_read_tokens": 5}, 1)
        return {"final_text": "saved", "turns": 1, "usage": {"input_tokens": 7, "output_tokens": 3}}

    monkeypatch.setitem(queue.TASK_HANDLERS, "research_one_professor", handler)
    real_claim = queue._claim_next_task
    monkeypatch.setattr(queue, "_claim_next_task", lambda session: real_claim(session, run_id))
    assert asyncio.run(queue.process_one()) is True

    async def read():
        async with SessionLocal() as session:
            return await session.get(ResearchTask, task_id)

    task = asyncio.run(read())
    assert task.status == TaskStatus.done
    assert (task.provider, task.model) == ("anthropic", "claude-x")
    assert task.model_seconds == pytest.approx(3.5) and task.tool_seconds == pytest.approx(1.5)
    assert task.cache_read_tokens == 8
    assert (task.path, task.path_reason) == ("likely", None)
    assert (task.input_tokens, task.output_tokens) == (7, 3)  # not counted twice


@pytest.mark.pipeline
@pytest.mark.parametrize(
    ("decision", "path"),
    [
        (pipeline.Decision("agent", "2 authors at the school", code="multiple_authors"), ("agent", "multiple_authors")),
        (pipeline.Decision("no_match", "unrelated"), ("no_match", None)),
    ],
)
def test_a_professor_task_records_its_route(monkeypatch, decision, path):
    run_id = _make_run()
    _, program_id = _make_program(run_id)
    totals = {"input_tokens": 0, "output_tokens": 0}

    async def first_pass(ctx, school, name, on_event=None, indexed=None):
        return decision

    async def agent(*args, **kwargs):
        return {"final_text": "concluded", "tool_log": [], "turns": 1, "usage": {}, "nudges": 0}

    monkeypatch.setattr(pipeline, "first_pass", first_pass)
    monkeypatch.setattr(prospect_tasks, "run_agent_task", agent)

    async def go(resume=None):
        orch.task_usage.set(totals)
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            task = ResearchTask(
                user_id=TEST_USER_ID, run_id=run_id, task_type="research_one_professor",
                target_id=program_id, target_name="Ada Walker",
            )  # fmt: skip
            session.add(task)
            await session.commit()
            await prospect_tasks.run_research_one_professor(session, task, run, resume_messages=resume)

    asyncio.run(go())
    assert (totals["path"], totals["path_reason"]) == path
    # A resumed task skips the first pass, unless its checkpoint has no model turn yet.
    asyncio.run(go(resume=[{"role": "user", "content": "go"}, {"role": "assistant", "content": "looking"}]))
    assert (totals["path"], totals["path_reason"]) == ("agent", "resume")


def test_run_usage_reports_the_cost_per_candidate():
    run_id = _make_run()
    _, program_id = _make_program(run_id)

    async def setup():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            rows = [
                {"path": "no_match", "input_tokens": 0, "output_tokens": 0},
                {"path": "likely", "input_tokens": 2000, "output_tokens": 200, "provider": "ollama", "model": "qwen3vl"},
                {"path": "agent", "path_reason": "application_indexing", "input_tokens": 40000, "output_tokens": 1800,
                 "provider": "ollama", "model": "qwen3vl", "cache_read_tokens": 500, "model_seconds": 60.0, "tool_seconds": 12.5},
            ]  # fmt: skip
            for row in rows:
                session.add(ResearchTask(user_id=TEST_USER_ID, run_id=run_id, task_type="research_one_professor", status=TaskStatus.done, **row))
            for name in ("Ada", "Grace"):
                prof = Professor(user_id=TEST_USER_ID, program_id=program_id, name=name)
                session.add(prof)
                await session.flush()
                session.add(
                    CandidateScore(
                        user_id=TEST_USER_ID, run_id=run_id, professor_id=prof.id, similarity_score=0.6,
                        rationale="r", created_at=run.created_at + timedelta(minutes=7),
                    )
                )  # fmt: skip
            await session.commit()

    asyncio.run(setup())
    body = TestClient(app).get(f"/api/runs/{run_id}/usage").json()
    assert body["candidates"] == 2
    assert body["tokens_per_candidate"] == (2200 + 41800) // 2
    assert body["first_candidate_seconds"] == pytest.approx(420, abs=1)
    assert body["narrow_paths"] == {"no_match": 1, "likely": 1, "agent": 1}
    assert body["narrow_fallbacks"] == {"application_indexing": 1}
    assert body["cache_read_tokens"] == 500
    assert body["model_seconds"] == 60.0 and body["tool_seconds"] == 12.5
    assert body["models"] == [
        {"provider": "ollama", "model": "qwen3vl", "tasks": 2, "input_tokens": 42000, "output_tokens": 2000}
    ]

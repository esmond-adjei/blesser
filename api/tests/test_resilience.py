import asyncio
import json
from datetime import timedelta
from typing import Any, cast

import pytest

from api.agent.tools import ToolContext, dispatch
from api.candidates.models import CandidateScore
from api.core.db import SessionLocal
from api.prospects.models import Professor, Program, RunSchool, School
from api.runs import queue
from api.runs.models import ResearchTask, Run, TaskStatus, ToolCallLog
from tests.conftest import TEST_USER_ID
from tests.grounding_helpers import ground


def _tool_call_stub(*, crash_on_second_chat=False, usage=None):
    from api.agent.llm.base import LLMResponse, ToolCall

    usage = usage or {}
    calls = {"n": 0}

    class StubProvider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            calls["n"] += 1
            if calls["n"] == 1:
                return LLMResponse(
                    text="working",
                    tool_calls=[
                        ToolCall(id="t1", name="score_alignment", arguments={})
                    ],
                    usage=dict(usage),
                )
            if crash_on_second_chat:
                raise RuntimeError("simulated crash")
            return LLMResponse(text="finished", tool_calls=[], usage=dict(usage))

    return StubProvider()


def test_compaction_replaces_old_tool_results():
    from api.agent.orchestrator import _compact_old_tool_results

    messages = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "on it"},
        {
            "role": "tool",
            "tool_call_id": "a",
            "name": "fetch_page",
            "content": "X" * 5000,
            "_turn": 1,
        },
        {
            "role": "tool",
            "tool_call_id": "b",
            "name": "search_web",
            "content": "fresh",
            "_turn": 3,
        },
    ]
    out = _compact_old_tool_results(messages, current_turn=4, max_age_turns=2, block_turns=1)
    assert out[0]["content"] == "go"
    assert out[1]["content"] == "on it"
    assert out[2]["content"] == "[fetch_page result already used - omitted]"
    assert out[2]["tool_call_id"] == "a"
    assert out[3]["content"] == "fresh"
    # Input list untouched (compaction is a per-call view).
    assert messages[2]["content"] == "X" * 5000


def test_compaction_disabled_at_zero():
    from api.agent.orchestrator import _compact_old_tool_results

    messages = [
        {"role": "tool", "tool_call_id": "a", "name": "x", "content": "big", "_turn": 1}
    ]
    assert (
        _compact_old_tool_results(messages, current_turn=99, max_age_turns=0)
        is messages
    )


def test_run_agent_task_resumes_from_checkpoint(monkeypatch):
    import api.agent.orchestrator as orch

    monkeypatch.setattr(
        orch, "get_provider", lambda: _tool_call_stub(crash_on_second_chat=True)
    )

    # dispatch_batch is the seam: it takes [(name, arguments)] and returns results in request order.
    async def fake_dispatch(calls, ctx, task_type=None):
        return [{"score": 0.5} for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)

    checkpoints = []

    async def on_checkpoint(messages):
        checkpoints.append(json.loads(json.dumps(messages, default=str)))

    with pytest.raises(RuntimeError, match="simulated crash"):
        asyncio.run(
            orch.run_agent_task(
                "sys", "hello", ctx=cast(Any, object()), on_checkpoint=on_checkpoint
            )
        )
    assert len(checkpoints) == 1
    saved = checkpoints[0]
    assert any(m.get("role") == "tool" for m in saved)

    class DoneProvider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            from api.agent.llm.base import LLMResponse

            return LLMResponse(text="finished", tool_calls=[])

    monkeypatch.setattr(orch, "get_provider", lambda: DoneProvider())
    dispatch_calls = []

    async def spy_dispatch(calls, ctx):
        dispatch_calls.extend(name for name, _ in calls)
        return [{} for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", spy_dispatch)
    out = asyncio.run(
        orch.run_agent_task("sys", "hello", ctx=object(), resume_messages=saved)  # type: ignore[arg-type]
    )
    assert out["final_text"] == "finished"
    assert out["turns"] == 2  # 1 used + this one
    assert dispatch_calls == []


def test_usage_is_accumulated(monkeypatch):
    import api.agent.orchestrator as orch

    monkeypatch.setattr(
        orch,
        "get_provider",
        lambda: _tool_call_stub(usage={"input_tokens": 10, "output_tokens": 5}),
    )

    async def fake_dispatch(calls, ctx, task_type=None):
        return [{} for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)
    out = asyncio.run(orch.run_agent_task("sys", "hi", ctx=object()))  # type: ignore[arg-type]
    assert out["usage"] == {"input_tokens": 20, "output_tokens": 10}


def _make_task(status="running", updated_at=None, messages_json=None):

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
            task.status = status
            if updated_at is not None:
                task.updated_at = updated_at
            if messages_json is not None:
                task.messages_json = messages_json
            session.add(task)
            await session.commit()
            return task.id

    return asyncio.run(setup())


def test_reap_stale_tasks_requeues(monkeypatch):

    monkeypatch.setattr(queue.settings, "stale_task_minutes", 15)
    old_id = _make_task(
        messages_json=json.dumps([{"role": "user"}]),
        updated_at=queue._utcnow() - timedelta(minutes=30),
    )
    fresh_id = _make_task()

    async def reap():
        async with SessionLocal() as session:
            return await queue.reap_stale_tasks(session)

    # The reaper is global, so assert on our rows, not the total count.
    assert asyncio.run(reap()) >= 1

    async def fetch(task_id):
        async with SessionLocal() as session:
            return await session.get(ResearchTask, task_id)

    old, fresh = asyncio.run(fetch(old_id)), asyncio.run(fetch(fresh_id))
    assert old is not None
    assert fresh is not None
    assert old.status == TaskStatus.pending
    assert old.messages_json == json.dumps([{"role": "user"}])  # kept for resume
    assert fresh.status == TaskStatus.running


def test_dedup_returns_existing_record():
    from sqlalchemy import func, select

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
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run.id)], name="S")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="P")
            session.add(program)
            await session.commit()
            return run.id, program.id

    run_id, program_id = asyncio.run(setup())
    payload = {
        "name": "Ada Lovelace",
        "openalex_id": "https://openalex.org/A123",
        "papers": [{"title": "Analytical Engines and robotic planning methods"}],
        "similarity_score": 0.9,
        "rationale": "Cites Analytical Engines and robotic planning methods directly.",
    }

    async def save_twice():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            first = await dispatch("save_professor_record", ground(ctx, dict(payload)), ctx)
            second = await dispatch("save_professor_record", ground(ctx, dict(payload)), ctx)
            profs = (
                await session.execute(
                    select(func.count())
                    .select_from(Professor)
                    .where(Professor.program_id == program_id)
                )
            ).scalar()
            cands = (
                await session.execute(
                    select(func.count())
                    .select_from(CandidateScore)
                    .where(CandidateScore.run_id == run_id)
                )
            ).scalar()
            return first, second, profs, cands

    first, second, profs, cands = asyncio.run(save_twice())
    assert "candidate_id" in first
    assert second.get("deduped") is True
    assert second["professor_id"] == first["professor_id"]
    assert second["candidate_id"] == first["candidate_id"]
    assert profs == 1
    assert cands == 1


def test_tool_call_log_rows_written(monkeypatch):
    from sqlalchemy import select

    import api.agent.orchestrator as orch

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
    monkeypatch.setattr(orch, "get_provider", lambda: _tool_call_stub())

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
            task = await session.get(ResearchTask, task_id)
            assert task is not None
            rows = (
                (
                    await session.execute(
                        select(ToolCallLog).where(ToolCallLog.task_id == task_id)
                    )
                )
                .scalars()
                .all()
            )
            return task, rows

    task, rows = asyncio.run(fetch())
    assert task.input_tokens == 0
    assert len(rows) == 1
    assert rows[0].tool_name == "score_alignment"
    assert rows[0].ok is True
    assert json.loads(rows[0].input_json) == {}


def test_failed_handler_rolls_back_stray_rows(monkeypatch):
    from sqlalchemy import func, select

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
            return run.id, task.id

    run_id, task_id = asyncio.run(setup())

    async def bad_handler(
        session, task, run, on_event=None, resume_messages=None, on_checkpoint=None
    ):
        session.add(School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run.id)], name="Stray"))
        raise ValueError("boom")

    monkeypatch.setitem(queue.TASK_HANDLERS, "discover_programs", bad_handler)

    async def fake_claim(session):
        task = await session.get(ResearchTask, task_id)
        task.status = TaskStatus.running
        await session.commit()
        return task

    monkeypatch.setattr(queue, "_claim_next_task", fake_claim)
    assert asyncio.run(queue.process_one()) is True

    async def fetch():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            assert task is not None
            strays = (
                await session.execute(
                    select(func.count())
                    .select_from(RunSchool)
                    .where(RunSchool.run_id == run_id)
                )
            ).scalar()
            return task, strays

    task, strays = asyncio.run(fetch())
    assert task.status == TaskStatus.error
    assert task.error == "boom"
    assert strays == 0


def test_worker_loop_survives_iteration_error(monkeypatch, capsys):
    calls = []

    async def flaky_process_one():
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("db drop")
        return False

    class _Break(Exception):
        pass

    async def stop_sleep(seconds):
        raise _Break()

    monkeypatch.setattr(queue, "process_one", flaky_process_one)
    monkeypatch.setattr(queue.asyncio, "sleep", stop_sleep)

    with pytest.raises(_Break):
        asyncio.run(queue.worker_loop(0, 0.01))
    # Otherwise ConnectionError escapes instead of _Break and the loop never reaches sleep.
    assert len(calls) == 1
    assert "loop 0 error" in capsys.readouterr().out


def test_usage_accumulates_across_resume(monkeypatch):
    import api.agent.orchestrator as orch
    from api.agent.llm.base import LLMResponse, ToolCall

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
            task.input_tokens = 100
            task.output_tokens = 50
            session.add(task)
            await session.commit()
            return task.id

    task_id = asyncio.run(setup())

    # save_program counts as progress, so no nudges: usage is exactly 2 chats x {10, 5}.
    calls = {"n": 0}

    class StubProvider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            calls["n"] += 1
            if calls["n"] == 1:
                return LLMResponse(
                    text="",
                    tool_calls=[ToolCall(id="t1", name="save_program", arguments={})],
                    usage={"input_tokens": 10, "output_tokens": 5},
                )
            return LLMResponse(
                text="done",
                tool_calls=[],
                usage={"input_tokens": 10, "output_tokens": 5},
            )

    monkeypatch.setattr(orch, "get_provider", lambda: StubProvider())

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
    assert (task.input_tokens, task.output_tokens) == (120, 60)

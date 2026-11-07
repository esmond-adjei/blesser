import asyncio
import json
import types
from datetime import timedelta

import pytest
from sqlalchemy import select

from api.agent.tools import ToolContext, dispatch_batch
from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.prospects import leads, web
from api.prospects.models import Program, RunSchool, School
from api.runs.models import ResearchTask, Run, TaskStatus, ToolCallLog
from tests.conftest import TEST_USER_ID
from tests.test_budgets import _make_program, _make_run

NARROW = "research_one_professor"


def _batches(monkeypatch, calls, task_type=NARROW, rounds=1):
    run_id = _make_run()
    _, program_id = _make_program(run_id)

    async def go():
        async with SessionLocal() as session:
            ctx = ToolContext(
                session=session,
                run=await session.get(Run, run_id),
                program=await session.get(Program, program_id),
            )
            return [await dispatch_batch(calls, ctx, task_type) for _ in range(rounds)]

    return asyncio.run(go())


def test_a_professor_task_is_capped_per_tool(monkeypatch):
    fetched = []

    async def fetch(url, max_chars=3000, offset=0):
        fetched.append(url)
        return "Faculty page"

    monkeypatch.setattr(web, "fetch_page", fetch)
    calls = [("fetch_page", {"url": f"https://uni.example/{i}"}) for i in range(6)]
    (results,) = _batches(monkeypatch, calls)
    assert [r.get("text") for r in results[:4]] == ["Faculty page"] * 4
    for refused in results[4:]:
        assert refused["error"].startswith("Tool call limit: fetch_page was already called 4 times")
        assert refused["gate"] == "cap.task_tool_calls"
    assert len(fetched) == 4
    fetched.clear()
    (results,) = _batches(monkeypatch, calls, task_type="research_professor")
    assert len(fetched) == 6 and all("text" in r for r in results)


def test_an_identical_failed_read_is_not_sent_again(monkeypatch):
    sent = []

    async def search(query, max_results=8):
        sent.append(query)
        raise web.SearchUnavailable("Web search is unavailable right now (tried: tavily). Work from URLs.")

    async def allowed(*args, **kwargs):
        return None

    from api.billing import service as billing

    monkeypatch.setattr(web, "search_web", search)
    monkeypatch.setattr(billing, "tool_call_refusal", allowed)
    first, second = _batches(monkeypatch, [("search_web", {"query": "robotics faculty"})], rounds=2)
    assert first[0]["error"].startswith("search_web failed: Web search is unavailable")
    assert "already failed in this task (Web search is unavailable right now (tried: tavily))" in second[0]["error"]
    assert second[0]["gate"] == "tool.repeated_failure"
    assert sent == ["robotics faculty"]


def test_calls_before_a_checkpoint_count_against_the_caps(monkeypatch):
    import api.agent.orchestrator as orch
    from api.agent.llm.base import LLMResponse

    class Done:
        async def chat(self, messages, system, tools, max_tokens=4096):
            return LLMResponse(text="done", tool_calls=[])

    monkeypatch.setattr(orch, "get_provider", lambda **_: Done())
    history = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": f"t{i}", "name": "fetch_page", "arguments": {}} for i in range(3)],
        },
    ]
    ctx = types.SimpleNamespace()
    asyncio.run(orch.run_agent_task("sys", "go", ctx=ctx, resume_messages=history))  # type: ignore[arg-type]
    assert ctx.tool_call_counts == {"fetch_page": 3}


def _leads_run(outcomes_a: list[str]):
    """Two programmes with done supervisors and 3 waiting leads each; A's outcomes oldest first ("added:" student-added, "failed:" errored)."""

    async def setup():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID, region="U", field="f", degree_level="phd",
                interest_statement="robots", status="running", max_professors=20,
            )  # fmt: skip
            session.add(run)
            await session.flush()
            programmes = []
            for name in ("A", "B"):
                school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run.id)], name=f"Uni {name}")
                session.add(school)
                await session.flush()
                program = Program(user_id=TEST_USER_ID, school_id=school.id, name=name)
                session.add(program)
                await session.flush()
                programmes.append(program.id)
                session.add(
                    ResearchTask(
                        run_id=run.id, user_id=TEST_USER_ID, task_type="research_professor",
                        target_id=program.id, status=TaskStatus.done,
                    )
                )  # fmt: skip
            a, b = programmes
            start = utcnow_naive() - timedelta(hours=1)
            for i, outcome in enumerate(outcomes_a):
                kind, _, outcome = outcome.rpartition(":")
                task = ResearchTask(
                    run_id=run.id, user_id=TEST_USER_ID, task_type=NARROW, target_id=a,
                    target_name=f"A{i}", status=TaskStatus.error if kind == "failed" else TaskStatus.done,
                    finished_at=start + timedelta(minutes=i),
                    path_reason="user_added" if kind == "added" else None,
                )  # fmt: skip
                session.add(task)
                await session.flush()
                tool, args = (
                    ("save_professor_record", {"name": f"A{i}"})
                    if outcome == "saved"
                    else ("confirm_no_match", {"reason": "r", "reason_code": outcome})
                )
                session.add(
                    ToolCallLog(
                        user_id=TEST_USER_ID, task_id=task.id, turn=1, tool_name=tool,
                        input_json=json.dumps(args), result_json="{}", ok=True,
                    )
                )  # fmt: skip
            for programme, prefix in ((a, "a"), (b, "b")):
                for i in range(3):
                    session.add(
                        ResearchTask(
                            run_id=run.id, user_id=TEST_USER_ID, task_type=NARROW, target_id=programme,
                            target_name=f"{prefix}-lead{i}", status=TaskStatus.deferred,
                        )
                    )  # fmt: skip
            await session.commit()
            return run.id, a, b

    return asyncio.run(setup())


def _release(run_id):
    async def go():
        async with SessionLocal() as session:
            await leads.release_deferred_leads(session, run_id)
            await session.commit()
            rows = (
                await session.execute(
                    select(ResearchTask.target_id, ResearchTask.status, ResearchTask.error).where(
                        ResearchTask.run_id == run_id, ResearchTask.target_name.like("%-lead%")
                    )
                )
            ).all()
            return rows

    return asyncio.run(go())


def test_a_programme_stops_after_a_run_of_unrelated_professors():
    run_id, a, b = _leads_run(["saved", "low_score", "low_score", "institution", "low_score"])
    rows = _release(run_id)
    a_rows = [r for r in rows if r.target_id == a]
    b_rows = [r for r in rows if r.target_id == b]
    assert all(r.status == TaskStatus.deferred for r in a_rows)
    assert all(r.error.startswith(leads.MISS_STREAK_NOTE) for r in a_rows)
    assert all(r.status == TaskStatus.pending for r in b_rows)  # its slots go to B


@pytest.mark.parametrize(
    "outcomes",
    [
        ["low_score", "low_score", "saved"],  # a save resets the streak
        ["low_score", "low_score"],
    ],
)
def test_a_programme_keeps_its_leads_without_a_streak(outcomes):
    run_id, a, _ = _leads_run(outcomes)
    rows = _release(run_id)
    assert any(r.target_id == a and r.status == TaskStatus.pending for r in rows)
    assert not any(r.error for r in rows)


def test_the_streak_can_be_switched_off(monkeypatch):
    from api.core.config import settings

    monkeypatch.setattr(settings, "programme_miss_streak", 0)
    run_id, a, _ = _leads_run(["low_score"] * 4)
    rows = _release(run_id)
    assert any(r.target_id == a and r.status == TaskStatus.pending for r in rows)


def test_the_run_says_which_leads_a_streak_held_back():
    from fastapi.testclient import TestClient

    from api.main import app

    run_id, _, _ = _leads_run(["low_score"] * 3)
    _release(run_id)

    async def finish():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            run.status = "done"
            await session.commit()

    asyncio.run(finish())
    body = TestClient(app).get(f"/api/runs/{run_id}/refusals").json()
    reasons = {r["gate"]: r for r in body["not_saved"]}
    assert reasons["narrow.programme_stopped"]["count"] == 3
    assert reasons["narrow.programme_stopped"]["label"] == "Not researched (programme kept missing)"

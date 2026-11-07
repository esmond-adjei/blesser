import asyncio
from types import SimpleNamespace

from sqlalchemy import text

from api.agent.llm.base import LLMResponse
from api.core.config import settings
from api.core.db import SessionLocal
from api.runs import queue
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID


async def _run_with(tasks: list[tuple[str, TaskStatus]]) -> str:
    async with SessionLocal() as session:
        run = Run(
            user_id=TEST_USER_ID,
            region="U",
            field="f",
            degree_level="phd",
            interest_statement="x",
            status="running",
        )
        session.add(run)
        await session.flush()
        for task_type, status in tasks:
            session.add(
                ResearchTask(
                    run_id=run.id, user_id=TEST_USER_ID, task_type=task_type, status=status
                )
            )
            await session.flush()  # distinct created_at, in this order
        await session.commit()
        return run.id


async def _claim(run_ids) -> str | None:
    async with SessionLocal() as session:
        task = await queue._claim_next_task(session, run_ids)
        return None if task is None else task.task_type


def test_first_professor_of_a_run_jumps_its_supervisors():
    async def scenario():
        run_id = await _run_with(
            [
                ("research_professor", TaskStatus.pending),
                ("research_professor", TaskStatus.pending),
                ("research_one_professor", TaskStatus.pending),
                ("research_one_professor", TaskStatus.pending),
            ]
        )
        return [await _claim(run_id) for _ in range(5)]

    assert asyncio.run(scenario()) == [
        "research_one_professor",
        "research_professor",
        "research_professor",
        "research_one_professor",
        None,
    ]


def test_drafts_still_come_first():
    async def scenario():
        run_id = await _run_with(
            [
                ("research_one_professor", TaskStatus.pending),
                ("draft_email", TaskStatus.pending),
            ]
        )
        return await _claim(run_id)

    assert asyncio.run(scenario()) == "draft_email"


def test_run_with_fewer_tasks_running_goes_first():
    async def scenario():
        busy = await _run_with(
            [
                ("research_professor", TaskStatus.running),
                ("research_professor", TaskStatus.running),
                ("research_professor", TaskStatus.pending),
            ]
        )
        idle = await _run_with([("research_professor", TaskStatus.pending)])
        async with SessionLocal() as session:
            task = await queue._claim_next_task(session, [busy, idle])
            return task.run_id, idle

    claimed, idle = asyncio.run(scenario())
    # The busy run's supervisor is older, but the idle run gets the loop.
    assert claimed == idle


def test_new_run_wakes_the_worker(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app
    from api.runs import service as run_service

    woken: list[str] = []

    async def record(session, run_id):
        woken.append(run_id)

    monkeypatch.setattr(run_service, "notify_work", record)
    resp = TestClient(app).post(
        "/api/runs",
        json={
            "region": "U",
            "field": "f",
            "degree_level": "phd",
            "interest_statement": "robots and control",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    assert woken == [resp.json()["id"]]


def test_no_connection_idles_in_a_transaction_during_a_model_call(monkeypatch):
    import api.agent.orchestrator as orch
    from api.agent.tools.context import ToolContext

    seen: list[int] = []

    class Probe:
        name = model = "probe"

        async def chat(self, messages, system, tools, max_tokens=4096):
            async with SessionLocal() as other:
                count = (
                    await other.execute(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname = current_database() "
                            "AND state LIKE 'idle in transaction%'"
                        )
                    )
                ).scalar()
            seen.append(int(count or 0))
            return LLMResponse(text="Done.", tool_calls=[])

    monkeypatch.setattr(orch, "get_provider", lambda **_: Probe())

    async def go():
        run_id = await _run_with([])
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            await orch.run_agent_task(
                "BASE",
                "go",
                ToolContext(session=session, run=run),
                task_type="discover_programs",
            )

    asyncio.run(go())
    assert seen == [0]


def test_model_call_past_its_deadline_is_retried(monkeypatch):
    import api.agent.orchestrator as orch

    monkeypatch.setattr(settings, "llm_call_deadline_seconds", 0.05)
    monkeypatch.setattr(settings, "llm_retry_backoff_seconds", 0)
    calls = {"n": 0}

    class HangsOnce:
        async def chat(self, messages, system, tools, max_tokens=4096):
            calls["n"] += 1
            if calls["n"] == 1:
                await asyncio.sleep(5)  # a backend that never answers
            return LLMResponse(text="finished", tool_calls=[])

    monkeypatch.setattr(orch, "get_provider", lambda **_: HangsOnce())
    ctx = SimpleNamespace(session=None, user_id=None, run=None)
    out = asyncio.run(orch.run_agent_task("sys", "go", ctx=ctx))
    assert out["final_text"] == "finished"
    assert calls["n"] == 2

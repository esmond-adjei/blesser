import asyncio
import itertools
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api.agent.llm.base import LLMResponse, ToolCall
from api.agents import models as agents_models
from api.agents import registry
from api.auth import models as auth_models
from api.core.db import SessionLocal
from api.main import app
from api.runs import queue
from api.runs.models import ResearchTask, TaskStatus

counter = itertools.count()


class KeepSaving:
    """A model that keeps finding schools in its shard's tier, two a turn."""

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, system, tools, max_tokens=4096):
        self.calls += 1
        brief = messages[0]["content"]
        tier = brief.split("covers only ", 1)[1].split(" ", 1)[0]
        calls = []
        for _ in range(2):
            n = next(counter)
            calls.append(
                ToolCall(
                    id=f"c{n}",
                    name="save_program",
                    arguments={
                        "school_name": f"University {tier} {n}",
                        "school_country": "Canada",
                        "program_name": "PhD in Computer Science",
                        "department_url": f"https://u{n}.example.edu/cs",
                        "school_tier": tier,
                    },
                )
            )
        return LLMResponse(text="", tool_calls=calls)


def _run(max_programs, tiers):
    resp = TestClient(app).post(
        "/api/runs",
        json={
            "region": "Canada",
            "field": "computer science",
            "degree_level": "phd",
            "interest_statement": "relighting of reconstructed scenes",
            "max_programs": max_programs,
            "school_tiers": tiers,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _process(run_id):
    """Run this run's discovery task via the claimed path; process_one could take another test's task."""

    async def go():
        async with SessionLocal() as session:
            task = (
                await session.execute(
                    select(ResearchTask).where(ResearchTask.run_id == run_id, ResearchTask.task_type == "discover_programs")
                )
            ).scalar_one()
            task.status = TaskStatus.running
            await session.commit()
            await queue._process_claimed(session, task)

    asyncio.run(go())


async def _discovery(run_id):
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(ResearchTask).where(ResearchTask.run_id == run_id, ResearchTask.task_type == "discover_programs")
            )
        ).scalars().all()
        return {t.target_name: t for t in rows}


def test_parallel_shards_that_fill_the_budget_finish_as_done(monkeypatch):
    import api.agent.orchestrator as orch

    model = KeepSaving()
    monkeypatch.setattr(orch, "get_provider", lambda **_: model)
    run_id = _run(4, ["top", "strong", "solid"])

    async def one(shard):
        async with SessionLocal() as session:
            task = (
                await session.execute(
                    select(ResearchTask).where(ResearchTask.run_id == run_id, ResearchTask.target_name == shard)
                )
            ).scalar_one()
            task.status = TaskStatus.running
            await session.commit()
            await queue._process_claimed(session, task)

    async def go():
        await asyncio.gather(*[one(f"tier:{t}") for t in ("top", "strong", "solid")])
        return await _discovery(run_id)

    shards = asyncio.run(go())
    assert len(shards) == 3
    for name, task in shards.items():
        assert task.status == TaskStatus.done, (name, task.error)
        assert task.error is None
        assert "discovery is complete" in task.final_text, task.final_text
    assert model.calls <= 6


def test_a_failure_after_the_budget_is_full_is_not_an_error(monkeypatch):
    run_id = _run(1, [])

    async def fill_then_fail(session, task, run, **kwargs):
        from api.prospects.models import RunSchool, School

        session.add(School(run_links=[RunSchool(origin="agent", run_id=run.id)], user_id=run.user_id, name="Only School"))
        await session.commit()
        raise RuntimeError("model went away")

    monkeypatch.setitem(queue.TASK_HANDLERS, "discover_programs", fill_then_fail)
    _process(run_id)
    task = asyncio.run(_discovery(run_id))[None]
    assert task.status == TaskStatus.done and task.error is None
    assert task.final_text.startswith("The run's school budget is reached (1 of 1")


def test_a_failure_with_room_left_is_still_an_error(monkeypatch):
    run_id = _run(5, [])

    async def fail(session, task, run, **kwargs):
        raise RuntimeError("model went away")

    monkeypatch.setitem(queue.TASK_HANDLERS, "discover_programs", fail)
    _process(run_id)
    task = asyncio.run(_discovery(run_id))[None]
    assert task.status == TaskStatus.error and "model went away" in task.error


def test_parallel_registry_seeding_for_a_new_account():
    async def go():
        async with SessionLocal() as session:
            user_id = str(uuid.uuid4())
            session.add(auth_models.User(id=user_id, email=f"{user_id}@example.com", password_hash="x"))
            await session.commit()

        async def seed():
            async with SessionLocal() as session:
                await registry.ensure_registry(session, user_id)

        await asyncio.gather(*[seed() for _ in range(4)])
        async with SessionLocal() as session:
            tools = (
                await session.execute(
                    select(func.count()).select_from(agents_models.AgentTool).where(agents_models.AgentTool.user_id == user_id)
                )
            ).scalar()
            return tools

    assert asyncio.run(go()) > 0

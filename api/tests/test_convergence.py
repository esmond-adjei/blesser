import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from api.agent.tools import ToolContext, dispatch
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.prospects.models import Program, RunSchool, School
from api.runs import queue
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID
from tests.grounding_helpers import ground


def _make_run(**kwargs):
    async def setup():
        async with SessionLocal() as session:
            run = Run(user_id=TEST_USER_ID, 
                region="U",
                field="f",
                degree_level="phd",
                interest_statement="robots",
                status="running",
                **kwargs,
            )
            session.add(run)
            await session.commit()
            return run.id

    return asyncio.run(setup())


def _make_program(run_id):
    async def setup():
        async with SessionLocal() as session:
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run_id)], name="S")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="P")
            session.add(program)
            await session.commit()
            return program.id

    return asyncio.run(setup())


def _program_input(n):
    return {"school_name": f"Uni {n}", "program_name": f"PhD Program {n}"}


def _professor_input(n):
    return {
        "name": f"Prof {n}",
        "papers": [{"title": f"Paper {n} on mobile robotics navigation"}],
        "similarity_score": 0.9,
        "rationale": f"Strong match: their work in Paper {n} on mobile robotics navigation aligns directly.",
    }


def test_save_program_run_budget():
    run_id = _make_run(max_programs=1)

    async def saves():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            ctx = ToolContext(session=session, run=run)
            first = await dispatch("save_program", _program_input(1), ctx)
            second = await dispatch("save_program", _program_input(2), ctx)
            return first, second

    first, second = asyncio.run(saves())
    assert "program_id" in first
    assert "error" in second
    assert "Run program budget" in second["error"]


def test_save_program_falls_back_to_settings(monkeypatch):
    monkeypatch.setattr(settings, "max_programs_per_run", 1)
    run_id = _make_run()

    async def saves():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            ctx = ToolContext(session=session, run=run)
            first = await dispatch("save_program", _program_input(1), ctx)
            second = await dispatch("save_program", _program_input(2), ctx)
            return first, second

    first, second = asyncio.run(saves())
    assert "program_id" in first
    assert "Run program budget" in second["error"]


def test_spawn_researches_up_to_program_limit_and_dedupes():
    run_id = _make_run(max_professors_per_program=2)
    program_id = _make_program(run_id)

    async def spawn():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            first = await dispatch(
                "spawn_professor_research", {"names": ["Ada", "Grace", "Edsger"]}, ctx
            )
            second = await dispatch(
                "spawn_professor_research", {"names": ["Ada", "Grace"]}, ctx
            )
            rows = (
                (
                    await session.execute(
                        select(ResearchTask)
                        .where(
                            ResearchTask.run_id == run_id,
                            ResearchTask.task_type == "research_one_professor",
                        )
                        .order_by(ResearchTask.created_at)
                    )
                )
                .scalars()
                .all()
            )
            return first, second, rows

    first, second, rows = asyncio.run(spawn())
    # Only the program's share is researched now, best first; the rest wait for a slot.
    assert first["queued"] == 3
    assert first["researching_now"] == 2
    assert first["waiting"] == 1
    assert second["queued"] == 0
    assert [(r.target_name, r.status) for r in rows] == [
        ("Ada", TaskStatus.pending),
        ("Grace", TaskStatus.pending),
        ("Edsger", TaskStatus.deferred),
    ]


def test_spawn_falls_back_to_settings(monkeypatch):
    monkeypatch.setattr(settings, "max_professors_per_program", 2)
    run_id = _make_run()
    program_id = _make_program(run_id)

    async def spawn():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            return await dispatch(
                "spawn_professor_research",
                {"names": ["A", "B", "C", "D"]},
                ctx,
            )

    out = asyncio.run(spawn())
    assert out["researching_now"] == 2


def test_save_professor_honors_run_override(monkeypatch):
    monkeypatch.setattr(settings, "max_candidates_per_run", 100)
    run_id = _make_run(max_professors=1)
    program_id = _make_program(run_id)

    async def saves():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            first = await dispatch("save_professor_record", ground(ctx, _professor_input(1)), ctx)
            second = await dispatch("save_professor_record", ground(ctx, _professor_input(2)), ctx)
            return first, second

    first, second = asyncio.run(saves())
    assert "candidate_id" in first
    assert "Run candidate budget" in second["error"]


def test_create_run_accepts_limits():
    client = TestClient(app)
    resp = client.post(
        "/api/runs",
        json={
            "region": "U",
            "field": "f",
            "degree_level": "phd",
            "interest_statement": "robots",
            "max_programs": 3,
            "max_professors": 9,
            "max_professors_per_program": 2,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["max_programs"] == 3
    assert body["max_professors"] == 9
    assert body["max_professors_per_program"] == 2

    assert (
        client.post(
            "/api/runs",
            json={
                "region": "U",
                "field": "f",
                "degree_level": "phd",
                "interest_statement": "robots",
                "max_programs": 0,
            },
        ).status_code
        == 422
    )


def test_draft_claimed_before_older_research():
    run_id = _make_run()

    async def setup():
        async with SessionLocal() as session:
            session.add(
                ResearchTask(user_id=TEST_USER_ID, 
                    run_id=run_id,
                    task_type="research_professor",
                    status=TaskStatus.pending,
                )
            )
            draft = ResearchTask(user_id=TEST_USER_ID, 
                run_id=run_id, task_type="draft_email", status=TaskStatus.pending
            )
            session.add(draft)
            await session.commit()
            return draft.id

    draft_id = asyncio.run(setup())

    async def claim():
        async with SessionLocal() as session:
            return await queue._claim_next_task(session)

    claimed = asyncio.run(claim())
    assert claimed is not None
    assert claimed.id == draft_id
    assert claimed.status == TaskStatus.running


def test_supervisor_claimed_before_older_narrow():
    """Only a run's first narrow task jumps the supervisors (see test_scheduling.py)."""
    run_id = _make_run()

    async def setup():
        async with SessionLocal() as session:
            base = datetime.now(UTC).replace(tzinfo=None)
            session.add(
                ResearchTask(
                    user_id=TEST_USER_ID,
                    run_id=run_id,
                    task_type="research_one_professor",
                    target_name="In Flight",
                    status=TaskStatus.running,
                    created_at=base - timedelta(minutes=40),
                )
            )
            session.add(
                ResearchTask(user_id=TEST_USER_ID, 
                    run_id=run_id,
                    task_type="research_one_professor",
                    target_name="Old Narrow",
                    status=TaskStatus.pending,
                    created_at=base - timedelta(minutes=30),
                )
            )
            session.add(
                ResearchTask(user_id=TEST_USER_ID, 
                    run_id=run_id,
                    task_type="research_professor",
                    status=TaskStatus.pending,
                )
            )
            await session.commit()

    asyncio.run(setup())

    async def ordered():
        from sqlalchemy import select

        async with SessionLocal() as session:
            rows = (
                (
                    await session.execute(
                        select(ResearchTask.task_type)
                        .where(
                            ResearchTask.run_id == run_id,
                            ResearchTask.status == TaskStatus.pending,
                        )
                        .order_by(queue._stage_priority(), ResearchTask.created_at)
                    )
                )
                .scalars()
                .all()
            )
            return rows

    assert asyncio.run(ordered()) == ["research_professor", "research_one_professor"]

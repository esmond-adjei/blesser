import asyncio
import json

from fastapi.testclient import TestClient

from api.agent.tools import ToolContext, dispatch
from api.candidates import scoring
from api.core.config import settings
from api.core.db import SessionLocal
from api.prospects.models import Professor, Program, RunSchool, School
from api.runs import queue
from api.runs.models import ResearchTask, Run
from tests.conftest import TEST_USER_ID
from tests.grounding_helpers import ground


def _make_run_and_program():

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

    return asyncio.run(setup())


def test_spawn_queues_one_task_per_name(monkeypatch):
    from sqlalchemy import func, select

    assert "research_one_professor" in queue.TASK_HANDLERS

    monkeypatch.setattr(settings, "max_spawn_per_call", 3)
    run_id, program_id = _make_run_and_program()

    async def spawn():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            out = await dispatch(
                "spawn_professor_research",
                {"names": ["Ada", "  ada ", "", "Grace", "Edsger", "Alan"]},
                ctx,
            )
            rows = (
                (
                    await session.execute(
                        select(ResearchTask).where(
                            ResearchTask.run_id == run_id,
                            ResearchTask.task_type == "research_one_professor",
                        )
                    )
                )
                .scalars()
                .all()
            )
            queued = (
                await session.execute(
                    select(func.count())
                    .select_from(ResearchTask)
                    .where(
                        ResearchTask.run_id == run_id,
                        ResearchTask.task_type == "research_one_professor",
                    )
                )
            ).scalar()
            return out, rows, queued

    out, rows, queued = asyncio.run(spawn())
    assert out["queued"] == 3
    assert out["names"] == ["Ada", "Grace", "Edsger"]
    assert queued == 3
    assert {r.target_name for r in rows} == {"Ada", "Grace", "Edsger"}
    assert all(r.target_id == program_id for r in rows)


def test_spawn_needs_program_context():

    async def spawn():
        async with SessionLocal() as session:
            run = Run(user_id=TEST_USER_ID, 
                region="U",
                field="f",
                degree_level="phd",
                interest_statement="x",
                status="running",
            )
            session.add(run)
            await session.commit()
            ctx = ToolContext(session=session, run=run)
            return await dispatch("spawn_professor_research", {"names": ["Ada"]}, ctx)

    assert "error" in asyncio.run(spawn())


def _citing_professor(name="Prof Cite"):
    return {
        "name": name,
        "papers": [
            {"title": "Deep reinforcement learning for legged locomotion control"}
        ],
        "similarity_score": 0.9,
        "rationale": "Direct match to Deep reinforcement learning for legged locomotion control.",
    }


def test_verifier_rejects_uncited_rationale():
    from sqlalchemy import func, select

    run_id, program_id = _make_run_and_program()

    async def save():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            bad = dict(_citing_professor())
            bad["rationale"] = "Their general vibe in robotics seems aligned."
            out = await dispatch("save_professor_record", ground(ctx, bad), ctx)
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(Professor)
                    .where(Professor.program_id == program_id)
                )
            ).scalar()
            return out, count

    out, count = asyncio.run(save())
    assert "error" in out
    assert "cite" in out["error"]
    assert count == 0


def test_run_candidate_cap(monkeypatch):

    monkeypatch.setattr(settings, "max_candidates_per_run", 1)
    run_id, program_id = _make_run_and_program()

    async def save_two():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            first = await dispatch(
                "save_professor_record", ground(ctx, _citing_professor("One")), ctx
            )
            second = await dispatch(
                "save_professor_record", ground(ctx, _citing_professor("Two")), ctx
            )
            return first, second

    first, second = asyncio.run(save_two())
    assert "candidate_id" in first
    assert "error" in second
    assert "Run candidate budget" in second["error"]


def test_score_uses_cached_vector(monkeypatch):

    run_id, _ = _make_run_and_program()

    async def set_cache():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            run.interest_embedding = json.dumps([1.0, 0.0])
            await session.commit()

    asyncio.run(set_cache())

    calls = {"embed_texts": 0, "embed_and_score": 0}

    def fake_embed_texts(texts, **_):
        calls["embed_texts"] += 1
        return [[1.0, 0.0], [0.0, 1.0]][: len(texts)]

    def boom(*a, **k):
        calls["embed_and_score"] += 1
        raise AssertionError("must use cache, not full embed")

    monkeypatch.setattr(scoring, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(scoring, "embed_and_score", boom)

    async def score():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            ctx = ToolContext(session=session, run=run)
            return await dispatch(
                "score_alignment",
                {"interest_text": "ignored", "abstracts": ["a", "b"]},
                ctx,
            )

    out = asyncio.run(score())
    assert out["score"] == 1.0
    assert out["best_index"] == 0
    assert calls == {"embed_texts": 1, "embed_and_score": 0}


def test_score_falls_back_without_cache(monkeypatch):

    run_id, _ = _make_run_and_program()
    monkeypatch.setattr(scoring, "embed_texts", lambda texts, **_: None)

    async def score():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            ctx = ToolContext(session=session, run=run)
            return await dispatch(
                "score_alignment",
                {
                    "interest_text": "robotics navigation",
                    "abstracts": ["robotics nav paper"],
                },
                ctx,
            )

    out = asyncio.run(score())
    assert out["best_index"] == 0
    assert "all_scores" in out


def _client():
    from api.main import app

    return TestClient(app)


def test_from_list_skips_discovery():
    from sqlalchemy import func, select

    with _client() as client:
        created = client.post(
            "/api/runs/from-list",
            json={
                "degree_level": "phd",
                "interest_statement": "robots",
                "programs": [
                    {"school_name": "Uni A", "program_name": "PhD Robotics"},
                    {
                        "school_name": "Uni B",
                        "school_country": "Germany",
                        "program_name": "PhD AI",
                        "department_url": "https://example.edu/dept",
                    },
                ],
            },
        )
        assert created.status_code == 200, created.text
        run_id = created.json()["id"]

        tasks = client.get(f"/api/runs/{run_id}/tasks").json()
        types = [t["task_type"] for t in tasks]
        assert types == ["research_professor", "research_professor"]
        assert "discover_programs" not in types

        assert (
            client.post(
                "/api/runs/from-list",
                json={
                    "degree_level": "phd",
                    "interest_statement": "x",
                    "programs": [],
                },
            ).status_code
            == 400
        )

    async def counts():
        async with SessionLocal() as session:
            schools = (
                await session.execute(
                    select(func.count())
                    .select_from(RunSchool)
                    .where(RunSchool.run_id == run_id)
                )
            ).scalar()
            dept = (
                await session.execute(
                    select(Program)
                    .join(RunSchool, Program.school_id == RunSchool.school_id)
                    .where(
                        Program.name == "PhD AI",
                        RunSchool.run_id == run_id,
                    )
                )
            ).scalar_one()
            return schools, dept.department_url

    schools, dept_url = asyncio.run(counts())
    assert schools == 2
    assert dept_url == "https://example.edu/dept"


def test_seed_does_not_misassign_school_website():
    from sqlalchemy import select

    with _client() as client:
        created = client.post(
            "/api/runs/from-list",
            json={
                "degree_level": "phd",
                "interest_statement": "robots",
                "programs": [
                    {
                        # Unique: the suite's one account keeps one row per school.
                        "school_name": "Uni C Seed Website",
                        "program_name": "PhD Robotics",
                        "department_url": "https://example.edu/robotics-dept",
                    },
                ],
            },
        )
        assert created.status_code == 200, created.text
        run_id = created.json()["id"]

    async def fetch_school():
        async with SessionLocal() as session:
            result = await session.execute(
                select(School)
                .join(RunSchool, RunSchool.school_id == School.id)
                .where(RunSchool.run_id == run_id)
            )
            return result.scalar_one()

    school = asyncio.run(fetch_school())
    assert school.website_url is None

import asyncio

from fastapi.testclient import TestClient

from api.agent.tools import ToolContext, dispatch
from api.candidates.models import CandidateScore, CandidateStatus
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.outreach.models import EmailDraft
from api.prospects.models import Paper, Professor, Program, RunSchool, School
from api.runs.models import Run
from tests.conftest import TEST_USER_ID
from tests.grounding_helpers import ground


def _make_run():

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
            await session.commit()
            return run.id

    return asyncio.run(setup())


def _make_program(run_id):

    async def setup():
        async with SessionLocal() as session:
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run_id)], name="Test University")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="PhD in Robotics")
            session.add(program)
            await session.commit()
            return school.id, program.id

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


def test_save_program_budget_enforced(monkeypatch):
    from sqlalchemy import func, select

    monkeypatch.setattr(settings, "max_programs_per_task", 2)
    run_id = _make_run()

    async def run_saves():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            ctx = ToolContext(session=session, run=run)
            results = [
                await dispatch("save_program", _program_input(n), ctx) for n in range(3)
            ]
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(RunSchool)
                    .where(RunSchool.run_id == run_id)
                )
            ).scalar()
            return results, count, ctx.programs_saved

    results, count, saved = asyncio.run(run_saves())
    assert "program_id" in results[0]
    assert "program_id" in results[1]
    assert "error" in results[2]
    assert "Budget reached" in results[2]["error"]
    assert count == 2
    assert saved == 2


def test_budgets_are_per_task_not_per_run(monkeypatch):

    monkeypatch.setattr(settings, "max_programs_per_task", 1)
    run_id = _make_run()

    async def run_saves():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            first = ToolContext(session=session, run=run)
            assert await dispatch("save_program", _program_input(1), first)
            refused = await dispatch("save_program", _program_input(2), first)
            second = ToolContext(session=session, run=run)
            ok_again = await dispatch("save_program", _program_input(3), second)
            return refused, ok_again

    refused, ok_again = asyncio.run(run_saves())
    assert "error" in refused
    assert "program_id" in ok_again


def test_save_professor_budget_enforced(monkeypatch):
    from sqlalchemy import func, select

    monkeypatch.setattr(settings, "max_professors_per_task", 2)
    run_id = _make_run()
    _, program_id = _make_program(run_id)

    async def run_saves():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            results = [
                await dispatch("save_professor_record", ground(ctx, _professor_input(n)), ctx)
                for n in range(3)
            ]
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(Professor)
                    .where(Professor.program_id == program_id)
                )
            ).scalar()
            return results, count

    results, count = asyncio.run(run_saves())
    assert "candidate_id" in results[0]
    assert "candidate_id" in results[1]
    assert "error" in results[2]
    assert "Budget reached" in results[2]["error"]
    assert count == 2


def test_save_professor_record_stores_lab_and_bio():
    run_id = _make_run()
    _, program_id = _make_program(run_id)

    async def run_save():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            payload = _professor_input(7)
            payload["openalex_id"] = "https://openalex.example.edu/W7"
            payload["photo_url"] = "https://faculty.example.edu/rob.jpg"
            payload["lab_name"] = "Navigation Lab"
            payload["bio"] = "Roboticist working on navigation."
            payload["bio_source"] = "faculty"
            payload["socials"] = [
                {"label": "Scholar", "url": "https://scholar.example.edu/rob"},
                {"label": "Lab", "url": "https://lab.example.edu"},
            ]
            result = await dispatch("save_professor_record", ground(ctx, payload), ctx)
            assert "professor_id" in result
            stored = await session.get(Professor, result["professor_id"])
            assert stored is not None
            return stored, result["professor_id"]

    stored, professor_id = asyncio.run(run_save())
    assert stored.lab_name == "Navigation Lab"
    assert stored.bio == "Roboticist working on navigation."
    assert stored.bio_source == "faculty"
    assert stored.photo_url == "https://faculty.example.edu/rob.jpg"
    assert stored.socials == [
        {"label": "Scholar", "url": "https://scholar.example.edu/rob"},
        {"label": "Lab", "url": "https://lab.example.edu"},
    ]

    body = TestClient(app).get(f"/api/professors/{professor_id}").json()
    assert body["lab_name"] == "Navigation Lab"
    assert body["bio"] == "Roboticist working on navigation."
    assert body["bio_source"] == "faculty"
    assert body["photo_url"] == "https://faculty.example.edu/rob.jpg"
    assert body["socials"] == [
        {"label": "Scholar", "url": "https://scholar.example.edu/rob"},
        {"label": "Lab", "url": "https://lab.example.edu"},
    ]

    async def run_resave():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            repeat = _professor_input(7)
            repeat["openalex_id"] = "https://openalex.example.edu/W7"
            repeat["socials"] = [
                {"label": "Scholar Page", "url": "https://scholar.example.edu/rob"},
                {"label": "Site", "url": "https://site.example.edu"},
            ]
            result = await dispatch("save_professor_record", ground(ctx, repeat), ctx)
            assert result.get("deduped") is True
            stored = await session.get(Professor, result["professor_id"])
            assert stored is not None
            return stored.socials

    assert asyncio.run(run_resave()) == [
        {"label": "Scholar", "url": "https://scholar.example.edu/rob"},
        {"label": "Lab", "url": "https://lab.example.edu"},
        {"label": "Site", "url": "https://site.example.edu"},
    ]


def test_save_draft_budget_enforced(monkeypatch):
    from sqlalchemy import func, select

    monkeypatch.setattr(settings, "max_drafts_per_task", 1)
    run_id = _make_run()
    _, program_id = _make_program(run_id)

    async def setup_candidate():
        async with SessionLocal() as session:
            professor = Professor(user_id=TEST_USER_ID, program_id=program_id, name="Prof Draft")
            session.add(professor)
            await session.flush()
            session.add(
                Paper(
                    user_id=TEST_USER_ID,
                    professor_id=professor.id,
                    title="Mobile robot navigation in crowds",
                )
            )
            candidate = CandidateScore(user_id=TEST_USER_ID, 
                run_id=run_id,
                professor_id=professor.id,
                similarity_score=0.9,
                status=CandidateStatus.scored,
            )
            session.add(candidate)
            await session.commit()
            return candidate.id

    candidate_id = asyncio.run(setup_candidate())

    async def run_saves():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            ctx = ToolContext(session=session, run=run)
            first = await dispatch(
                "save_email_draft",
                {
                    "candidate_id": candidate_id,
                    "subject": "hi",
                    "body": "I read Mobile robot navigation in crowds.",
                },
                ctx,
            )
            second = await dispatch(
                "save_email_draft",
                {
                    "candidate_id": candidate_id,
                    "subject": "hi",
                    "body": "I read Mobile robot navigation in crowds.",
                },
                ctx,
            )
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(EmailDraft)
                    .where(EmailDraft.candidate_id == candidate_id)
                )
            ).scalar()
            return first, second, count

    first, second, count = asyncio.run(run_saves())
    assert first["status"] == "drafted"
    assert "error" in second
    assert "Budget reached" in second["error"]
    assert count == 1

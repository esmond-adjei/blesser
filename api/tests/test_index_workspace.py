import asyncio
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from api.agent.tools import ToolContext, dispatch
from api.candidates import service as candidate_service
from api.candidates.models import CandidateScore
from api.core.db import SessionLocal
from api.cv.models import CvDocument
from api.index import freshness, keys
from api.index import models as index_models
from api.prospects import optouts
from api.prospects.models import Paper, Program, RunSchool, School
from api.runs.models import Run
from api.workspace import models as workspace_models
from tests.conftest import TEST_USER_ID
from tests.grounding_helpers import ground

INTEREST = "Legged locomotion with deep reinforcement learning"


def _citing(name):
    return {
        "name": name,
        "papers": [{"title": "Deep reinforcement learning for legged locomotion control"}],
        "similarity_score": 0.9,
        "rationale": "Direct match to Deep reinforcement learning for legged locomotion control.",
    }


async def _run_at(session, school: School | None, school_name: str, program_name: str):
    run = Run(
        user_id=TEST_USER_ID, region="U", field="robotics", degree_level="phd",
        interest_statement=INTEREST, status="running",
    )
    session.add(run)
    await session.flush()
    if school is None:
        school = School(user_id=TEST_USER_ID, name=school_name)
        session.add(school)
        await session.flush()
    session.add(RunSchool(run_id=run.id, school_id=school.id))
    program = Program(user_id=TEST_USER_ID, school_id=school.id, name=program_name)
    session.add(program)
    await session.flush()
    return run, school, program


async def _save(session, run, program, name):
    ctx = ToolContext(session=session, run=run, program=program)
    return await dispatch("save_professor_record", ground(ctx, _citing(name)), ctx)


async def _count(session, model, *where):
    return (await session.execute(select(func.count()).select_from(model).where(*where))).scalar()


def test_two_runs_saving_one_person_make_one_person_and_one_match():
    async def go():
        async with SessionLocal() as session:
            run1, school, prog1 = await _run_at(session, None, "Index University", "PhD in Robots")
            first = await _save(session, run1, prog1, "Prof Index Twice")
            run2, _, prog2 = await _run_at(session, school, "", "PhD in Control")
            second = await _save(session, run2, prog2, "Prof Index Twice")
            assert "candidate_id" in first and "candidate_id" in second, (first, second)

            c1 = await session.get(CandidateScore, first["candidate_id"])
            c2 = await session.get(CandidateScore, second["candidate_id"])
            assert c1.match_id and c1.match_id == c2.match_id
            match = await session.get(workspace_models.Match, c1.match_id)
            person = await session.get(index_models.IndexProfessor, match.professor_id)
            assert person.name == "Prof Index Twice"
            places = (
                await session.execute(
                    select(index_models.Affiliation.program_id).where(
                        index_models.Affiliation.professor_id == person.id
                    )
                )
            ).scalars().all()
            assert set(places) == {prog1.id, prog2.id}
            doc = await session.get(CvDocument, match.interest_document_id)
            assert doc.kind == "interest" and doc.markdown == INTEREST
            assert run1.interest_document_id == run2.interest_document_id == doc.id
            assert await _count(session, workspace_models.MatchScore, workspace_models.MatchScore.match_id == match.id) == 2
            papers = await _count(
                session, index_models.PaperAuthor, index_models.PaperAuthor.professor_id == person.id
            )
            assert papers == 1
            assert await _count(session, workspace_models.MatchEvidence, workspace_models.MatchEvidence.match_id == match.id) == 1
            legacy = (await session.execute(select(Paper).where(Paper.professor_id == c1.professor_id))).scalar_one()
            assert legacy.index_paper_id is not None
            return c2.id, match.id

    candidate_id, match_id = asyncio.run(go())

    async def review():
        async with SessionLocal() as session:
            await candidate_service.review_candidate(session, TEST_USER_ID, candidate_id, approved=False)
            match = await session.get(workspace_models.Match, match_id)
            return match.status

    assert asyncio.run(review()) == "passed"


def test_an_opt_out_removes_the_person_and_their_matches():
    async def go():
        async with SessionLocal() as session:
            run, _, program = await _run_at(session, None, "Optout Index University", "PhD in Leaving")
            saved = await _save(session, run, program, "Prof Index Leaves")
            match_id = (await session.get(CandidateScore, saved["candidate_id"])).match_id
            assert match_id
            counts = await optouts.remove_person(
                session, name="Prof Index Leaves", school="Optout Index University", note="test"
            )
            await session.commit()
            assert counts["index_professors"] == 1
            return await session.get(workspace_models.Match, match_id)

    assert asyncio.run(go()) is None


def test_works_are_keyed_by_doi_then_openalex_then_title():
    assert keys.work_key(title="X", url="https://doi.org/10.1000/ABC.1") == "doi:10.1000/abc.1"
    assert keys.work_key(title="X", url="https://openalex.org/W123") == "openalex:W123"
    assert keys.work_key(title="On <i>Guarding</i>!", year=2024) == "title:on guarding|2024"
    assert keys.person_key("Prof. Ada Lovelace, PhD") == "ada lovelace"


def test_freshness_defaults():
    now = datetime(2026, 10, 24, tzinfo=UTC).replace(tzinfo=None)
    assert not freshness.is_stale("faculty", now - timedelta(days=29), now=now)
    assert freshness.is_stale("faculty", now - timedelta(days=31), now=now)
    assert not freshness.is_stale("programme", now - timedelta(days=300), now=now)
    assert freshness.is_stale("bio", now - timedelta(days=181), now=now)
    assert freshness.is_stale("works", None, now=now)
    # A cycle is re-checked weekly once its deadline is within 60 days.
    eight_days = now - timedelta(days=8)
    assert not freshness.is_stale("cycle", eight_days, deadline=date(2027, 6, 1), now=now)
    assert freshness.is_stale("cycle", eight_days, deadline=date(2026, 12, 1), now=now)

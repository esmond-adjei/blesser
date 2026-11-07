import asyncio

from api.agent.tools import ToolContext, dispatch
from api.core.db import SessionLocal
from api.prospects import openalex, ranking
from api.prospects.models import Program, RunSchool, School
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID

PAGE = ["Alice Smith", "Bob Jones", "Chen Lee", "Dana Kim"]
AUTHORS = [
    {"openalex_id": "A3", "name": "C. Lee", "works": 9},
    {"openalex_id": "A2", "name": "Jones, Bob", "works": 3},
    {"openalex_id": "A9", "name": "Visiting Coauthor", "works": 12},  # not faculty
]


def test_topic_query_keeps_content_words():
    q = ranking.topic_query("I want to do a PhD in robot learning for dexterous manipulation in Canada")
    assert q == "robot learning dexterous manipulation"


def test_topic_query_keeps_two_letter_acronyms():
    q = ranking.topic_query("I am into AI and ML for RL agents, so if I do CV")
    assert q == "ai ml rl agents cv"


def test_names_rank_by_topical_works_then_page_order():
    ranked, matched = ranking.rank_names(PAGE, AUTHORS)
    assert ranked == ["Chen Lee", "Bob Jones", "Alice Smith", "Dana Kim"]
    assert matched == 2


def test_accents_and_honorifics_still_match():
    ranked, matched = ranking.rank_names(
        ["Prof. Dr. José García, PhD", "Ann Other"], [{"name": "Jose Garcia", "works": 2}]
    )
    assert ranked[0].startswith("Prof. Dr. José") and matched == 1


def test_authors_query_shape(monkeypatch):
    seen = {}

    async def fake(path, params):
        seen.update(path=path, **params)
        return {"group_by": [
            {"key": "https://openalex.org/A1", "key_display_name": "A One", "count": 2},
            {"key": "https://openalex.org/A2", "key_display_name": "B Two", "count": 7},
        ]}  # fmt: skip

    monkeypatch.setattr(openalex, "_get_json", fake)
    out = asyncio.run(openalex.authors_publishing_on("I63966007", "robot learning"))
    assert seen["path"] == "/works" and seen["group_by"] == "authorships.author.id"
    assert seen["filter"].startswith("institutions.id:I63966007,from_publication_date:")
    assert [a["openalex_id"] for a in out] == ["A2", "A1"]


def _program(institution_id):
    async def go():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID, region="U", field="f", degree_level="phd",
                interest_statement="robot learning for manipulation", status="running",
                max_professors_per_program=2,
            )  # fmt: skip
            session.add(run)
            await session.flush()
            school = School(
                user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run.id)], name="Test University",
                openalex_institution_id=institution_id, institution_names="[]",
            )  # fmt: skip
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="Robotics")
            session.add(program)
            await session.commit()
            return run.id, program.id

    return asyncio.run(go())


def _spawn(run_id, program_id):
    async def go():
        async with SessionLocal() as session:
            ctx = ToolContext(
                session=session, run=await session.get(Run, run_id),
                program=await session.get(Program, program_id),
            )  # fmt: skip
            out = await dispatch("spawn_professor_research", {"names": PAGE}, ctx)
            from sqlalchemy import select

            started = (
                await session.execute(
                    select(ResearchTask.target_name)
                    .where(ResearchTask.run_id == run_id, ResearchTask.status == TaskStatus.pending)
                    .order_by(ResearchTask.created_at)
                )
            ).scalars().all()
            return out, list(started)

    return asyncio.run(go())


def test_spawn_researches_the_topical_faculty_first(monkeypatch):
    async def authors(institution_id, query, **_):
        assert institution_id == "I1" and "robot" in query
        return AUTHORS

    monkeypatch.setattr(openalex, "authors_publishing_on", authors)
    run_id, program_id = _program("I1")
    out, started = _spawn(run_id, program_id)
    assert out["ranked_by_topic"] is True
    assert out["names"] == ["Chen Lee", "Bob Jones", "Alice Smith", "Dana Kim"]
    assert started == ["Chen Lee", "Bob Jones"]  # the per-programme share of 2


def test_spawn_keeps_page_order_without_openalex(monkeypatch):
    async def down(institution_id, query, **_):
        raise openalex.OpenAlexUnavailable("OpenAlex is unavailable right now (HTTP 503).")

    monkeypatch.setattr(openalex, "authors_publishing_on", down)
    run_id, program_id = _program("I1")
    out, started = _spawn(run_id, program_id)
    assert out["ranked_by_topic"] is False
    assert started == ["Alice Smith", "Bob Jones"]
    run_id, program_id = _program(None)
    out, _ = _spawn(run_id, program_id)
    assert out["ranked_by_topic"] is False

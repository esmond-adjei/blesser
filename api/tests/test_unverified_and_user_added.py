import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api.agent.tools import ToolContext, dispatch
from api.candidates import scoring
from api.candidates.models import CandidateScore
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.prospects import openalex
from api.prospects import tasks as prospect_tasks
from api.prospects.models import Professor, Program
from api.prospects.prompts import INDEX_APPLICATION_MARKER
from api.runs.models import ResearchTask, Run
from tests.test_budgets import _make_program, _make_run

WORK = {"title": "Learning to walk on rough terrain", "abstract": "Legged robots.", "year": 2024, "url": None}


def _ctx_ids():
    run_id = _make_run()
    _, program_id = _make_program(run_id)
    return run_id, program_id


async def _ctx(session, run_id, program_id):
    return ToolContext(
        session=session,
        run=await session.get(Run, run_id),
        program=await session.get(Program, program_id),
    )


def _save_unverified(monkeypatch, find, works=None, openalex_id=None):
    monkeypatch.setattr(openalex, "find_author", find)
    if works is not None:
        monkeypatch.setattr(openalex, "get_recent_works", works)
    run_id, program_id = _ctx_ids()

    async def go():
        async with SessionLocal() as session:
            ctx = await _ctx(session, run_id, program_id)
            await dispatch("find_openalex_author", {"name": "Ada Walker"}, ctx)
            if works is not None:
                await dispatch("get_author_works", {"openalex_id": openalex_id}, ctx)
            saved = await dispatch(
                "save_professor_record",
                {
                    "name": "Ada Walker",
                    "openalex_id": openalex_id,
                    "unverified": True,
                    "rationale": "Listed on the faculty page; OpenAlex has no record.",
                },
                ctx,
            )
            row = None
            if "candidate_id" in saved:
                row = await session.get(CandidateScore, saved["candidate_id"])
            return saved, row

    return asyncio.run(go())


def test_not_on_openalex_is_saved_unverified(monkeypatch):
    async def nobody(name, hint=None, **_):
        return []

    saved, row = _save_unverified(monkeypatch, nobody)
    assert "candidate_id" in saved, saved
    assert row.similarity_score is None
    assert row.rationale.startswith("Unverified: Listed on the faculty page")


def test_outage_allows_an_unverified_save(monkeypatch):
    async def down(name, hint=None, **_):
        raise openalex.OpenAlexUnavailable("OpenAlex is unavailable right now (HTTP 503).")

    saved, _ = _save_unverified(monkeypatch, down)
    assert "candidate_id" in saved, saved


def test_author_with_no_works_is_saved_unverified(monkeypatch):
    async def found(name, hint=None, **_):
        return [{"openalex_id": "A5", "display_name": name, "institution": "Test University"}]

    async def none(openalex_id, limit=10):
        return []

    saved, _ = _save_unverified(monkeypatch, found, works=none, openalex_id="A5")
    assert "candidate_id" in saved, saved


def test_unverified_is_refused_when_openalex_found_them(monkeypatch):
    async def found(name, hint=None, **_):
        return [{"openalex_id": "A5", "display_name": name, "institution": "Test University"}]

    saved, _ = _save_unverified(monkeypatch, found)
    assert "unverified is only for professors OpenAlex can't confirm" in saved["error"]
    assert saved["gate"] != "other"


@pytest.mark.parametrize("code_first", [False, pytest.param(True, marks=pytest.mark.pipeline)])
def test_user_added_professor_is_researched_past_the_cap_into_their_row(monkeypatch, code_first):
    # With the code-first pass, a low score would conclude "not a match" without the model; a student's pick always gets the agent.
    if code_first:

        async def find(name, hint=None, **_):
            return [{"openalex_id": "A9", "display_name": name, "institution": "Test University"}]

        monkeypatch.setattr(openalex, "find_author", find)
    run_id, program_id = _ctx_ids()

    async def fill_cap():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            run.max_professors = 1
            prof = Professor(user_id=run.user_id, program_id=program_id, name="Someone Else")
            session.add(prof)
            await session.flush()
            session.add(CandidateScore(run_id=run_id, user_id=run.user_id, professor_id=prof.id, similarity_score=0.5, rationale="r"))
            await session.commit()

    asyncio.run(fill_cap())
    client = TestClient(app)
    resp = client.post(f"/api/programs/{program_id}/professors", json={"name": "Ada Walker", "openalex_id": "A9"})
    assert resp.status_code in (200, 201), resp.text

    seen = {}

    async def fake_agent(system_prompt, user_message, ctx, **kwargs):
        if user_message.startswith(INDEX_APPLICATION_MARKER):
            return {"final_text": "", "tool_log": [], "turns": 0, "usage": {}, "nudges": 0}
        seen["message"] = user_message
        seen["user_added"] = ctx.user_added
        seen["candidates"] = dict(ctx.author_candidates)
        await dispatch("get_author_works", {"openalex_id": "A9"}, ctx)
        scored = await dispatch("score_alignment", {"openalex_id": "A9"}, ctx)
        seen["saved"] = await dispatch(
            "save_professor_record",
            {
                "name": "Ada Walker",
                "openalex_id": "A9",
                "papers": [{"title": WORK["title"]}],
                "similarity_score": scored["score"],
                "rationale": f"{WORK['title']} is close to the student's interest.",
            },
            ctx,
        )
        return {"final_text": "saved", "tool_log": [], "turns": 3, "usage": {}, "nudges": 0}

    async def works(openalex_id, limit=10, **_):
        return [WORK]

    async def score(ctx, interest_text, texts):
        return {"score": 0.12, "best_index": 0, "all_scores": [0.12], "method": "embedding"}

    monkeypatch.setattr(prospect_tasks, "run_agent_task", fake_agent)
    monkeypatch.setattr(openalex, "get_recent_works", works)
    monkeypatch.setattr(scoring, "score_interest_for_ctx_async", score)

    async def go():
        async with SessionLocal() as session:
            task = (
                await session.execute(
                    select(ResearchTask).where(ResearchTask.run_id == run_id, ResearchTask.target_name == "Ada Walker")
                )
            ).scalar_one()
            run = await session.get(Run, run_id)
            out = await prospect_tasks.run_research_one_professor(session, task, run)
            rows = (
                await session.execute(
                    select(func.count()).select_from(Professor).where(Professor.program_id == program_id, Professor.name == "Ada Walker")
                )
            ).scalar()
            return out, rows

    out, rows = asyncio.run(go())
    assert not out["final_text"].startswith("Skipped"), out
    assert seen["user_added"] is True
    assert "added this professor themselves" in seen["message"] and "A9" in seen["message"]
    assert "A9" in seen["candidates"]
    assert "candidate_id" in seen["saved"], seen["saved"]  # past the cap of 1, low score
    assert rows == 1


def test_user_added_professors_have_their_own_allowance(monkeypatch):
    monkeypatch.setattr(settings, "max_user_professors_per_run", 1)
    _, program_id = _ctx_ids()
    client = TestClient(app)
    assert client.post(f"/api/programs/{program_id}/professors", json={"name": "First Person"}).status_code in (200, 201)
    second = client.post(f"/api/programs/{program_id}/professors", json={"name": "Second Person"})
    assert second.status_code == 400
    assert "still waiting to be researched" in second.json()["detail"]


@pytest.mark.parametrize("text", ["save the professor with unverified: true"])
def test_outage_message_matches_the_save_path(text):
    import inspect

    assert text in inspect.getsource(openalex)


@pytest.mark.pipeline
def test_outage_in_the_code_first_pass_allows_an_unverified_save(monkeypatch):
    from api.prospects import pipeline
    from api.prospects.models import School

    async def found(name, hint=None, **_):
        return [{"openalex_id": "A7", "display_name": name, "institution": "Test University"}]

    async def down(openalex_id, limit=15, **_):
        raise openalex.OpenAlexUnavailable("OpenAlex is unavailable right now (HTTP 503).")

    monkeypatch.setattr(openalex, "find_author", found)
    monkeypatch.setattr(openalex, "get_recent_works", down)
    run_id, program_id = _ctx_ids()

    async def go():
        async with SessionLocal() as session:
            ctx = await _ctx(session, run_id, program_id)
            school = await session.get(School, ctx.program.school_id)
            decision = await pipeline.first_pass(ctx, school, "Ada Walker")
            saved = await dispatch(
                "save_professor_record",
                {
                    "name": "Ada Walker",
                    "openalex_id": "A7",
                    "unverified": True,
                    "rationale": "On the faculty page; OpenAlex was down when checked.",
                },
                ctx,
            )
            return decision, saved

    decision, saved = asyncio.run(go())
    assert decision.outcome == "agent"
    assert "candidate_id" in saved, saved

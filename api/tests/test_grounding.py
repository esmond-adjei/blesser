import asyncio

import pytest

from api.agent.tools import ToolContext, dispatch
from api.candidates import scoring
from api.candidates.models import CandidateScore
from api.core.db import SessionLocal
from api.prospects import openalex
from api.prospects.models import Paper, Program
from api.runs.models import Run
from tests.test_budgets import _make_program, _make_run

AUTHOR = "https://openalex.org/A1"
WORKS = [
    {
        "title": "Legged locomotion with deep reinforcement learning",
        "abstract": "We train quadruped controllers in simulation.",
        "year": 2024,
        "publication_type": "conference-paper",
        "url": "https://doi.org/x",
    },
    {
        "title": "Terrain-aware planning for walking robots",
        "abstract": "A planner for rough terrain.",
        "year": 2023,
        "url": None,
    },
]
TOOL_SCORE = 0.8043


@pytest.fixture
def research(monkeypatch):
    async def find_author(name, hint=None):
        return [
            {
                "openalex_id": AUTHOR,
                "display_name": name,
                "institution": "Test University",
            },
            {
                "openalex_id": "https://openalex.org/A2",
                "display_name": name,
                "institution": "Elsewhere College",
            },
        ]

    async def works(openalex_id, limit=10):
        return WORKS if openalex_id == AUTHOR else []

    async def score(ctx, interest_text, abstracts):
        return {"score": TOOL_SCORE, "best_index": 0, "all_scores": [TOOL_SCORE]}

    monkeypatch.setattr(openalex, "find_author", find_author)
    monkeypatch.setattr(openalex, "get_recent_works", works)
    monkeypatch.setattr(scoring, "score_interest_for_ctx_async", score)


def _save_input(**overrides):
    payload = {
        "name": "Ada Walker",
        "openalex_id": AUTHOR,
        "papers": [{"title": WORKS[0]["title"]}],
        "similarity_score": 0.8,
        "rationale": f"Her paper {WORKS[0]['title']} matches the interest directly.",
    }
    payload.update(overrides)
    return payload


def _run_sequence(save_payload, *, find=True, fetch=True, score_texts=None):
    run_id = _make_run()
    _, program_id = _make_program(run_id)

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            if find:
                await dispatch("find_openalex_author", {"name": "Ada Walker"}, ctx)
            if fetch:
                await dispatch("get_author_works", {"openalex_id": AUTHOR}, ctx)
            texts = (
                score_texts
                if score_texts is not None
                else [w["abstract"] for w in WORKS]
            )
            await dispatch(
                "score_alignment",
                {"interest_text": "legged robots", "abstracts": texts},
                ctx,
            )
            result = await dispatch("save_professor_record", save_payload, ctx)
            stored = None
            if "candidate_id" in result:
                cand = await session.get(CandidateScore, result["candidate_id"])
                papers = (
                    await session.execute(
                        Paper.__table__.select().where(
                            Paper.professor_id == result["professor_id"]
                        )
                    )
                ).all()
                stored = (
                    cand.similarity_score,
                    [(p.title, p.abstract, p.year, p.publication_type) for p in papers],
                )
            return result, stored

    return asyncio.run(go())


def test_grounded_save_stores_tool_values(research):
    result, stored = _run_sequence(_save_input())
    assert "candidate_id" in result, result
    score, papers = stored
    assert score == TOOL_SCORE  # the tool's value, not the model's 0.8
    assert papers == [(WORKS[0]["title"], WORKS[0]["abstract"], 2024, "conference-paper")]


def test_invented_paper_is_refused(research):
    invented = "Quantum gravity for household robots"
    result, _ = _run_sequence(
        _save_input(
            papers=[{"title": invented}],
            rationale=f"Her paper {invented} matches directly.",
        )
    )
    assert "not returned by get_author_works" in result["error"]


def test_uncomputed_score_is_refused(research):
    result, _ = _run_sequence(_save_input(similarity_score=0.99))
    assert "score_alignment" in result["error"]


def test_score_over_made_up_abstracts_is_refused(research):
    result, _ = _run_sequence(
        _save_input(), score_texts=["An abstract the model wrote to match perfectly."]
    )
    assert "score_alignment" in result["error"]


def test_out_of_range_score_is_refused(research):
    result, _ = _run_sequence(_save_input(similarity_score=1.7))
    assert "0-1" in result["error"]


def test_openalex_id_must_come_from_find_author(research):
    result, _ = _run_sequence(_save_input(), find=False)
    assert "find_openalex_author" in result["error"]


def test_works_must_have_been_fetched(research):
    result, _ = _run_sequence(_save_input(), fetch=False)
    assert "get_author_works" in result["error"]


def test_institution_must_match_the_school(research):
    result, _ = _run_sequence(_save_input(openalex_id="https://openalex.org/A2"))
    assert "Elsewhere College" in result["error"]

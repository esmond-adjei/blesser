import asyncio
import json

from fastapi.testclient import TestClient

from api.agent.tools import ToolContext, dispatch
from api.candidates import scoring
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.prospects import prompts
from api.prospects.models import Program
from api.runs.models import ResearchTask, Run, TaskStatus, ToolCallLog
from tests.conftest import TEST_USER_ID
from tests.test_fewer_turns import AUTHOR, _ctx_run, _research


def test_bands_per_method():
    assert scoring.score_band(0.52, "embedding") == "strong"
    assert scoring.score_band(0.33, "embedding") == "moderate"
    assert scoring.score_band(0.2, "embedding") == "weak"
    assert scoring.score_band(0.05, "embedding") == "unrelated"
    # Word overlap: 0 means no shared words, not unrelated work.
    assert scoring.score_band(0.0, "lexical") == "no_overlap"
    assert scoring.score_band(0.3, "lexical") == "strong"


def test_scores_say_how_they_were_computed(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "local")
    out = scoring.embed_and_score("graph neural networks", ["message passing on graphs"])
    assert out["method"] == "lexical"
    from api.candidates.scoring import get_embedding_info

    assert get_embedding_info()["scoring_method"] == "lexical"


def test_weak_grounded_match_is_scored_flagged_and_saved(monkeypatch):
    _research(monkeypatch)

    async def weak(ctx, interest_text, texts):
        return {"score": 0.21, "best_index": 0, "all_scores": [0.21, 0.12], "method": "embedding"}

    monkeypatch.setattr(scoring, "score_interest_for_ctx_async", weak)
    run_id, program_id = _ctx_run()

    async def go():
        async with SessionLocal() as session:
            ctx = ToolContext(
                session=session,
                run=await session.get(Run, run_id),
                program=await session.get(Program, program_id),
            )
            await dispatch("find_openalex_author", {"name": "Ada Walker"}, ctx)
            await dispatch("get_author_works", {"openalex_id": "A1"}, ctx)
            scored = await dispatch("score_alignment", {"openalex_id": AUTHOR}, ctx)
            best = scored["top_works"][0]["title"]
            saved = await dispatch(
                "save_professor_record",
                {
                    "name": "Ada Walker",
                    "openalex_id": "A1",
                    "papers": [{"title": best}],
                    "similarity_score": scored["score"],
                    "rationale": f"Only {best} overlaps with the interest; the rest is elsewhere.",
                },
                ctx,
            )
            return scored, saved

    scored, saved = asyncio.run(go())
    assert scored["band"] == "weak" and scored["method"] == "embedding"
    assert "note" not in scored
    assert "candidate_id" in saved, saved


def test_lexical_score_carries_a_warning(monkeypatch):
    _research(monkeypatch)

    async def lexical(ctx, interest_text, texts):
        return {"score": 0.0, "best_index": 0, "all_scores": [0.0, 0.0], "method": "lexical"}

    monkeypatch.setattr(scoring, "score_interest_for_ctx_async", lexical)
    run_id, program_id = _ctx_run()

    async def go():
        async with SessionLocal() as session:
            ctx = ToolContext(
                session=session,
                run=await session.get(Run, run_id),
                program=await session.get(Program, program_id),
            )
            await dispatch("find_openalex_author", {"name": "Ada Walker"}, ctx)
            await dispatch("get_author_works", {"openalex_id": "A1"}, ctx)
            return await dispatch("score_alignment", {"openalex_id": AUTHOR}, ctx)

    scored = asyncio.run(go())
    assert scored["band"] == "no_overlap"
    assert "never conclude no match from this score alone" in scored["note"]


def test_prompt_saves_weak_matches_and_guards_lexical():
    text = prompts.RESEARCH_ONE_PROFESSOR_SYSTEM_PROMPT
    assert 'unless score_alignment\'s band is\n   "unrelated"' in text
    assert "never\n   conclude no match from that score alone" in text


def test_run_summary_counts_lexical_scores():
    async def seed():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID, region="U", field="f", degree_level="phd",
                interest_statement="x", status="done",
            )  # fmt: skip
            session.add(run)
            await session.flush()
            task = ResearchTask(
                run_id=run.id, user_id=TEST_USER_ID, task_type="research_one_professor",
                status=TaskStatus.done,
            )  # fmt: skip
            session.add(task)
            await session.flush()
            for method in ("lexical", "lexical", "embedding"):
                session.add(
                    ToolCallLog(
                        task_id=task.id, user_id=TEST_USER_ID, turn=1, tool_name="score_alignment",
                        ok=True, input_json="{}", result_json=json.dumps({"score": 0.1, "method": method}),
                    )
                )  # fmt: skip
            await session.commit()
            return run.id

    run_id = asyncio.run(seed())
    body = TestClient(app).get(f"/api/runs/{run_id}/refusals").json()
    assert body["lexical_scores"] == 2

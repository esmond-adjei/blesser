import asyncio

import pytest
from sqlalchemy import func, select

from api.agent.llm.base import LLMResponse, ToolCall
from api.applications.models import Application
from api.candidates import scoring
from api.candidates.models import CandidateScore
from api.core.db import SessionLocal
from api.prospects import openalex
from api.prospects import tasks as prospect_tasks
from api.prospects.models import Program, RunSchool, School
from api.prospects.prompts import SAVE_ONE_PROFESSOR_SYSTEM_PROMPT
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID

pytestmark = pytest.mark.pipeline

NAMES = [f"Prof Person{i:02d}" for i in range(20)]
# Even-numbered professors work on the student's topic, odd ones don't.
SCORES = {n: (0.62 if i % 2 == 0 else 0.05) for i, n in enumerate(NAMES)}


def _author_id(name: str) -> str:
    return "A" + name[-2:]


def _setup():
    async def go():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID, region="U", field="robotics", degree_level="phd",
                interest_statement="robot learning", status="running", max_professors=100,
            )  # fmt: skip
            session.add(run)
            await session.flush()
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run.id)], name="Test University")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="Robotics")
            session.add(program)
            await session.flush()
            # Admissions are already indexed, so no task here takes the agent path for that.
            session.add(Application(user_id=TEST_USER_ID, run_id=run.id, school="Test University"))
            session.add(
                ResearchTask(
                    run_id=run.id, user_id=TEST_USER_ID, task_type="research_one_professor",
                    target_id=program.id, target_name="Earlier Task", status=TaskStatus.done,
                )
            )  # fmt: skip
            await session.flush()
            tasks = []
            for name in NAMES:
                task = ResearchTask(
                    run_id=run.id, user_id=TEST_USER_ID, task_type="research_one_professor",
                    target_id=program.id, target_name=name, status=TaskStatus.running,
                )  # fmt: skip
                session.add(task)
                await session.flush()
                tasks.append(task.id)
            await session.commit()
            return run.id, program.id, tasks

    return asyncio.run(go())


def _openalex(monkeypatch, at_school=1):
    async def find_author(name, hint=None, **_):
        return [
            {"openalex_id": _author_id(name), "display_name": name, "institution": "Test University"}
            for _ in range(at_school)
        ] if at_school < 2 else [
            {"openalex_id": f"{_author_id(name)}{k}", "display_name": name, "institution": "Test University"}
            for k in range(at_school)
        ]  # fmt: skip

    async def works(author_id, limit=15, years=None):
        assert limit == 50 and years == 5
        return [
            {"title": f"Work {k} of {author_id}", "abstract": f"Abstract {k}.", "year": 2024, "url": None}
            for k in range(3)
        ]  # fmt: skip

    async def score(ctx, interest, texts):
        author = next(iter(ctx.works_by_author))  # one author per task here
        name = next(n for n in NAMES if _author_id(n) == author)
        s = SCORES[name]
        return {"score": s, "best_index": 0, "all_scores": [s, s / 2, s / 3], "method": "embedding"}

    monkeypatch.setattr(openalex, "find_author", find_author)
    monkeypatch.setattr(openalex, "get_recent_works", works)
    monkeypatch.setattr(scoring, "score_interest_for_ctx_async", score)


class SaveModel:
    """Plays the one-call step: cite the first listed work and save."""

    def __init__(self):
        self.calls = []

    async def chat(self, messages, system, tools, max_tokens=4096):
        self.calls.append(system)
        brief = messages[0]["content"]
        name = brief.split("Professor: ", 1)[1].split("\n", 1)[0]
        author = brief.split("OpenAlex author: ", 1)[1].split(" ", 1)[0]
        score = float(brief.split("similarity_score ", 1)[1].split(" ", 1)[0])
        title = brief.split('- "', 1)[1].split('"', 1)[0]
        return LLMResponse(
            text="",
            tool_calls=[
                ToolCall(
                    id="s1",
                    name="save_professor_record",
                    arguments={
                        "name": name,
                        "openalex_id": author,
                        "papers": [{"title": title}],
                        "similarity_score": score,
                        "rationale": f"{title} is directly on the student's topic.",
                    },
                )
            ],
        )


def _run_all(monkeypatch, model):
    import api.agent.orchestrator as orch

    monkeypatch.setattr(orch, "get_provider", lambda **_: model)
    run_id, _program_id, task_ids = _setup()

    async def go():
        outcomes = []
        for task_id in task_ids:
            async with SessionLocal() as session:
                task = await session.get(ResearchTask, task_id)
                run = await session.get(Run, run_id)
                outcomes.append(await prospect_tasks.run_research_one_professor(session, task, run))
        async with SessionLocal() as session:
            saved = (
                await session.execute(
                    select(func.count()).select_from(CandidateScore).where(CandidateScore.run_id == run_id)
                )
            ).scalar()
        return outcomes, saved

    return asyncio.run(go())


def test_twenty_professors_with_model_calls_only_for_likely_matches(monkeypatch):
    _openalex(monkeypatch)
    model = SaveModel()
    outcomes, saved = _run_all(monkeypatch, model)
    assert len(model.calls) == 10
    assert all(system.startswith(SAVE_ONE_PROFESSOR_SYSTEM_PROMPT[:40]) for system in model.calls)
    assert saved == 10
    unrelated = [o for o in outcomes if o["final_text"].startswith("Researched")]
    assert len(unrelated) == 10 and all(o["turns"] == 0 for o in unrelated)
    assert all("unrelated to the student's interest" in o["final_text"] for o in unrelated)


def test_ambiguous_names_go_to_the_agent(monkeypatch):
    _openalex(monkeypatch, at_school=2)
    seen = []

    async def fake_agent(system_prompt, user_message, ctx, **kwargs):
        seen.append((system_prompt, user_message, set(ctx.author_candidates)))
        return {"final_text": "agent", "tool_log": [], "turns": 1, "usage": {}, "nudges": 0}

    monkeypatch.setattr(prospect_tasks, "run_agent_task", fake_agent)
    run_id, _program_id, task_ids = _setup()

    async def go():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_ids[0])
            run = await session.get(Run, run_id)
            return await prospect_tasks.run_research_one_professor(session, task, run)

    out = asyncio.run(go())
    assert out["final_text"] == "agent"
    system, message, candidates = seen[0]
    assert "researching exactly ONE professor" in system
    assert "2 authors at the school" in message
    assert len(candidates) == 2


def test_a_refused_save_gets_one_repair_turn(monkeypatch):
    _openalex(monkeypatch)

    class RepairModel(SaveModel):
        async def chat(self, messages, system, tools, max_tokens=4096):
            response = await super().chat(messages, system, tools, max_tokens)
            if len(self.calls) == 1:
                # First try paraphrases instead of citing: the citation check refuses it.
                response.tool_calls[0].arguments["rationale"] = "Their work broadly fits."
            else:
                assert "Rationale does not cite" in str(messages[-1]["content"])
            return response

    model = RepairModel()
    import api.agent.orchestrator as orch

    monkeypatch.setattr(orch, "get_provider", lambda **_: model)
    run_id, _program_id, task_ids = _setup()

    async def go():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_ids[0])  # an even, likely match
            run = await session.get(Run, run_id)
            out = await prospect_tasks.run_research_one_professor(session, task, run)
            saved = (
                await session.execute(
                    select(func.count()).select_from(CandidateScore).where(CandidateScore.run_id == run_id)
                )
            ).scalar()
            return out, saved

    out, saved = asyncio.run(go())
    assert len(model.calls) == 2 and saved == 1
    assert out["turns"] == 2


def test_a_refused_no_match_falls_through_to_the_agent(monkeypatch):
    from api.prospects import pipeline

    _openalex(monkeypatch)
    real_dispatch = pipeline.dispatch

    async def dispatch(tool, tool_input, ctx):
        if tool == "confirm_no_match":
            return {"error": "Refused: test"}
        return await real_dispatch(tool, tool_input, ctx)

    seen = []

    async def fake_agent(system_prompt, user_message, ctx, **kwargs):
        seen.append(user_message)
        return {"final_text": "agent", "tool_log": [], "turns": 1, "usage": {}, "nudges": 0}

    monkeypatch.setattr(pipeline, "dispatch", dispatch)
    monkeypatch.setattr(prospect_tasks, "run_agent_task", fake_agent)
    run_id, _program_id, task_ids = _setup()

    async def go():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_ids[1])  # an odd, unrelated one
            run = await session.get(Run, run_id)
            return await prospect_tasks.run_research_one_professor(session, task, run)

    out = asyncio.run(go())
    assert out["final_text"] == "agent"
    assert "no-match not recorded: Refused: test" in seen[0]


def test_five_years_back_from_a_leap_day():
    from datetime import date

    assert openalex.years_before(date(2028, 2, 29), 5) == date(2023, 2, 28)
    assert openalex.years_before(date(2028, 2, 29), 4) == date(2024, 2, 29)
    assert openalex.years_before(date(2026, 10, 16), 5) == date(2021, 10, 16)


def test_jev_picks_between_same_name_authors_so_no_agent_is_needed(monkeypatch):
    from api.candidates import verification
    from api.core.config import settings

    _openalex(monkeypatch, at_school=2)

    async def score(ctx, interest, texts):
        return {"score": 0.62, "best_index": 0, "all_scores": [0.62, 0.3, 0.2], "method": "embedding"}

    async def ask(state, question):
        return type("Answer", (), {"choice": "author_1", "confidence": 0.95})()

    monkeypatch.setattr(scoring, "score_interest_for_ctx_async", score)
    monkeypatch.setattr(settings, "typesafe_author_pick", True)
    monkeypatch.setattr(settings, "typesafe_api_key", "test-key")
    monkeypatch.setattr(verification, "_ask", ask)
    model = SaveModel()
    _outcomes, saved = _run_all(monkeypatch, model)
    # Every professor took the one-call save, none the full agent loop.
    assert saved == 20 and len(model.calls) == 20
    assert all(system.startswith(SAVE_ONE_PROFESSOR_SYSTEM_PROMPT[:40]) for system in model.calls)


def test_a_confident_fit_keeps_a_professor_the_similarity_would_drop(monkeypatch):
    from api.candidates import verification
    from api.core.config import settings

    _openalex(monkeypatch)

    async def ask(state, question):
        return type("Answer", (), {"score": 3.0, "confidence": 0.9})()

    monkeypatch.setattr(settings, "typesafe_fit_rating", True)
    monkeypatch.setattr(settings, "typesafe_api_key", "test-key")
    monkeypatch.setattr(verification, "_ask", ask)
    model = SaveModel()
    _outcomes, saved = _run_all(monkeypatch, model)
    # The 10 "unrelated" professors go on to a save instead of a no-match.
    assert len(model.calls) == 20 and saved == 20

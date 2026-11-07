import asyncio
import json

from api.agent.llm.base import LLMResponse, ToolCall
from api.agent.tools import ToolContext, dispatch
from api.candidates import scoring
from api.candidates.models import CandidateScore
from api.core.db import SessionLocal
from api.prospects import openalex
from api.prospects import tasks as prospect_tasks
from api.prospects.models import Program
from api.runs.models import ResearchTask, Run
from tests.conftest import TEST_USER_ID
from tests.test_budgets import _make_program, _make_run

AUTHOR = "https://openalex.org/A1"
WORKS = [
    {
        "title": "Terrain-aware planning for walking robots",
        "abstract": "A planner.",
        "year": 2023,
        "url": None,
    },
    {
        "title": "Legged locomotion with deep reinforcement learning",
        "abstract": "",
        "year": 2024,
        "url": None,
    },
]


def _research(monkeypatch):
    async def find_author(name, hint=None):
        return [
            {
                "openalex_id": AUTHOR,
                "display_name": name,
                "institution": "Test University",
            }
        ]

    async def works(openalex_id, limit=10):
        return WORKS

    async def score(ctx, interest_text, texts):
        assert texts == [
            "A planner.",
            WORKS[1]["title"],
        ]  # title stands in for a missing abstract
        assert interest_text == "robots"
        return {"score": 0.81, "best_index": 1, "all_scores": [0.42, 0.81]}

    monkeypatch.setattr(openalex, "find_author", find_author)
    monkeypatch.setattr(openalex, "get_recent_works", works)
    monkeypatch.setattr(scoring, "score_interest_for_ctx_async", score)


def _ctx_run():
    run_id = _make_run()
    _, program_id = _make_program(run_id)
    return run_id, program_id


def test_score_by_openalex_id_returns_titles_to_cite(monkeypatch):
    _research(monkeypatch)
    run_id, program_id = _ctx_run()

    async def go():
        async with SessionLocal() as session:
            ctx = ToolContext(
                session=session,
                run=await session.get(Run, run_id),
                program=await session.get(Program, program_id),
            )
            missing = await dispatch("score_alignment", {"openalex_id": AUTHOR}, ctx)
            await dispatch("find_openalex_author", {"name": "Ada Walker"}, ctx)
            await dispatch("get_author_works", {"openalex_id": "A1"}, ctx)
            scored = await dispatch("score_alignment", {"openalex_id": "A1"}, ctx)
            best = scored["top_works"][0]["title"]
            saved = await dispatch(
                "save_professor_record",
                {
                    "name": "Ada Walker",
                    "openalex_id": "A1",
                    "papers": [{"title": best}],
                    "similarity_score": scored["score"],
                    "rationale": f"Her paper {best} matches directly.",
                },
                ctx,
            )
            return missing, scored, saved

    missing, scored, saved = asyncio.run(go())
    assert "get_author_works for it first" in missing["error"]
    assert scored["score"] == 0.81
    assert [w["title"] for w in scored["top_works"]] == [
        WORKS[1]["title"],
        WORKS[0]["title"],
    ]
    assert "candidate_id" in saved, saved


def test_a_matched_professor_saves_in_four_turns(monkeypatch):
    import api.agent.orchestrator as orch

    _research(monkeypatch)
    run_id, program_id = _ctx_run()
    calls = {"n": 0}

    class Model:
        async def chat(self, messages, system, tools, max_tokens=4096):
            calls["n"] += 1
            last = messages[-1]
            if calls["n"] == 1:
                step = ToolCall(
                    id="c1",
                    name="find_openalex_author",
                    arguments={"name": "Ada Walker"},
                )
            elif calls["n"] == 2:
                step = ToolCall(
                    id="c2", name="get_author_works", arguments={"openalex_id": AUTHOR}
                )
            elif calls["n"] == 3:
                step = ToolCall(
                    id="c3", name="score_alignment", arguments={"openalex_id": AUTHOR}
                )
            else:
                content = last["content"]
                body = json.loads(content[content.index("{") : content.rindex("}") + 1])
                title = body["top_works"][0]["title"]
                step = ToolCall(
                    id="c4",
                    name="save_professor_record",
                    arguments={
                        "name": "Ada Walker",
                        "openalex_id": AUTHOR,
                        "papers": [{"title": title}],
                        "similarity_score": body["score"],
                        "rationale": f"Her paper {title} matches directly.",
                    },
                )
            return LLMResponse(text="", tool_calls=[step])

    monkeypatch.setattr(orch, "get_provider", lambda **_: Model())

    async def go():
        async with SessionLocal() as session:
            ctx = ToolContext(
                session=session,
                run=await session.get(Run, run_id),
                program=await session.get(Program, program_id),
            )
            out = await orch.run_agent_task(
                "sys",
                "go",
                ctx,
                task_type="research_one_professor",
                finish_on={"save_professor_record", "confirm_no_match"},
            )
            saved = (
                await session.execute(
                    CandidateScore.__table__.select().where(
                        CandidateScore.run_id == run_id
                    )
                )
            ).all()
            return out, saved

    out, saved = asyncio.run(go())
    assert calls["n"] == 4 and out["turns"] == 4
    assert len(saved) == 1
    assert "Saved: Ada Walker" in out["final_text"]


def test_a_failed_terminal_tool_does_not_end_the_task(monkeypatch):
    import api.agent.orchestrator as orch

    calls = {"n": 0}

    class Model:
        async def chat(self, messages, system, tools, max_tokens=4096):
            calls["n"] += 1
            if calls["n"] == 1:
                return LLMResponse(
                    text="",
                    tool_calls=[
                        ToolCall(id="c1", name="save_professor_record", arguments={})
                    ],
                )
            if calls["n"] == 2:
                return LLMResponse(
                    text="No confident match.",
                    tool_calls=[
                        ToolCall(
                            id="c2",
                            name="confirm_no_match",
                            arguments={"reason": "not at this school"},
                        )
                    ],
                )
            raise AssertionError("the task should have ended")

    async def fake_dispatch(batch, ctx, task_type=None):
        return [
            {"error": "refused"}
            if name == "save_professor_record"
            else {"acknowledged": True}
            for name, _ in batch
        ]

    monkeypatch.setattr(orch, "get_provider", lambda **_: Model())
    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)
    from types import SimpleNamespace

    out = asyncio.run(
        orch.run_agent_task(
            "sys",
            "go",
            ctx=SimpleNamespace(session=None, user_id=None, run=None),
            finish_on={"save_professor_record", "confirm_no_match"},
        )
    )
    assert calls["n"] == 2 and out["turns"] == 2
    assert "Skipped: not at this school" in out["final_text"]
    assert "Saved: None" in out["final_text"]


def test_professor_tasks_do_not_index_applications(monkeypatch):
    run_id, program_id = _ctx_run()
    steps = []

    async def fake_agent(system_prompt, user_message, ctx, **kwargs):
        steps.append((user_message, kwargs["finish_on"]))
        return {"final_text": "", "tool_log": [], "turns": 0, "usage": {}}

    monkeypatch.setattr(prospect_tasks, "run_agent_task", fake_agent)

    async def go():
        async with SessionLocal() as session:
            tasks = []
            for name in ("First Prof", "Second Prof"):
                t = ResearchTask(
                    user_id=TEST_USER_ID,
                    run_id=run_id,
                    task_type="research_one_professor",
                    target_id=program_id,
                    target_name=name,
                )
                session.add(t)
                await session.commit()
                tasks.append(t)
            run = await session.get(Run, run_id)
            for t in reversed(tasks):  # order of execution doesn't matter
                await prospect_tasks.run_research_one_professor(session, t, run)

    asyncio.run(go())
    (second, _), (first, first_finish) = steps
    assert "Second Prof" in second and "First Prof" in first
    assert "Do not index the application" in first and "Do not index the application" in second
    assert first_finish == {"save_professor_record", "confirm_no_match"}

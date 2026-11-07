import asyncio

import pytest

from api.core.db import SessionLocal
from api.prospects import openalex, pipeline
from api.prospects import tasks as prospect_tasks
from api.prospects.prompts import (
    INDEX_APPLICATION_MARKER,
    INDEX_APPLICATION_SYSTEM_PROMPT,
)
from api.runs.models import ResearchTask, Run
from tests.conftest import TEST_USER_ID
from tests.test_budgets import _make_program, _make_run


def _narrow(monkeypatch, *, resume=None, decision=None):
    """Run one narrow task with first pass and model stubbed; returns (first_pass calls, run_agent_task calls)."""
    run_id = _make_run()
    _, program_id = _make_program(run_id)
    passes, agents = [], []

    async def first_pass(ctx, school, name, on_event=None, indexed=None):
        passes.append(name)
        return decision or pipeline.Decision("no_match", "unrelated")

    async def agent(system_prompt, user_message, ctx, **kwargs):
        agents.append((system_prompt, user_message, kwargs.get("resume_messages")))
        return {"final_text": "step done", "tool_log": [], "turns": 1, "usage": {"input_tokens": 10, "output_tokens": 1}}

    monkeypatch.setattr(pipeline, "first_pass", first_pass)
    monkeypatch.setattr(pipeline, "enabled", lambda: True)
    monkeypatch.setattr(prospect_tasks, "run_agent_task", agent)

    async def go():
        async with SessionLocal() as session:
            task = ResearchTask(
                user_id=TEST_USER_ID, run_id=run_id, task_type="research_one_professor",
                target_id=program_id, target_name="Ada Walker",
            )  # fmt: skip
            session.add(task)
            await session.commit()
            run = await session.get(Run, run_id)
            return await prospect_tasks.run_research_one_professor(session, task, run, resume_messages=resume)

    return asyncio.run(go()), passes, agents


def test_the_first_professor_still_takes_the_code_first_path(monkeypatch):
    out, passes, agents = _narrow(monkeypatch)
    assert passes == ["Ada Walker"]
    assert agents == []
    assert "not a match" in out["final_text"]


def test_a_checkpoint_without_a_model_turn_still_gets_the_first_pass(monkeypatch):
    _, passes, agents = _narrow(monkeypatch, resume=[{"role": "user", "content": "Professor: Ada"}])
    assert passes == ["Ada Walker"] and agents == []


def test_a_checkpoint_with_model_turns_resumes_the_agent_loop(monkeypatch):
    history = [{"role": "user", "content": "Professor: Ada"}, {"role": "assistant", "content": "looking"}]
    _, passes, agents = _narrow(monkeypatch, resume=history)
    assert passes == []
    [(_, _, resumed)] = agents
    assert resumed == history


def test_an_admissions_checkpoint_resumes_only_that_step(monkeypatch):
    history = [
        {"role": "user", "content": f"{INDEX_APPLICATION_MARKER} PhD at Uni"},
        {"role": "assistant", "content": "fetching"},
    ]
    _, passes, agents = _narrow(monkeypatch, resume=history)
    assert passes == []
    [(prompt, _, resumed)] = agents
    assert prompt == INDEX_APPLICATION_SYSTEM_PROMPT and resumed == history


@pytest.mark.parametrize(
    ("name", "variants"),
    [
        ("Jane Q. Smith", ["Jane Smith"]),
        ("Smith, Jane", ["Jane Smith"]),
        ("Tanaka Hiroshi", ["Hiroshi Tanaka"]),
        ("Ada", []),
    ],
)
def test_name_variants(name, variants):
    assert openalex.name_variants(name) == variants


def test_authors_are_searched_within_the_school_under_other_spellings(monkeypatch):
    searched = []

    async def get_json(path, params):
        searched.append((params["search"], "filter" in params))
        if params["search"] == "Hiroshi Tanaka" and "filter" in params:
            return {"results": [{"id": "https://openalex.org/A9", "display_name": "Hiroshi Tanaka"}]}
        return {"results": []}

    monkeypatch.setattr(openalex, "_get_json", get_json)
    found = asyncio.run(openalex.find_author("Tanaka Hiroshi", institution_id="I123"))
    assert [c["openalex_id"] for c in found] == ["https://openalex.org/A9"]
    assert searched == [("Tanaka Hiroshi", True), ("Hiroshi Tanaka", True)]

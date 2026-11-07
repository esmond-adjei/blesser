import asyncio

import pytest

from api.core.config import settings
from api.core.db import SessionLocal
from api.prospects import tasks
from api.prospects.prompts import INDEX_APPLICATION_SYSTEM_PROMPT
from api.runs.models import ResearchTask, Run
from tests.conftest import TEST_USER_ID
from tests.test_budgets import _make_program, _make_run


@pytest.mark.parametrize("roster_first", [True, False])
def test_faculty_task_indexes_application_after_roster(monkeypatch, roster_first):
    run_id = _make_run()
    _, program_id = _make_program(run_id)
    steps = []

    async def roster(*args, **kwargs):
        if roster_first:
            steps.append("roster")
            return {"final_text": "Faculty queued", "tool_log": [], "turns": 0, "usage": {}}
        return None

    async def agent(prompt, message, ctx, **kwargs):
        steps.append("application" if prompt == INDEX_APPLICATION_SYSTEM_PROMPT else "roster")
        if prompt == INDEX_APPLICATION_SYSTEM_PROMPT:
            assert kwargs["task_type"] == "research_professor"
            assert kwargs["only_tools"] == {"search_web", "fetch_page", "save_application"}
        return {"final_text": "Done", "tool_log": [], "turns": 1, "usage": {}}

    monkeypatch.setattr(settings, "roster_min_names", 1)
    monkeypatch.setattr(tasks, "_roster_first", roster)
    monkeypatch.setattr(tasks, "run_agent_task", agent)
    monkeypatch.setattr("api.prospects.institutions.resolve_school", lambda *args: _no_institution())
    monkeypatch.setattr("api.prospects.rosters.openalex_seed", lambda *args: _no_names())

    async def run():
        async with SessionLocal() as session:
            task = ResearchTask(user_id=TEST_USER_ID, run_id=run_id, task_type="research_professor", target_id=program_id)
            session.add(task)
            await session.commit()
            return await tasks.run_research_professor(session, task, await session.get(Run, run_id))

    asyncio.run(run())
    assert steps == ["roster", "application"]


async def _no_institution():
    return None, None


async def _no_names():
    return []


def test_faculty_admissions_checkpoint_resumes_without_requeueing_roster(monkeypatch):
    run_id = _make_run()
    _, program_id = _make_program(run_id)
    history = [{"role": "user", "content": "Index the application for a programme"}, {"role": "assistant", "content": "Looking"}]
    seen = []

    async def agent(prompt, message, ctx, **kwargs):
        seen.append((prompt, kwargs.get("resume_messages"), kwargs["task_type"]))
        return {"final_text": "Done", "tool_log": [], "turns": 1, "usage": {}}

    monkeypatch.setattr(tasks, "run_agent_task", agent)

    async def run():
        async with SessionLocal() as session:
            task = ResearchTask(user_id=TEST_USER_ID, run_id=run_id, task_type="research_professor", target_id=program_id)
            session.add(task)
            await session.commit()
            await tasks.run_research_professor(session, task, await session.get(Run, run_id), resume_messages=history)

    asyncio.run(run())
    assert seen == [(INDEX_APPLICATION_SYSTEM_PROMPT, history, "research_professor")]


def test_faculty_default_allows_application_save():
    from api.agents import registry

    async def check():
        async with SessionLocal() as session:
            definitions = await registry.worker_definitions(session, TEST_USER_ID, "research_professor")
            return {tool["name"] for tool in definitions}

    assert "save_application" in asyncio.run(check())


def test_admissions_failure_does_not_remove_queued_professors(monkeypatch):
    from sqlalchemy import select

    from api.prospects import ranking
    from api.prospects.tools import handle_spawn_professor_research

    run_id = _make_run()
    _, program_id = _make_program(run_id)

    async def rank(session, school, interest, names):
        return names, False

    async def roster(session, ctx, program, key, **kwargs):
        await handle_spawn_professor_research({"names": ["Ada Walker"]}, ctx)
        return {"final_text": "Faculty queued", "tool_log": [], "turns": 0, "usage": {}}

    async def fail_admissions(*args, **kwargs):
        raise RuntimeError("Admissions search failed")

    monkeypatch.setattr(settings, "roster_min_names", 1)
    monkeypatch.setattr(ranking, "rank_by_topic", rank)
    monkeypatch.setattr(tasks, "_roster_first", roster)
    monkeypatch.setattr(tasks, "_index_application", fail_admissions)

    async def run():
        async with SessionLocal() as session:
            task = ResearchTask(user_id=TEST_USER_ID, run_id=run_id, task_type="research_professor", target_id=program_id)
            session.add(task)
            await session.commit()
            with pytest.raises(RuntimeError, match="Admissions search failed"):
                await tasks.run_research_professor(session, task, await session.get(Run, run_id))
        async with SessionLocal() as session:
            return (await session.execute(select(ResearchTask.target_name).where(
                ResearchTask.run_id == run_id, ResearchTask.task_type == "research_one_professor",
            ))).scalars().all()

    assert asyncio.run(run()) == ["Ada Walker"]

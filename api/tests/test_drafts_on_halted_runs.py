"""Stopping a run stops its research, not outreach asked for by hand."""

import asyncio
import json

import pytest

from api.agent.tools.context import ToolContext
from api.agent.tools.dispatch import run_halted
from api.core.db import SessionLocal
from api.runs import queue
from api.runs.models import ResearchTask, Run
from tests.conftest import TEST_USER_ID
from tests.test_task_lease import _run_id


def _setup(run_status: str, agent_states: dict | None = None) -> tuple[str, str, str]:
    run_id = _run_id()

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            run.status = run_status
            run.agent_states = json.dumps(agent_states) if agent_states else None
            draft = ResearchTask(user_id=TEST_USER_ID, run_id=run_id, task_type="draft_email")
            research = ResearchTask(user_id=TEST_USER_ID, run_id=run_id, task_type="discover_programs")
            session.add_all([draft, research])
            await session.commit()
            return draft.id, research.id

    draft_id, research_id = asyncio.run(go())
    return run_id, draft_id, research_id


def _claim_all(run_id: str) -> set[str]:
    async def go():
        claimed = set()
        async with SessionLocal() as session:
            while (task := await queue._claim_next_task(session, run_id)) is not None:
                claimed.add(task.id)
        return claimed

    return asyncio.run(go())


@pytest.mark.parametrize("run_status", ["paused", "cancelled"])
def test_halted_run_still_drafts_but_does_no_research(run_status):
    run_id, draft_id, _ = _setup(run_status)
    assert _claim_all(run_id) == {draft_id}


def test_paused_drafting_agent_holds_drafts_on_a_cancelled_run():
    run_id, _, _ = _setup("cancelled", {"draft_email": "paused"})
    assert _claim_all(run_id) == set()


@pytest.mark.parametrize("run_status", ["paused", "cancelled"])
def test_halted_run_does_not_stop_a_draft_mid_way(run_status):
    run_id, _, _ = _setup(run_status)

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            ctx = ToolContext(session=session, run=run)
            return await run_halted(ctx, "draft_email"), await run_halted(ctx, "discover_programs")

    assert asyncio.run(go()) == (None, run_status)


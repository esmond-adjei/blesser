import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from api.agent import gates
from api.agent.tools.dispatch import _invoke_untagged
from api.core.config import settings
from api.core.db import SessionLocal
from api.prospects import grounding, openalex
from api.runs import queue
from api.runs.models import ResearchTask, TaskStatus
from tests.test_openalex_budget import _bare_ctx, _mock, _narrow_task, _no_sleep


@pytest.fixture
def rejected(monkeypatch):
    """OpenAlex answering 401 to everything; returns the requests sent."""
    _no_sleep(monkeypatch)
    sent = []

    def handler(req):
        sent.append(req)
        return httpx.Response(401, json={"error": "invalid api key"})

    _mock(monkeypatch, handler)
    return sent


def test_a_rejected_key_opens_the_breaker_and_logs_once(rejected, caplog):
    with caplog.at_level(logging.ERROR, logger="api.prospects.openalex"):
        with pytest.raises(openalex.OpenAlexAuthError) as caught:
            asyncio.run(openalex.find_author("Ada Lovelace"))
        with pytest.raises(openalex.OpenAlexAuthError):
            asyncio.run(openalex.get_recent_works("A1"))
    assert len(rejected) == 1  # no retries, and nothing sent while it's open
    expected = datetime.now(UTC) + timedelta(seconds=settings.openalex_auth_recheck_seconds)
    assert abs((caught.value.until - expected).total_seconds()) < 5
    assert caught.value.status == 401
    errors = [r for r in caplog.records if "rejected the API key" in r.getMessage()]
    assert len(errors) == 1
    assert isinstance(caught.value, openalex.OpenAlexUnavailable)
    assert gates.classify(f"find_openalex_author failed: {caught.value}") == "openalex.auth"


def test_a_fixed_key_works_at_the_next_recheck(monkeypatch):
    _no_sleep(monkeypatch)
    replies = iter([httpx.Response(403), httpx.Response(200, json={"results": []})])
    _mock(monkeypatch, lambda req: next(replies))
    with pytest.raises(openalex.OpenAlexAuthError):
        asyncio.run(openalex.find_author("Ada Lovelace"))
    assert isinstance(openalex.wait_error(), openalex.OpenAlexAuthError)
    openalex._down_until = datetime.now(UTC) - timedelta(seconds=1)  # the recheck is due
    assert asyncio.run(openalex.find_author("Grace Hopper")) == []
    assert openalex.wait_error() is None


def test_outside_a_professor_task_it_is_an_outage(rejected):
    ctx = _bare_ctx()
    out = asyncio.run(_invoke_untagged("find_openalex_author", {"name": "Ada Lovelace"}, ctx, None))
    assert out["error"].startswith("find_openalex_author failed: OpenAlex rejected the server's API key")
    # Recorded as an outage, so the save can still go through unverified.
    assert grounding.UNAVAILABLE in ctx.openalex_outcomes
    assert grounding.unverified_save_error(ctx, {"rationale": "OpenAlex was down."}) is None


def test_a_professor_task_is_told_to_repeat_the_lookup_once_it_resumes(rejected):
    ctx = _bare_ctx(park_on_openalex_budget=True)
    out = asyncio.run(_invoke_untagged("find_openalex_author", {"name": "Ada Lovelace"}, ctx, None))
    assert isinstance(ctx.openalex_wait, openalex.OpenAlexAuthError)
    assert "rejected the server's API key" in out["error"] and "call find_openalex_author again" in out["error"]
    assert not getattr(ctx, "openalex_outcomes", None)


@pytest.mark.pipeline
def test_the_code_first_pass_waits(rejected):
    from api.agent.tools import ToolContext
    from api.prospects import pipeline
    from api.prospects.models import Program, School
    from api.runs.models import Run

    run_id, program_id, _ = _narrow_task()

    async def go():
        async with SessionLocal() as session:
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=await session.get(Run, run_id), program=program)
            ctx.park_on_openalex_budget = True
            await pipeline.first_pass(ctx, await session.get(School, program.school_id), "Ada Walker")

    with pytest.raises(openalex.OpenAlexAuthError):
        asyncio.run(go())


def test_a_professor_task_waits_for_the_recheck(monkeypatch):
    run_id, _, task_id = _narrow_task()
    until = datetime.now(UTC) + timedelta(seconds=settings.openalex_auth_recheck_seconds)

    async def rejected_key(session, task, run, **kwargs):
        raise openalex.OpenAlexAuthError(until, 403)

    monkeypatch.setitem(queue.TASK_HANDLERS, "research_one_professor", rejected_key)
    real_claim = queue._claim_next_task
    monkeypatch.setattr(queue, "_claim_next_task", lambda session: real_claim(session, run_id))
    assert asyncio.run(queue.process_one()) is True

    async def state():
        async with SessionLocal() as session:
            return await session.get(ResearchTask, task_id)

    task = asyncio.run(state())
    assert task.status == TaskStatus.pending
    assert task.error.startswith(f"{queue.OPENALEX_WAIT_PREFIX}the server's API key was rejected")
    naive = until.replace(tzinfo=None)
    # Resumes spread within one recheck, not the budget's 10 minutes.
    assert naive <= task.wait_until <= naive + timedelta(seconds=settings.openalex_auth_recheck_seconds)


def test_a_professor_task_waits_when_the_key_is_already_rejected(monkeypatch):
    from api.prospects import tasks as prospect_tasks
    from api.runs.models import Run

    run_id, _, task_id = _narrow_task()
    openalex._trip(datetime.now(UTC) + timedelta(minutes=5), "auth")

    async def no_agent(*args, **kwargs):
        raise AssertionError("no model call while the key is rejected")

    monkeypatch.setattr(prospect_tasks, "run_agent_task", no_agent)

    async def go():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            await prospect_tasks.run_research_one_professor(session, task, await session.get(Run, run_id))

    with pytest.raises(openalex.OpenAlexAuthError):
        asyncio.run(go())

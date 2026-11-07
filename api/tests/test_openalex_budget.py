import asyncio
import json
import types
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from api.agent.tools import ToolContext
from api.agent.tools.dispatch import HANDLERS
from api.core.config import settings
from api.core.db import SessionLocal
from api.prospects import openalex
from api.prospects import tasks as prospect_tasks
from api.prospects.models import Program, School
from api.runs import queue
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID
from tests.test_budgets import _make_program, _make_run

BUDGET_429 = {
    "retry-after": "42662",
    "x-ratelimit-limit-usd": "0.1",
    "x-ratelimit-remaining-usd": "0",
}


def _mock(monkeypatch, handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(openalex, "client", lambda: client)


def _no_sleep(monkeypatch, slept=None):
    async def sleep(seconds):
        if slept is not None:
            slept.append(seconds)

    monkeypatch.setattr(
        openalex, "asyncio", types.SimpleNamespace(sleep=sleep, Semaphore=asyncio.Semaphore)
    )


def test_the_api_key_is_sent_as_a_bearer_token(monkeypatch):
    assert "Authorization" not in openalex._headers()
    monkeypatch.setattr(settings, "openalex_api_key", " key-123 ")
    assert openalex._headers()["Authorization"] == "Bearer key-123"


def test_a_used_up_budget_trips_the_breaker_without_retrying(monkeypatch):
    _no_sleep(monkeypatch)
    sent = []

    def handler(req):
        sent.append(req)
        return httpx.Response(429, headers=BUDGET_429, json={"error": "budget"})

    _mock(monkeypatch, handler)
    with pytest.raises(openalex.OpenAlexBudgetExhausted) as caught:
        asyncio.run(openalex.find_author("Ada Lovelace"))
    assert len(sent) == 1  # no retries into a certain 429
    expected = datetime.now(UTC) + timedelta(seconds=42662)
    assert abs((caught.value.until - expected).total_seconds()) < 5
    assert openalex.down_until() == caught.value.until
    assert openalex.budget()["remaining_usd"] == 0
    with pytest.raises(openalex.OpenAlexBudgetExhausted):
        asyncio.run(openalex.get_recent_works("A1"))
    assert len(sent) == 1
    assert isinstance(caught.value, openalex.OpenAlexUnavailable)


def test_a_short_429_waits_as_long_as_it_asks(monkeypatch):
    slept = []
    _no_sleep(monkeypatch, slept)
    replies = iter(
        [
            httpx.Response(429, headers={"retry-after": "2"}),
            httpx.Response(200, json={"results": []}),
        ]
    )
    _mock(monkeypatch, lambda req: next(replies))
    assert asyncio.run(openalex.find_author("Ada Lovelace")) == []
    assert slept == [2.0]
    assert openalex.down_until() is None


def test_the_last_of_the_budget_trips_the_breaker_before_a_429(monkeypatch):
    _no_sleep(monkeypatch)
    sent = []

    def handler(req):
        sent.append(req)
        return httpx.Response(
            200,
            headers={"x-ratelimit-remaining-usd": "0", "x-ratelimit-reset": "600"},
            json={"results": []},
        )

    _mock(monkeypatch, handler)
    assert asyncio.run(openalex.find_author("Ada Lovelace")) == []
    until = openalex.down_until()
    assert until is not None
    assert abs((until - datetime.now(UTC)).total_seconds() - 600) < 5
    with pytest.raises(openalex.OpenAlexBudgetExhausted):
        asyncio.run(openalex.find_author("Grace Hopper"))
    assert len(sent) == 1


def test_the_breaker_closes_at_the_reset():
    openalex._trip(datetime.now(UTC) - timedelta(seconds=1))
    assert openalex.down_until() is None


def _bare_ctx(**attrs):
    ctx = ToolContext(session=None, run=types.SimpleNamespace(user_id=TEST_USER_ID))  # type: ignore[arg-type]
    for k, v in attrs.items():
        setattr(ctx, k, v)
    return ctx


def test_an_identical_failed_lookup_is_not_sent_again(monkeypatch):
    calls = []

    async def down(name, hint=None, **_):
        calls.append(name)
        raise openalex.OpenAlexUnavailable("OpenAlex is unavailable right now (HTTP 503). Don't invent papers.")

    monkeypatch.setattr(openalex, "find_author", down)
    ctx = _bare_ctx()
    find = HANDLERS["find_openalex_author"]
    with pytest.raises(openalex.OpenAlexUnavailable):
        asyncio.run(find({"name": "Ada Lovelace"}, ctx))
    again = asyncio.run(find({"name": "Ada Lovelace"}, ctx))
    assert "already failed in this task (OpenAlex is unavailable right now (HTTP 503))" in again["error"]
    assert "unverified: true" in again["error"]
    assert calls == ["Ada Lovelace"]
    with pytest.raises(openalex.OpenAlexUnavailable):
        asyncio.run(find({"name": "Grace Hopper"}, ctx))
    assert calls == ["Ada Lovelace", "Grace Hopper"]


def test_a_waiting_task_is_told_to_repeat_the_lookup(monkeypatch):
    until = datetime.now(UTC) + timedelta(hours=3)

    async def budget(name, hint=None, **_):
        raise openalex.OpenAlexBudgetExhausted(until)

    monkeypatch.setattr(openalex, "find_author", budget)
    ctx = _bare_ctx(park_on_openalex_budget=True)
    out = asyncio.run(HANDLERS["find_openalex_author"]({"name": "Ada Lovelace"}, ctx))
    assert ctx.openalex_wait.until == until
    assert "call find_openalex_author again" in out["error"]
    # Not cached as failed and no outage recorded: after the reset the lookup must really run.
    assert ctx.failed_openalex_calls == {}
    assert not getattr(ctx, "openalex_outcomes", None)


@pytest.mark.parametrize("wait", [openalex.OpenAlexBudgetExhausted, openalex.OpenAlexAuthError])
def test_the_agent_loop_stops_before_the_next_model_call(monkeypatch, wait):
    import api.agent.orchestrator as orch
    from api.agent.llm.base import LLMResponse, ToolCall

    until = datetime.now(UTC) + timedelta(hours=3)
    chats = []

    class Provider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            chats.append(messages)
            return LLMResponse(
                text="looking them up",
                tool_calls=[ToolCall(id="t1", name="find_openalex_author", arguments={"name": "Ada"})],
            )

    async def fake_dispatch(calls, ctx, task_type=None):
        ctx.openalex_wait = wait(until)
        return [{"error": "OpenAlex's daily budget ran out ... call find_openalex_author again."}]

    monkeypatch.setattr(orch, "get_provider", lambda **_: Provider())
    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)
    checkpoints = []

    async def on_checkpoint(messages):
        checkpoints.append(json.loads(json.dumps(messages, default=str)))

    ctx = types.SimpleNamespace(park_on_openalex_budget=True, openalex_wait=None)
    with pytest.raises(wait) as caught:
        asyncio.run(orch.run_agent_task("sys", "go", ctx=ctx, on_checkpoint=on_checkpoint))  # type: ignore[arg-type]
    assert caught.value.until == until
    assert len(chats) == 1
    assert len(checkpoints) == 1
    assert any(m.get("role") == "tool" and "call find_openalex_author again" in m["content"] for m in checkpoints[0])


def _narrow_task():
    run_id = _make_run()
    _, program_id = _make_program(run_id)

    async def setup():
        async with SessionLocal() as session:
            task = ResearchTask(
                user_id=TEST_USER_ID,
                run_id=run_id,
                task_type="research_one_professor",
                target_id=program_id,
                target_name="Ada Walker",
            )
            session.add(task)
            await session.commit()
            return run_id, program_id, task.id

    return asyncio.run(setup())


def test_a_professor_task_waits_when_the_budget_is_already_used_up(monkeypatch):
    run_id, _, task_id = _narrow_task()
    openalex._trip(datetime.now(UTC) + timedelta(hours=2))

    async def no_agent(*args, **kwargs):
        raise AssertionError("no model call while OpenAlex is down")

    monkeypatch.setattr(prospect_tasks, "run_agent_task", no_agent)

    async def go():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            run = await session.get(Run, run_id)
            await prospect_tasks.run_research_one_professor(session, task, run)

    with pytest.raises(openalex.OpenAlexBudgetExhausted):
        asyncio.run(go())


@pytest.mark.pipeline
def test_the_code_first_pass_waits_instead_of_handing_over(monkeypatch):
    from api.prospects import pipeline

    until = datetime.now(UTC) + timedelta(hours=2)

    async def budget(name, hint=None, **_):
        raise openalex.OpenAlexBudgetExhausted(until)

    monkeypatch.setattr(openalex, "find_author", budget)
    run_id, program_id, _ = _narrow_task()

    async def go():
        async with SessionLocal() as session:
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=await session.get(Run, run_id), program=program)
            ctx.park_on_openalex_budget = True
            school = await session.get(School, program.school_id)
            await pipeline.first_pass(ctx, school, "Ada Walker")

    with pytest.raises(openalex.OpenAlexBudgetExhausted) as caught:
        asyncio.run(go())
    assert caught.value.until == until


def test_a_waiting_task_stays_queued_until_the_reset(monkeypatch):
    monkeypatch.setattr(settings, "openalex_resume_spread_seconds", 600)
    run_id, _, task_id = _narrow_task()
    until = datetime.now(UTC) + timedelta(hours=2)

    async def budget_out(session, task, run, **kwargs):
        raise openalex.OpenAlexBudgetExhausted(until)

    monkeypatch.setitem(queue.TASK_HANDLERS, "research_one_professor", budget_out)
    real_claim = queue._claim_next_task
    monkeypatch.setattr(queue, "_claim_next_task", lambda session: real_claim(session, run_id))
    assert asyncio.run(queue.process_one()) is True

    async def state():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            run = await session.get(Run, run_id)
            return task, run.status

    task, run_status = asyncio.run(state())
    assert task.status == TaskStatus.pending
    assert task.claimed_by is None
    assert task.error.startswith(queue.OPENALEX_WAIT_PREFIX)
    naive = until.replace(tzinfo=None)
    assert naive <= task.wait_until <= naive + timedelta(seconds=600)
    assert run_status == "running"
    assert asyncio.run(queue.process_one()) is False

    async def reset_passed():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            task.wait_until = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(reset_passed())

    async def done(session, task, run, **kwargs):
        return {"final_text": "researched", "turns": 1, "usage": {}}

    monkeypatch.setitem(queue.TASK_HANDLERS, "research_one_professor", done)
    assert asyncio.run(queue.process_one()) is True
    task, _ = asyncio.run(state())
    assert task.status == TaskStatus.done
    assert task.error is None and task.wait_until is None


def test_the_breaker_waits_as_long_as_the_server_asks_not_until_a_midnight_guess():
    # A 12-hour Retry-After just after midnight ends before the next midnight; the breaker must not keep the later guess.
    now = datetime(2026, 10, 18, 0, 5, tzinfo=UTC)
    resp = httpx.Response(429, headers=BUDGET_429)
    assert openalex._budget_reset(resp, now) == now + timedelta(seconds=42662)
    reset = httpx.Response(429, headers={"x-ratelimit-remaining-usd": "0", "x-ratelimit-reset": "600"})
    assert openalex._budget_reset(reset, now) == now + timedelta(seconds=600)
    bare = httpx.Response(429, headers={"x-ratelimit-remaining-usd": "0"})
    assert openalex._budget_reset(bare, now) == datetime(2026, 10, 19, tzinfo=UTC)

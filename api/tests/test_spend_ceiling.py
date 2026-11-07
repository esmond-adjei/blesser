import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.agent.llm.base import LLMResponse
from api.agent.orchestrator import ModelAllowanceRefused, run_agent_task
from api.agent.tools.context import ToolContext
from api.auth import models as auth_models
from api.billing import service as billing
from api.candidates.models import CandidateScore, CandidateStatus
from api.core.config import settings
from api.core.db import SessionLocal
from api.core.exceptions import ForbiddenError
from api.main import app
from api.metering import service as metering
from api.prospects import tasks as prospect_tasks
from api.prospects.models import Professor
from api.runs.models import Run
from tests.conftest import TEST_USER_ID
from tests.test_convergence import _make_program, _make_run

OPERATOR_KEY = "operator-key-marker"


class Counting:
    name = model = "counting"

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, system, tools, max_tokens=4096):
        self.calls += 1
        return LLMResponse(text="Done.", tool_calls=[], usage={"input_tokens": 5})


def _set_verified(verified: bool):
    async def go():
        async with SessionLocal() as session:
            user = await session.get(auth_models.User, TEST_USER_ID)
            assert user is not None
            user.email_verified_at = (
                datetime.now(UTC).replace(tzinfo=None) if verified else None
            )
            await session.commit()

    asyncio.run(go())


def _run_task(monkeypatch, provider) -> dict:
    import api.agent.orchestrator as orch

    monkeypatch.setattr(orch, "get_provider", lambda **_: provider)
    run_id = _make_run()

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            try:
                return await run_agent_task(
                    "BASE",
                    "go",
                    ToolContext(session=session, run=run),
                    task_type="discover_programs",
                )
            except ModelAllowanceRefused as exc:
                return {"refused": exc.message}

    return asyncio.run(go())


@pytest.fixture(autouse=True)
def _clean_usage():
    """Recorded usage is shared state: leave none behind for other files."""
    from sqlalchemy import delete

    from api.metering.models import UsageDaily

    async def wipe():
        async with SessionLocal() as session:
            await session.execute(
                delete(UsageDaily).where(UsageDaily.user_id == TEST_USER_ID)
            )
            await session.commit()

    asyncio.run(wipe())
    yield
    asyncio.run(wipe())


@pytest.fixture(autouse=True)
def _free_plan(monkeypatch):
    # Beta (billing off) has no daily ceilings, so these run on Free, the account's stored plan.
    monkeypatch.setattr(settings, "billing_enforced", True)


def _free_token_cap(monkeypatch, tokens: int) -> None:
    """Point Free's Auto ceiling at a test-sized number; the env var cannot set it."""
    from dataclasses import replace

    from api.billing import plans as plan_defs

    monkeypatch.setattr(
        billing,
        "PLANS",
        {**plan_defs.PLANS, "free": replace(plan_defs.PLANS["free"], system_tokens_per_day=tokens)},
    )


@pytest.fixture
def operator_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", OPERATOR_KEY)
    yield
    _set_verified(False)


def test_unverified_account_cannot_spend_operator_key(monkeypatch, operator_key):
    _set_verified(False)
    provider = Counting()
    result = _run_task(monkeypatch, provider)
    assert provider.calls == 0
    assert "Confirm your email" in result["refused"]


def test_operator_key_daily_ceiling(monkeypatch, operator_key):
    _set_verified(True)
    _free_token_cap(monkeypatch, 100)
    asyncio.run(metering.record(TEST_USER_ID, "research", "anthropic", "m", 90, 20))
    provider = Counting()
    result = _run_task(monkeypatch, provider)
    assert provider.calls == 0
    assert "allowance" in result["refused"]


def test_beta_has_no_daily_ceiling(monkeypatch, operator_key):
    _set_verified(True)
    monkeypatch.setattr(settings, "billing_enforced", False)
    monkeypatch.setattr(settings, "system_model_daily_tokens", 100)
    monkeypatch.setattr(settings, "system_daily_tool_calls", 1)
    asyncio.run(metering.record(TEST_USER_ID, "research", "anthropic", "m", 90, 20))
    provider = Counting()
    result = _run_task(monkeypatch, provider)
    assert provider.calls > 0
    assert "refused" not in result

    async def two_tool_calls():
        for _ in range(2):
            await billing.reserve_tool_call(TEST_USER_ID, "search", "test")

    asyncio.run(two_tool_calls())  # past the 1-call ceiling, not refused


def test_system_model_can_be_switched_off(operator_key, monkeypatch):
    _set_verified(True)
    monkeypatch.setattr(settings, "allow_system_model", False)

    async def go():
        async with SessionLocal() as session:
            await billing.check_model_allowance(session, TEST_USER_ID, {})

    with pytest.raises(ForbiddenError):
        asyncio.run(go())

    async def own_key():
        async with SessionLocal() as session:
            await billing.check_model_allowance(
                session, TEST_USER_ID, {"provider": "openai", "api_key": "mine"}
            )

    asyncio.run(own_key())


def test_over_quota_task_makes_no_model_call(monkeypatch):
    monkeypatch.setattr(settings, "billing_enforced", True)
    asyncio.run(
        metering.record(TEST_USER_ID, "research", "openai", "gpt", 3_000_000, 0)
    )
    provider = Counting()
    result = _run_task(monkeypatch, provider)
    assert provider.calls == 0
    assert "model tokens a month" in result["refused"]


@pytest.mark.parametrize(
    "dial,value",
    [
        ("max_professors_per_program", 10000),
        ("max_programs", 500),
        ("max_professors", 5000),
    ],
)
def test_run_dials_are_bounded(dial, value):
    body = {
        "region": "X",
        "field": "y",
        "degree_level": "phd",
        "interest_statement": "robots",
        dial: value,
    }
    with TestClient(app) as client:
        assert client.post("/api/runs", json=body).status_code == 422


def test_narrow_task_after_cap_spends_nothing(monkeypatch):
    run_id = _make_run(max_professors=1)
    program_id = _make_program(run_id)

    async def fill():
        async with SessionLocal() as session:
            prof = Professor(user_id=TEST_USER_ID, program_id=program_id, name="Taken")
            session.add(prof)
            await session.flush()
            session.add(
                CandidateScore(
                    user_id=TEST_USER_ID,
                    run_id=run_id,
                    professor_id=prof.id,
                    similarity_score=0.5,
                    status=CandidateStatus.scored,
                )
            )
            await session.commit()

    asyncio.run(fill())
    called = []

    async def never(*args, **kwargs):
        called.append(1)
        return {}

    monkeypatch.setattr(prospect_tasks, "run_agent_task", never)

    class Task:
        id = "t"
        target_id = program_id
        target_name = "Late Professor"

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            return await prospect_tasks.run_research_one_professor(session, Task(), run)

    result = asyncio.run(go())
    assert called == []
    assert result["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert result["final_text"].startswith("Skipped")


def test_undecryptable_key_is_an_error_not_the_operator_key(monkeypatch, prefer_own_model):
    from api.core.secrets import SecretUnavailable
    from api.providers import service as providers_service

    async def broken(session, user_id):
        raise SecretUnavailable("Stored secret can't be decrypted")

    monkeypatch.setattr(providers_service, "resolve_active_config", broken)

    async def go():
        async with SessionLocal() as session:
            return await providers_service.resolve_llm_kwargs(session, TEST_USER_ID)

    with pytest.raises(SecretUnavailable):
        asyncio.run(go())


def _reserve_concurrently(n: int, estimate: int) -> list:
    async def one():
        try:
            return await billing.reserve_model_call(TEST_USER_ID, {}, estimate)
        except ForbiddenError:
            return None

    async def go():
        return await asyncio.gather(*(one() for _ in range(n)))

    return asyncio.run(go())


def test_concurrent_calls_cannot_all_pass_one_reading(monkeypatch, operator_key):
    """Of five concurrent calls against a 100-token ceiling, only those fitting before it pass."""
    _set_verified(True)
    _free_token_cap(monkeypatch, 100)
    results = _reserve_concurrently(5, 60)
    admitted = [r for r in results if r is not None]
    assert len(admitted) == 2  # 0 -> 60 -> 120; everything after refuses

    async def today():
        async with SessionLocal() as session:
            return await billing.tokens_today(session, TEST_USER_ID)

    assert asyncio.run(today()) == 120
    for reservation in admitted:
        asyncio.run(billing.release(reservation))
    assert asyncio.run(today()) == 0
    assert all(r is not None for r in _reserve_concurrently(1, 60))


def test_reservations_are_hidden_from_usage_views(operator_key):
    _set_verified(True)
    reservation = asyncio.run(billing.reserve_model_call(TEST_USER_ID, {}, 500))
    try:

        async def view():
            async with SessionLocal() as session:
                return await metering.summary(session, TEST_USER_ID, 1)

        out = asyncio.run(view())
        assert out["totals"]["input_tokens"] == 0
        assert out["by_feature"] == []
    finally:
        asyncio.run(billing.release(reservation))


def test_model_call_releases_its_reservation(monkeypatch, operator_key):
    _set_verified(True)
    provider = Counting()
    _run_task(monkeypatch, provider)
    assert provider.calls == 1

    async def today():
        async with SessionLocal() as session:
            return await billing.tokens_today(session, TEST_USER_ID)

    assert asyncio.run(today()) == 5


def test_operator_tools_share_a_daily_call_ceiling(monkeypatch):
    """Search, scoring and the TypeSafe re-judge spend operator keys outside the model."""
    import importlib

    from api.candidates import tools as candidate_tools
    from api.candidates import verification
    from api.prospects import web

    # The package re-exports a `dispatch` function under the module's name.
    dispatch = importlib.import_module("api.agent.tools.dispatch")
    monkeypatch.setattr(settings, "system_daily_tool_calls", 3)
    searches = []

    async def fake_search(query, max_results=8):
        searches.append(query)
        return [{"title": "t", "url": "https://example.org", "snippet": ""}]

    monkeypatch.setattr(web, "search_web", fake_search)

    async def fake_judge(*_a, **_k):
        return {"verdict": "verified", "confidence": 1.0, "auto": True, "model": "m"}

    monkeypatch.setattr(verification, "check_rationale_citation", fake_judge)
    monkeypatch.setattr(settings, "typesafe_rationale_check", True)
    monkeypatch.setattr(settings, "typesafe_api_key", "ts-key")
    run_id = _make_run()

    async def go():
        async with SessionLocal() as session:
            ctx = ToolContext(session=session, run=await session.get(Run, run_id))
            first = await dispatch._search_web({"query": "a"}, ctx)
            second = await dispatch._search_web({"query": "b"}, ctx)
            judged = await verification.maybe_verify_rationale({}, TEST_USER_ID)
            over = await dispatch._search_web({"query": "c"}, ctx)
            scored = await candidate_tools.handle_score_alignment(
                {"interest_text": "x", "abstracts": ["y"]}, ctx
            )
            rejudged = await verification.maybe_verify_rationale({}, TEST_USER_ID)
            return first, second, judged, over, scored, rejudged

    first, second, judged, over, scored, rejudged = asyncio.run(go())
    assert "results" in first and "results" in second
    assert judged is not None and judged["auto"]
    assert "calls" in over["error"]
    assert "calls" in scored["error"]
    assert rejudged is None
    assert searches == ["a", "b"]

    async def counted():
        async with SessionLocal() as session:
            return await billing.tool_calls_today(session, TEST_USER_ID)

    assert asyncio.run(counted()) == 3


def test_interest_embedding_cache_honors_tool_ceiling(monkeypatch):
    """The run-creation embedding spends the operator key, so a capped account skips the cache."""
    import api.runs.service as run_service
    from api.candidates import scoring

    monkeypatch.setattr(settings, "system_daily_tool_calls", 1)
    calls = []
    monkeypatch.setattr(
        scoring, "embed_texts", lambda texts, **_: calls.append(texts) or [[0.1] * 3]
    )

    async def cached_embedding(run_id):
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            await run_service.cache_interest_embedding(run)
            return run.interest_embedding

    async def spend_one():
        await billing.reserve_tool_call(TEST_USER_ID, "scoring", "test", "test")

    asyncio.run(spend_one())
    assert asyncio.run(cached_embedding(_make_run())) is None
    assert calls == []

    monkeypatch.setattr(settings, "system_daily_tool_calls", 1000)
    assert asyncio.run(cached_embedding(_make_run())) is not None
    assert len(calls) == 1

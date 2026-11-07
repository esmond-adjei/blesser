import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.agent.llm.base import LLMResponse
from api.agent.tools import ToolContext
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.providers import models as providers_models
from api.runs.models import Run

RUN = {"region": "Canada", "field": "Robotics", "degree_level": "phd", "interest_statement": "Robot learning for manipulation"}


@pytest.fixture(autouse=True)
def _clean_providers():
    async def _wipe():
        async with SessionLocal() as session:
            await session.execute(delete(providers_models.ProviderConfig))
            await session.commit()

    asyncio.run(_wipe())
    yield
    asyncio.run(_wipe())


def _configure(client, provider="ollama", model="qwen3:8b", active=False):
    resp = client.patch(f"/api/providers/{provider}", json={"model": model, "is_active": active})
    assert resp.status_code == 200, resp.text


def test_a_run_keeps_the_model_it_was_started_with():
    client = TestClient(app)
    _configure(client)
    resp = client.post("/api/runs", json={**RUN, "llm_provider": "ollama"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["llm_provider"] == "ollama"
    assert client.post("/api/runs", json={**RUN, "llm_provider": "system"}).json()["llm_provider"] == "system"


def test_unset_means_auto_even_with_a_default_own_model():
    client = TestClient(app)
    _configure(client, active=True)
    assert client.post("/api/runs", json=RUN).json()["llm_provider"] == "system"
    assert client.post("/api/runs", json={**RUN, "llm_provider": "default"}).json()["llm_provider"] == "system"


def test_opting_in_makes_unset_use_the_own_default(prefer_own_model):
    client = TestClient(app)
    assert client.post("/api/runs", json=RUN).json()["llm_provider"] == "system"
    _configure(client, active=True)
    assert client.post("/api/runs", json=RUN).json()["llm_provider"] == "ollama"
    client.patch("/api/providers/ollama", json={"enabled": False})
    assert client.post("/api/runs", json=RUN).json()["llm_provider"] == "system"


def test_the_preference_is_a_profile_setting_that_keeps_the_name():
    client = TestClient(app)
    client.patch("/api/auth/me", json={"display_name": "Ada"})
    body = client.patch("/api/auth/me", json={"prefer_own_model": True}).json()
    assert body["prefer_own_model"] is True and body["display_name"] == "Ada"
    assert client.patch("/api/auth/me", json={"prefer_own_model": False}).json()["prefer_own_model"] is False


def test_a_switched_off_model_keeps_its_details_and_is_not_offered():
    client = TestClient(app)
    _configure(client, active=True)
    row = client.patch("/api/providers/ollama", json={"enabled": False}).json()
    assert row["enabled"] is False and row["model"] == "qwen3:8b" and row["is_active"] is True
    resp = client.post("/api/runs", json={**RUN, "llm_provider": "ollama"})
    assert resp.status_code == 400 and "switched off" in resp.text
    client.patch("/api/providers/ollama", json={"enabled": True})
    assert client.post("/api/runs", json={**RUN, "llm_provider": "ollama"}).status_code == 200


def test_an_unconfigured_model_is_refused_up_front():
    client = TestClient(app)
    resp = client.post("/api/runs", json={**RUN, "llm_provider": "openai"})
    assert resp.status_code == 400 and "openai" in resp.text
    assert client.post("/api/runs", json={**RUN, "llm_provider": "nope"}).status_code == 400


def test_switching_a_runs_model_mid_run():
    client = TestClient(app)
    _configure(client)
    run_id = client.post("/api/runs", json=RUN).json()["id"]
    assert client.patch(f"/api/runs/{run_id}", json={"llm_provider": "ollama"}).json()["llm_provider"] == "ollama"
    assert client.patch(f"/api/runs/{run_id}", json={"llm_provider": "openai"}).status_code == 400
    assert client.patch(f"/api/runs/{run_id}", json={"max_programs": 3}).json()["llm_provider"] == "ollama"
    assert client.patch(f"/api/runs/{run_id}", json={"llm_provider": None}).json()["llm_provider"] == "system"
    client.patch(f"/api/runs/{run_id}", json={"llm_provider": "ollama"})
    assert client.patch(f"/api/runs/{run_id}", json={"llm_provider": "default"}).json()["llm_provider"] == "system"


def test_agent_calls_use_the_runs_model(monkeypatch):
    import api.agent.orchestrator as orch

    client = TestClient(app)
    _configure(client, "ollama", "qwen3:8b")
    _configure(client, "openai", "gpt-5-mini", active=True)
    run_id = client.post("/api/runs", json={**RUN, "llm_provider": "ollama"}).json()["id"]
    seen = []

    class Model:
        async def chat(self, messages, system, tools, max_tokens=4096):
            return LLMResponse(text="Done.", tool_calls=[])

    def get_provider(**kwargs):
        seen.append((kwargs.get("provider"), kwargs.get("model")))
        return Model()

    monkeypatch.setattr(orch, "get_provider", get_provider)

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            await orch.run_agent_task("system", "hello", ToolContext(session=session, run=run))
            run.llm_provider = None
            await orch.run_agent_task("system", "hello", ToolContext(session=session, run=run))
            run.llm_provider = "ollama"
            await session.commit()

    asyncio.run(go())
    # Auto is the factory with no overrides: the environment's model.
    assert seen == [("ollama", "qwen3:8b"), (None, None)]

    client.patch("/api/providers/ollama", json={"enabled": False})
    seen.clear()

    async def again():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            await orch.run_agent_task("system", "hello", ToolContext(session=session, run=run))

    asyncio.run(again())
    assert seen == [(None, None)]


def test_estimate_follows_the_chosen_model(monkeypatch):
    monkeypatch.setattr(settings, "billing_enforced", True)  # Free: has the ceiling
    monkeypatch.setattr(settings, "llm_api_key", "operator-key")
    monkeypatch.setattr(settings, "system_model_daily_tokens", 1_000_000)
    client = TestClient(app)
    _configure(client, "ollama", "qwen3:8b", active=True)
    own = client.get("/api/runs/estimate", params={"llm_provider": "ollama"}).json()
    shared = client.get("/api/runs/estimate", params={"llm_provider": "system"}).json()
    assert own["daily_allowance_left"] is None
    assert shared["daily_allowance_left"] is not None


def test_system_allowance_follows_the_plan(monkeypatch):
    from api.billing import plans
    from api.billing.service import system_daily_cap

    monkeypatch.setattr(settings, "system_model_daily_tokens", 1_000_000)
    assert system_daily_cap(plans.PLANS["beta"]) == 1_000_000
    assert system_daily_cap(plans.PLANS["free"]) == 500_000
    assert system_daily_cap(plans.PLANS["pro"]) == 0  # unlimited
    assert system_daily_cap(None) == 1_000_000


def test_pro_has_no_daily_ceiling_on_the_system_model(monkeypatch):
    from api.auth.models import User
    from api.billing.service import check_model_allowance
    from api.metering import service as metering
    from tests.conftest import TEST_USER_ID

    monkeypatch.setattr(settings, "llm_api_key", "operator-key")
    monkeypatch.setattr(settings, "system_model_requires_verified_email", False)
    monkeypatch.setattr(settings, "system_model_daily_tokens", 100)
    monkeypatch.setattr(settings, "billing_enforced", True)
    asyncio.run(metering.record(TEST_USER_ID, "research", "anthropic", "m", 500_000, 100_000))

    async def check(plan):
        async with SessionLocal() as session:
            user = await session.get(User, TEST_USER_ID)
            user.plan = plan
            await session.commit()
            await check_model_allowance(session, TEST_USER_ID, {})

    try:
        asyncio.run(check("pro"))  # past the server's 100 and free's 500k
        with pytest.raises(Exception, match="500,000-token allowance"):
            asyncio.run(check("free"))
    finally:
        asyncio.run(_reset_plan_and_usage())


async def _reset_plan_and_usage():
    from sqlalchemy import delete as sa_delete

    from api.auth.models import User
    from api.metering.models import UsageDaily
    from tests.conftest import TEST_USER_ID

    async with SessionLocal() as session:
        user = await session.get(User, TEST_USER_ID)
        user.plan = "free"
        await session.execute(sa_delete(UsageDaily).where(UsageDaily.user_id == TEST_USER_ID))
        await session.commit()

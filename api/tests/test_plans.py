"""Each test uses a fresh account so monthly counts start at zero."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from api.auth import models as auth_models
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.metering import service as metering

pytestmark = pytest.mark.real_auth
RUN = {
    "region": "X",
    "field": "y",
    "degree_level": "phd",
    "interest_statement": "robots",
}


def _account(client, plan="free"):
    email = f"plan-{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/api/auth/register", json={"accept_terms": True, "email": email, "password": "long-enough-1"}
    ).json()
    user_id = reg["user"]["id"]
    _set_plan(user_id, plan)
    return user_id, {"Authorization": f"Bearer {reg['tokens']['access_token']}"}


def _set_plan(user_id, plan):
    async def go():
        async with SessionLocal() as session:
            await session.execute(
                update(auth_models.User)
                .where(auth_models.User.id == user_id)
                .values(plan=plan)
            )
            await session.commit()

    asyncio.run(go())


def test_beta_everyone_unaffected(monkeypatch):
    monkeypatch.setattr(settings, "billing_enforced", False)
    with TestClient(app) as client:
        _, h = _account(client)
        plan = client.get("/api/billing/plan", headers=h).json()
        assert plan["plan"]["id"] == "beta" and plan["enforced"] is False
        assert all(f["included"] for f in plan["features"])
        assert all(q["limit"] is None for q in plan["quotas"])
        for _ in range(5):  # past Free's 3/month
            assert client.post("/api/runs", json=RUN, headers=h).status_code == 200
        big = client.post("/api/runs", json={**RUN, "max_professors": 250}, headers=h).json()
        assert big["max_professors"] == 250


def test_free_run_quota_and_per_run_cap(monkeypatch):
    monkeypatch.setattr(settings, "billing_enforced", True)
    with TestClient(app) as client:
        _, h = _account(client)
        first = client.post(
            "/api/runs", json={**RUN, "max_professors": 80}, headers=h
        ).json()
        assert first["max_professors"] == 30  # clamped to Free's per-run cap
        for _ in range(2):
            assert client.post("/api/runs", json=RUN, headers=h).status_code == 200
        blocked = client.post("/api/runs", json=RUN, headers=h)
        assert blocked.status_code == 402
        detail = blocked.json()["detail"]
        assert detail["code"] == "upgrade_required" and detail["kind"] == "quota"
        assert (
            detail["key"] == "runs_per_month"
            and detail["used"] == 3
            and detail["limit"] == 3
        )
        assert detail["upgrade_to"] == "pro" and "you've used 3" in detail["message"]
        summary = client.get("/api/billing/plan", headers=h).json()
        runs = next(q for q in summary["quotas"] if q["key"] == "runs_per_month")
        assert runs == {
            "key": "runs_per_month",
            "label": "Research runs per month",
            "limit": 3,
            "used": 3,
        }


def test_token_allowance_gates_chat_and_pro_passes(monkeypatch):
    monkeypatch.setattr(settings, "billing_enforced", True)
    with TestClient(app) as client:
        user_id, h = _account(client)
        asyncio.run(metering.record(user_id, "chat", "p", "m", 2_000_000, 0))
        conv = client.post("/api/assistant/conversations", headers=h).json()["id"]
        r = client.post(
            f"/api/assistant/conversations/{conv}/chat",
            json={"content": "hi"},
            headers=h,
        )
        assert (
            r.status_code == 402
            and r.json()["detail"]["key"] == "model_tokens_per_month"
        )
        _set_plan(user_id, "pro")
        big = client.post(
            "/api/runs", json={**RUN, "max_professors": 80}, headers=h
        ).json()
        assert big["max_professors"] == 80


def test_free_interest_suggestions_needs_pro(monkeypatch):
    monkeypatch.setattr(settings, "billing_enforced", True)
    with TestClient(app) as client:
        user_id, h = _account(client)
        r = client.post("/api/runs/interest-suggestions", headers=h)
        assert r.status_code == 402
        assert r.json()["detail"]["key"] == "interest_suggestions"
        _set_plan(user_id, "pro")
        ok = client.post("/api/runs/interest-suggestions", headers=h)
        assert ok.status_code == 200
        assert ok.json()["method"] == "none"


def test_free_update_run_clamps_professor_cap(monkeypatch):
    monkeypatch.setattr(settings, "billing_enforced", True)
    with TestClient(app) as client:
        _, h = _account(client)
        run_id = client.post("/api/runs", json=RUN, headers=h).json()["id"]
        patched = client.patch(
            f"/api/runs/{run_id}", json={"max_professors": 250}, headers=h
        ).json()
        assert patched["max_professors"] == 30


def test_plan_switch_is_off_by_default(monkeypatch):
    monkeypatch.setattr(settings, "billing_plan_switch", False)
    with TestClient(app) as client:
        _, h = _account(client)
        assert client.put("/api/billing/plan", json={"plan": "pro"}, headers=h).status_code == 404
        plan = client.get("/api/billing/plan", headers=h).json()
        assert plan["switchable"] is False and plan["plans"] == []


def test_plan_switch_applies_the_picked_plan_without_billing(monkeypatch):
    monkeypatch.setattr(settings, "billing_enforced", False)
    monkeypatch.setattr(settings, "billing_plan_switch", True)
    with TestClient(app) as client:
        _, h = _account(client, plan="pro")
        plan = client.get("/api/billing/plan", headers=h).json()
        assert plan["switchable"] is True and plan["enforced"] is True
        assert {p["id"] for p in plan["plans"]} == {"free", "pro", "beta"}

        free = client.put("/api/billing/plan", json={"plan": "free"}, headers=h).json()
        assert free["plan"]["id"] == "free"
        for _ in range(3):
            assert client.post("/api/runs", json=RUN, headers=h).status_code == 200
        assert client.post("/api/runs", json=RUN, headers=h).status_code == 402  # Free: 3/month

        client.put("/api/billing/plan", json={"plan": "beta"}, headers=h)
        assert client.post("/api/runs", json=RUN, headers=h).status_code == 200

        bad = client.put("/api/billing/plan", json={"plan": "gold"}, headers=h)
        assert bad.status_code == 400

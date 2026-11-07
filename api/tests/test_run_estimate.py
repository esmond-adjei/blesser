"""Each case uses a fresh account, so other tests' tasks never count."""

import asyncio
import uuid

from fastapi.testclient import TestClient

from api.auth import models as auth_models
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.metering import service as metering
from api.runs.estimate import estimate_run
from api.runs.models import ResearchTask, Run, TaskStatus


def _account(narrow_history: int = 0) -> str:
    async def go():
        async with SessionLocal() as session:
            user_id = str(uuid.uuid4())
            session.add(
                auth_models.User(id=user_id, email=f"{user_id}@example.com", password_hash="x")
            )
            await session.flush()
            if narrow_history:
                run = Run(user_id=user_id, region="U", field="f", degree_level="phd",
                          interest_statement="x", status="done")  # fmt: skip
                session.add(run)
                await session.flush()
                for _ in range(narrow_history):
                    session.add(ResearchTask(
                        run_id=run.id, user_id=user_id, task_type="research_one_professor",
                        status=TaskStatus.done, input_tokens=9_000, output_tokens=1_000,
                    ))  # fmt: skip
            await session.commit()
            return user_id

    return asyncio.run(go())


def _estimate(user_id: str, programs=10, professors=30, per_program=5) -> dict:
    async def go():
        async with SessionLocal() as session:
            return await estimate_run(
                session, user_id, max_programs=programs, max_professors=professors,
                max_professors_per_program=per_program,
            )  # fmt: skip

    return asyncio.run(go())


def test_defaults_until_there_is_history(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    out = _estimate(_account())
    # 1 discovery + 10 supervisors + min(10x5, 30x2.5) narrow tasks.
    assert out["narrow_tasks"] == 50
    assert out["estimated_tokens"] == 80_000 + 10 * 30_000 + 50 * 25_000
    assert out["basis"] == "defaults"


def test_own_history_replaces_the_defaults(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    out = _estimate(_account(narrow_history=5), programs=2, professors=10, per_program=3)
    assert out["basis"] == "history"
    assert out["estimated_tokens"] == 80_000 + 2 * 30_000 + 6 * 10_000


def test_says_when_the_shared_allowance_is_short(monkeypatch):
    monkeypatch.setattr(settings, "billing_enforced", True)  # Free: has the ceiling
    monkeypatch.setattr(settings, "llm_api_key", "operator-key")
    user_id = _account()
    # Free's Auto ceiling is 500k/day (Plan.system_tokens_per_day).
    asyncio.run(metering.record(user_id, "research", "anthropic", "m", 350_000, 50_000))
    out = _estimate(user_id)
    assert out["daily_allowance_left"] == 100_000
    assert out["fits"] is False


def test_own_key_has_no_allowance_and_the_route_answers(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    out = _estimate(_account())
    assert out["daily_allowance_left"] is None and out["fits"] is None
    # Declared before /runs/{run_id}, so "estimate" is never read as a run id.
    resp = TestClient(app).get("/api/runs/estimate", params={"max_programs": 3})
    assert resp.status_code == 200, resp.text
    assert set(resp.json()) >= {"estimated_tokens", "basis", "fits"}

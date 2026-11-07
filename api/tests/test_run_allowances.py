import asyncio

from fastapi.testclient import TestClient

from api.agent.tools import ToolContext, dispatch
from api.assistant import tools as assistant_tools
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.runs.models import Run
from tests.conftest import TEST_USER_ID


def _run(**kwargs) -> str:
    async def setup():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID,
                region="U",
                field="f",
                degree_level="phd",
                interest_statement="robots",
                status="running",
                **kwargs,
            )
            session.add(run)
            await session.commit()
            return run.id

    return asyncio.run(setup())


def _program(n):
    return {"school_name": f"Quota Uni {n}", "program_name": f"PhD {n}"}


def test_chat_saves_work_after_agent_budget_is_spent_and_vice_versa():
    run_id = _run(max_programs=1)

    async def flow():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            agent = ToolContext(session=session, run=run)
            first = await dispatch("save_program", _program(1), agent)
            refused = await dispatch("save_program", _program(2), agent)
            chat = await assistant_tools.invoke(
                "save_program",
                {"run_id": run_id, **_program(3)},
                session,
                TEST_USER_ID,
                approved=True,
            )
            return first, refused, chat

    first, refused, chat = asyncio.run(flow())
    assert "program_id" in first
    assert "Run program budget reached" in refused["error"]
    assert "program_id" in chat, chat

    with TestClient(app) as client:
        budget = client.get(f"/api/runs/{run_id}/budget").json()
    assert budget["programs"] == {"used": 1, "limit": 1}
    assert budget["user_programs"]["used"] == 1


def test_user_additions_have_their_own_clear_cap(monkeypatch):
    monkeypatch.setattr(settings, "max_user_programs_per_run", 1)
    run_id = _run(max_programs=5)

    async def flow():
        async with SessionLocal() as session:
            ok = await assistant_tools.invoke(
                "save_program",
                {"run_id": run_id, **_program(1)},
                session,
                TEST_USER_ID,
                approved=True,
            )
            capped = await assistant_tools.invoke(
                "save_program",
                {"run_id": run_id, **_program(2)},
                session,
                TEST_USER_ID,
                approved=True,
            )
            run = await session.get(Run, run_id)
            agent = await dispatch(
                "save_program", _program(3), ToolContext(session=session, run=run)
            )
            return ok, capped, agent

    ok, capped, agent = asyncio.run(flow())
    assert "program_id" in ok
    assert "most allowed" in capped["error"]
    assert "program_id" in agent

    with TestClient(app) as client:
        manual = client.post(
            f"/api/runs/{run_id}/schools", json={"name": "One too many"}
        )
    assert manual.status_code == 400
    assert "limit 1" in manual.json()["detail"]

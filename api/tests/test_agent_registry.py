"""Registry tables are wiped around every test so a disabled tool can't leak into later modules."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.agent.orchestrator import run_agent_task
from api.agent.tools.context import ToolContext
from api.agent.tools.dispatch import dispatch, dispatch_batch
from api.agents import models as agents_models
from api.agents import registry as agents_registry
from api.assistant import tools as assistant_tools
from api.core.db import SessionLocal
from api.main import app
from api.runs.models import Run
from tests.conftest import TEST_USER_ID


@pytest.fixture(autouse=True)
def _clean_registry():
    async def _wipe():
        async with SessionLocal() as session:
            await session.execute(delete(agents_models.AgentTool))
            await session.execute(delete(agents_models.AgentTask))
            await session.commit()

    asyncio.run(_wipe())
    yield
    asyncio.run(_wipe())


def _client():
    return TestClient(app)


async def _ctx(session, run_id: str) -> ToolContext:
    run = await session.get(Run, run_id)
    if run is None:
        run = Run(user_id=TEST_USER_ID, 
            id=run_id,
            region="United States",
            field="robotics",
            degree_level="phd",
            interest_statement="robots",
            status="running",
        )
        session.add(run)
        await session.commit()
    return ToolContext(session=session, run=run)


def test_registry_seeds_from_code():
    client = _client()
    tools = client.get("/api/agent/tools").json()
    by_scope: dict[str, set[str]] = {}
    for row in tools:
        by_scope.setdefault(row["scope"], set()).add(row["name"])
    from api.agent.tools.dispatch import HANDLERS as worker_handlers

    assert by_scope["worker"] == set(worker_handlers)
    assert by_scope["assistant"] == set(assistant_tools.HANDLERS)
    assert all(row["enabled"] for row in tools)
    assert all(row["description"] for row in tools)

    tasks = client.get("/api/agent/tasks").json()
    assert {t["task_type"] for t in tasks} == {
        "discover_programs",
        "research_professor",
        "research_one_professor",
        "draft_email",
    }
    # Least privilege by default: every task has an explicit list.
    from api.agents.registry import DEFAULT_TASK_TOOLS

    assert all(t["enabled"] for t in tasks)
    assert {t["task_type"]: tuple(t["tools"]) for t in tasks} == DEFAULT_TASK_TOOLS


def test_disabled_worker_tool_is_refused_and_hidden():
    client = _client()
    patched = client.patch(
        "/api/agent/tools/worker/fetch_page", json={"enabled": False}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["enabled"] is False

    async def check():
        async with SessionLocal() as session:
            ctx = await _ctx(session, "run-registry-hidden")
            refused = await dispatch("fetch_page", {"url": "https://example.edu"}, ctx)
            assert "disabled" in refused.get("error", "")
            defs = await agents_registry.worker_definitions(session, TEST_USER_ID)
            names = [d["name"] for d in defs]
            assert "fetch_page" not in names
            assert "search_web" in names

    asyncio.run(check())


def test_task_allowlist_restricts_batch():
    client = _client()
    patched = client.patch(
        "/api/agent/tasks/draft_email", json={"tools": ["save_email_draft"]}
    )
    assert patched.status_code == 200, patched.text

    async def check():
        async with SessionLocal() as session:
            ctx = await _ctx(session, "run-registry-allow")
            results = await dispatch_batch(
                [("confirm_no_match", {"reason": "none"}), ("save_email_draft", {})],
                ctx,
                "draft_email",
            )
            assert "allowlist" in results[0].get("error", "")
            assert "allowlist" not in results[1].get("error", "")

    asyncio.run(check())


def test_disabled_task_returns_without_model_call():
    client = _client()
    assert (
        client.patch(
            "/api/agent/tasks/draft_email", json={"enabled": False}
        ).status_code
        == 200
    )

    async def check():
        async with SessionLocal() as session:
            ctx = await _ctx(session, "run-registry-disabled")
            result = await run_agent_task(
                "sys", "do work", ctx, task_type="draft_email"
            )
            assert result["turns"] == 0
            assert "disabled" in result["final_text"]

    asyncio.run(check())


def test_assistant_disable_and_unknown_rows_404():
    client = _client()
    assert (
        client.patch(
            "/api/agent/tools/assistant/list_runs", json={"enabled": False}
        ).status_code
        == 200
    )

    async def check():
        async with SessionLocal() as session:
            result = await assistant_tools.invoke(
                "list_runs", {}, session, TEST_USER_ID
            )
            assert "disabled" in result.get("error", "")
            ok = await assistant_tools.invoke(
                "get_run", {"run_id": "does-not-exist"}, session, TEST_USER_ID
            )
            assert "disabled" not in ok.get("error", "")

    asyncio.run(check())
    assert (
        client.patch(
            "/api/agent/tools/worker/nope", json={"enabled": False}
        ).status_code
        == 404
    )
    assert (
        client.patch("/api/agent/tasks/nope", json={"enabled": False}).status_code
        == 404
    )


def test_tool_groups_cover_real_tools_and_do_not_overlap():
    from api.agent.tools.dispatch import HANDLERS
    from api.agents.groups import TOOL_GROUPS

    known = set(HANDLERS) | set(assistant_tools.HANDLERS)
    seen: set[str] = set()
    for gid, group in TOOL_GROUPS.items():
        members = set(group["tools"])
        assert members <= known, f"{gid} names unknown tools: {members - known}"
        assert not members & seen, f"{gid} overlaps another group"
        seen |= members


def test_group_toggle_flips_members_together_and_resolves_mixed():
    with _client() as client:
        tools = client.get("/api/agent/tools").json()
        web = [t for t in tools if t["scope"] == "assistant" and t["group"] == "web"]
        assert {t["name"] for t in web} == {"search_web", "fetch_page"}
        assert all(t["group"] == "runs" for t in tools if t["name"] == "list_runs")

        client.patch("/api/agent/tools/assistant/fetch_page", json={"enabled": False})
        resp = client.patch("/api/agent/tool-groups/assistant/web", json={"enabled": True})
        assert resp.status_code == 200, resp.text
        assert {t["name"]: t["enabled"] for t in resp.json()} == {
            "search_web": True,
            "fetch_page": True,
        }

        off = client.patch("/api/agent/tool-groups/assistant/web", json={"enabled": False})
        assert {t["enabled"] for t in off.json()} == {False}
        # Scopes are independent: the worker's web tools are untouched.
        worker_web = [
            t
            for t in client.get("/api/agent/tools").json()
            if t["scope"] == "worker" and t["group"] == "web"
        ]
        assert worker_web and all(t["enabled"] for t in worker_web)

        assert client.patch(
            "/api/agent/tool-groups/assistant/nope", json={"enabled": True}
        ).status_code == 404
        # The worker scope has no CV tools, so the group does not exist there.
        assert client.patch(
            "/api/agent/tool-groups/worker/cv", json={"enabled": True}
        ).status_code == 404
        groups = client.get("/api/agent/tool-groups").json()
        assert {g["id"] for g in groups} >= {"web", "scholar", "cv"}


def test_group_approval_and_full_access_skip_the_ask():
    from api.agents import registry
    from api.core.db import SessionLocal
    from tests.conftest import TEST_USER_ID

    async def asks(name):
        async with SessionLocal() as session:
            return await registry.assistant_confirm_required(session, TEST_USER_ID, name)

    with _client() as client:
        resp = client.patch("/api/agent/tool-groups/assistant/professors", json={"confirm_required": False})
        assert resp.status_code == 200, resp.text
        flags = {t["name"]: t["confirm_required"] for t in resp.json()}
        assert flags["delete_professor"] is False
        # Reads never ask, whatever the group says.
        assert flags["get_professor"] is False
        client.patch("/api/agent/tool-groups/assistant/professors", json={"confirm_required": True})
        assert asyncio.run(asks("delete_professor")) is True

        me = client.patch("/api/auth/me", json={"agent_full_access": True})
        assert me.json()["agent_full_access"] is True
        try:
            assert asyncio.run(asks("delete_professor")) is False
        finally:
            client.patch("/api/auth/me", json={"agent_full_access": False})
        assert asyncio.run(asks("delete_professor")) is True

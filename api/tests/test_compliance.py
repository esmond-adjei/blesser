import asyncio
import uuid
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from api.agent.tools import ToolContext, dispatch
from api.auth import models as auth_models
from api.core import egress
from api.core.config import settings
from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.main import app
from api.prospects import openalex, optouts, web
from api.prospects.models import Professor, Program
from api.runs.models import ResearchTask, Run, TaskStatus, ToolCallLog
from api.runs.retention import prune_traces
from tests.conftest import TEST_USER_ID
from tests.grounding_helpers import ground
from tests.test_budgets import _make_program, _make_run, _professor_input


def _public_dns(monkeypatch):
    async def resolve(host, port):
        return ["93.184.216.34"]

    monkeypatch.setattr(egress, "_resolve", resolve)


@pytest.mark.real_auth
def test_sign_up_requires_and_records_consent():
    email = f"terms-{uuid.uuid4().hex[:8]}@example.com"
    with TestClient(app) as client:
        refused = client.post(
            "/api/auth/register", json={"email": email, "password": "long-enough-1"}
        )
        assert refused.status_code == 400
        assert "Terms" in refused.json()["detail"]
        ok = client.post(
            "/api/auth/register",
            json={"email": email, "password": "long-enough-1", "accept_terms": True},
        )
        assert ok.status_code == 200, ok.text
        user_id = ok.json()["user"]["id"]

    async def check():
        async with SessionLocal() as session:
            user = await session.get(auth_models.User, user_id)
            assert user is not None
            return user.terms_accepted_at, user.terms_version

    accepted_at, version = asyncio.run(check())
    assert accepted_at is not None and version == settings.terms_version


def _mock_fetch(monkeypatch, handler):
    seen: list[httpx.Request] = []

    def record(req):
        seen.append(req)
        return handler(req)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(record),
        headers={"User-Agent": settings.fetch_user_agent},
    )
    monkeypatch.setattr(web, "fetch_client", lambda: client)
    return seen


def test_fetches_identify_the_agent(monkeypatch):
    _public_dns(monkeypatch)
    seen = _mock_fetch(monkeypatch, lambda req: httpx.Response(200, text="<p>hi</p>"))
    asyncio.run(web.fetch_page("https://uni.example/people"))
    assert seen and all("GraduatorBot" in r.headers["user-agent"] for r in seen)
    assert all("Mozilla" not in r.headers["user-agent"] for r in seen)
    web._fetch_client = None
    assert "GraduatorBot" in web.fetch_client().headers["user-agent"]


@pytest.mark.robots
def test_robots_disallow_is_honoured(monkeypatch):
    _public_dns(monkeypatch)
    page_hits = []

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(
                200, text="User-agent: GraduatorBot\nDisallow: /private\n"
            )
        page_hits.append(str(req.url))
        return httpx.Response(200, text="<p>Faculty list</p>")

    _mock_fetch(monkeypatch, handler)
    blocked = asyncio.run(web.fetch_page("https://uni.example/private/staff"))
    assert "robots.txt" in blocked and page_hits == []
    allowed = asyncio.run(web.fetch_page("https://uni.example/people"))
    assert "robots.txt" not in allowed and page_hits == ["https://uni.example/people"]


def test_duckduckgo_is_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "search_providers", "")
    monkeypatch.setattr(settings, "search_provider", "tavily")
    assert [e["name"] for e in web.search_chain()] == ["tavily"]
    monkeypatch.setattr(settings, "search_providers", "tavily,duckduckgo")
    assert [e["name"] for e in web.search_chain()] == ["tavily", "duckduckgo"]


def test_openalex_contact_is_configurable(monkeypatch):
    monkeypatch.setattr(settings, "openalex_mailto", "")
    assert "example.com" not in openalex._headers()["User-Agent"]
    monkeypatch.setattr(settings, "openalex_mailto", "ops@grad.example")
    assert openalex._headers()["User-Agent"] == "graduator (mailto:ops@grad.example)"


def test_old_traces_are_pruned():
    run_id = _make_run()

    async def go():
        async with SessionLocal() as session:
            old = ResearchTask(
                user_id=TEST_USER_ID,
                run_id=run_id,
                task_type="discover_programs",
                status=TaskStatus.done,
                finished_at=utcnow_naive() - timedelta(days=200),
                log="[{}]",
                messages_json="[]",
            )
            fresh = ResearchTask(
                user_id=TEST_USER_ID,
                run_id=run_id,
                task_type="discover_programs",
                status=TaskStatus.done,
                finished_at=utcnow_naive(),
                log="[{}]",
            )
            session.add_all([old, fresh])
            await session.flush()
            for t in (old, fresh):
                session.add(
                    ToolCallLog(
                        task_id=t.id, user_id=TEST_USER_ID, turn=1, tool_name="x"
                    )
                )
            await session.commit()
            counts = await prune_traces(session, days=90)
            await session.refresh(old)
            await session.refresh(fresh)
            return counts, old.log, old.messages_json, fresh.log

    counts, old_log, old_messages, fresh_log = asyncio.run(go())
    assert counts["tool_calls"] >= 1 and counts["tasks"] >= 1
    assert old_log is None and old_messages is None
    assert fresh_log == "[{}]"


def test_removed_person_is_deleted_everywhere_and_never_resaved():
    run_id = _make_run()
    _, program_id = _make_program(run_id)
    payload = _professor_input(1)

    async def save():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            return await dispatch(
                "save_professor_record", ground(ctx, dict(payload)), ctx
            )

    first = asyncio.run(save())
    assert "professor_id" in first, first

    async def remove():
        async with SessionLocal() as session:
            return await optouts.remove_person(
                session, name=payload["name"], school="Test University", note="test"
            )

    counts = asyncio.run(remove())
    assert counts["professors"] >= 1 and counts["candidates"] >= 1

    async def gone():
        async with SessionLocal() as session:
            return await session.get(Professor, first["professor_id"])

    assert asyncio.run(gone()) is None
    again = asyncio.run(save())
    assert "asked not to be included" in again["error"]

    async def spawn():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            program = await session.get(Program, program_id)
            return await dispatch(
                "spawn_professor_research",
                {"names": [payload["name"], "Someone Else"]},
                ToolContext(session=session, run=run, program=program),
            )

    spawned = asyncio.run(spawn())
    assert spawned.get("names") == ["Someone Else"], spawned

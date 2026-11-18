import asyncio
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.agent.llm.base import LLMResponse, ToolCall
from api.assistant import service
from api.auth.models import User
from api.auth.security import issue_access_token
from api.core.config import settings
from api.core.db import SessionLocal
from api.core.ids import new_id
from api.core.ratelimit import LIMITS
from api.main import app
from api.opportunities.models import Opportunity
from tests.conftest import TEST_USER_ID

BASE = "/api/app/assistant/conversations"


def _events(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return [
        {"event": lines[0][7:], **json.loads(lines[1][6:])}
        for frame in response.text.split("\n\n")
        if (lines := frame.splitlines()) and lines[0].startswith("event: ")
    ]


def _model(monkeypatch, *replies):
    remaining = iter(replies)
    calls = []

    class Provider:
        async def chat(self, **kwargs):
            calls.append(kwargs)
            return next(remaining)

    monkeypatch.setattr(service, "get_provider", Provider)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    return calls


def _tool(name, **arguments):
    return LLMResponse(tool_calls=[ToolCall(new_id(), name, arguments)])


def _chat(client):
    response = client.post(BASE)
    assert response.status_code == 201
    return f"{BASE}/{response.json()['id']}"


def _seed(*, user=False, opportunities=False):
    async def add():
        async with SessionLocal() as session:
            owner = TEST_USER_ID
            if user:
                other = User(email=f"{new_id()}@example.org", password_hash="test")
                session.add(other)
                await session.flush()
                owner = other.id
            title = f"Climate Grant {new_id()[:8]}"
            if opportunities:
                for status in ("published", "hidden"):
                    session.add(
                        Opportunity(
                            title=title
                            if status == "published"
                            else f"{title} private",
                            organization="Climate Fund",
                            category="research",
                            kind="grant",
                            status=status,
                            source="staff",
                            audience="members",
                            dedupe_key=f"{title}-{status}",
                            deadline_date=date(2040, 6, 18),
                        )
                    )
            await session.commit()
            return owner, title

    return asyncio.run(add())


def test_catalog_turn_streams_and_persists_grounded_citations(monkeypatch):
    _, title = _seed(opportunities=True)
    calls = _model(
        monkeypatch,
        _tool("search_catalog", query=title),
        LLMResponse(
            text=f"{title} closes on [deadline:s1]. [s1]\nA different grant closes on 31 December 2041. [s99]"
        ),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(f"{path}/chat", json={"content": f"When does {title} close?"})
        )
        assert [e["event"] for e in events] == [
            "user_message",
            "status",
            "tool_start",
            "tool_result",
            "status",
            "token",
            "message",
            "done",
        ]
        assert "search_web" not in {item["name"] for item in calls[0]["tools"]}
        msg = events[-2]["message"]
        assert "closes on 18 Jun 2040" in msg["content"]
        assert "2041" not in msg["content"]
        assert msg["cited_deadlines"]
        assert len(msg["sources"]) == 1
        assert msg["sources"][0]["opportunity"]["title"] == title
        assert msg["trace"][0]["label"] == "Searched the Blesser catalog, 1 match"
        thread = client.get(path).json()
        assert thread["messages"][-1] == msg
        assert thread["running"] is False
        assert (
            client.patch(path, json={"title": "Research deadlines"}).json()["title"]
            == "Research deadlines"
        )
        assert any(
            chat["title"] == "Research deadlines" for chat in client.get(BASE).json()
        )
        assert client.delete(path).status_code == 204
        assert client.get(path).status_code == 404


@pytest.mark.parametrize("approved", [True, False])
def test_to_do_proposal_only_writes_after_approval(monkeypatch, approved):
    title = f"Review {new_id()}"
    _model(monkeypatch, _tool("enable_changes"), _tool("add_todo", title=title))
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(
                f"{path}/chat", json={"content": f"Add a to-do called {title}."}
            )
        )
        pending = next(e["call"] for e in events if e["event"] == "confirm_required")
        assert pending["summary"] == f"Add “{title}” to your to-dos?"
        assert client.get(path).json()["pending_call"] == pending
        assert not any(
            todo["title"] == title for todo in client.get("/api/app/todos").json()
        )
        assert (
            client.post(
                f"{path}/chat", json={"content": "A different prompt"}
            ).status_code
            == 409
        )

        confirm = {"call_id": pending["id"], "approved": approved}
        events = _events(client.post(f"{path}/confirm", json=confirm))
        assert events[-1]["event"] == "done"
        assert client.get(path).json()["pending_call"] is None
        assert client.post(f"{path}/confirm", json=confirm).status_code == 404
        todos = [
            todo
            for todo in client.get("/api/app/todos").json()
            if todo["title"] == title
        ]
        assert len(todos) == int(approved)


def test_private_context_cannot_reach_web_search(monkeypatch):
    monkeypatch.setattr(service.web, "search_chain", lambda: [{"configured": True}])

    async def never_search(*args):
        pytest.fail("Private data must not reach a search provider")

    monkeypatch.setattr(service.web, "search_web", never_search)
    calls = _model(
        monkeypatch,
        _tool("search_catalog", query="unique-no-match"),
        LLMResponse(
            tool_calls=[
                ToolCall("private", "list_applications"),
                ToolCall("web", "search_web", {"query": "private application"}),
            ]
        ),
        LLMResponse(text="I checked your applications."),
        _tool("search_catalog", query="unique-no-match"),
        LLMResponse(text="I checked the catalog."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(f"{path}/chat", json={"content": "Check my applications."})
        )
        steps = [e["step"] for e in events if e["event"] == "tool_result"]
        assert steps[-1]["tool"] == "search_web"
        assert not steps[-1]["ok"]
        assert "search_web" in {definition["name"] for definition in calls[1]["tools"]}
        _events(client.post(f"{path}/chat", json={"content": "Search again."}))
        assert "search_web" not in {
            definition["name"] for definition in calls[-1]["tools"]
        }


@pytest.mark.real_auth
def test_chats_authenticate_and_are_owned_by_the_member():
    owner, _ = _seed(user=True)
    other, _ = _seed(user=True)
    auth = {"Authorization": f"Bearer {issue_access_token(owner)}"}
    outsider = {"Authorization": f"Bearer {issue_access_token(other)}"}
    with TestClient(app) as client:
        assert client.get(BASE).status_code == 401
        chat_id = client.post(BASE, headers=auth).json()["id"]
        path = f"{BASE}/{chat_id}"
        assert client.get(path, headers=auth).status_code == 200
        assert client.get(BASE, headers=outsider).json() == []
        assert client.get(path, headers=outsider).status_code == 404
        assert (
            client.patch(path, headers=outsider, json={"title": "Changed"}).status_code
            == 404
        )
        assert client.delete(path, headers=outsider).status_code == 404


@pytest.mark.rate_limits
def test_chat_rate_limit_and_clear_unconfigured_response(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setitem(LIMITS, "assistant", [(1, 60)])
    with TestClient(app) as client:
        path = _chat(client)
        response = client.post(
            f"{path}/chat", json={"content": "Help with my applications"}
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "Assistant isn't set up yet"
        response = client.post(f"{path}/chat", json={"content": "Try again"})
        assert response.status_code == 429
        assert response.headers.get("Retry-After")


def test_public_web_fallback_uses_existing_search_and_links_only_returned_sources(
    monkeypatch,
):
    monkeypatch.setattr(service.web, "search_chain", lambda: [{"configured": True}])
    queries = []

    async def search(query):
        queries.append(query)
        return [
            {
                "url": "https://example.org/grant",
                "title": "Grant listing",
                "snippet": "Applications close on 27 December 2040.",
            }
        ]

    monkeypatch.setattr(service.web, "search_web", search)
    _model(
        monkeypatch,
        _tool("search_catalog", query=f"nonexistent-{new_id()}"),
        _tool("search_web", query="public astronomy grant"),
        LLMResponse(
            text="I found a web listing you can check. [s1]\nIt closes on 27 December 2040."
        ),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(
                f"{path}/chat", json={"content": "Find public astronomy grants."}
            )
        )
        result = events[-2]["message"]
        assert queries == ["public astronomy grant"]
        assert result["sources"][0]["url"] == "https://example.org/grant"
        assert "2040" not in result["content"]
        assert not result["cited_deadlines"]


def test_track_confirmation_uses_catalog_record_and_updates_only_current_member(
    monkeypatch,
):
    _, title = _seed(opportunities=True)

    async def opportunity_id():
        async with SessionLocal() as session:
            return await session.scalar(
                select(Opportunity.id).where(Opportunity.title == title)
            )

    opp_id = asyncio.run(opportunity_id())
    _model(
        monkeypatch,
        _tool("search_catalog", query=title),
        _tool("enable_changes"),
        _tool("track_opportunity", opportunity_id=opp_id),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(f"{path}/chat", json={"content": f"Track {title} for me."})
        )
        pending = next(e["call"] for e in events if e["event"] == "confirm_required")
        assert title in pending["summary"]
        assert opp_id not in client.get("/api/app/opportunities/tracked").json()
        completed = _events(
            client.post(
                f"{path}/confirm", json={"call_id": pending["id"], "approved": True}
            )
        )
        assert (
            completed[-2]["message"]["content"] == f"“{title}” is in your applications."
        )
        assert opp_id in client.get("/api/app/opportunities/tracked").json()

import asyncio
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.agent.llm.base import BaseLLMProvider, LLMResponse, ToolCall
from api.applications.models import Application
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

    class Provider(BaseLLMProvider):
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


def _saved_application(owner=TEST_USER_ID):
    async def add():
        async with SessionLocal() as session:
            opp = Opportunity(
                title="Unreviewed scholarship",
                organization="Fund",
                category="research",
                kind="grant",
                status="in_review",
                source="staff",
                dedupe_key=new_id(),
                summary="Unpublished editorial content",
            )
            session.add(opp)
            await session.flush()
            application = Application(
                user_id=owner,
                title="My saved scholarship",
                opportunity_id=opp.id,
                notes="My saved research notes",
                benefits="Saved benefit",
                requirements=[{"label": "Existing reference", "done": True}],
            )
            session.add(application)
            await session.commit()
            return application.id, opp.id

    return asyncio.run(add())


def test_owned_application_details_do_not_require_catalog_publication(monkeypatch):
    application_id, opportunity_id = _saved_application()
    calls = _model(
        monkeypatch,
        _tool("get_opportunity", opportunity_id=opportunity_id),
        _tool("get_application", application_id=application_id),
        LLMResponse(text="Your saved notes are available. [s1]"),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(f"{path}/chat", json={"content": "Read my saved details."})
        )
        error = json.loads(calls[1]["messages"][2]["content"])
        assert error["code"] == "not_found_or_inaccessible"
        assert error["retryable"] is False
        saved = json.loads(calls[2]["messages"][-1]["content"])
        assert saved["id"] == application_id
        assert saved["notes"] == "My saved research notes"
        assert saved["benefits"] == "Saved benefit"
        assert saved["requirements"] == [{"label": "Existing reference", "done": True}]
        assert "Unpublished editorial content" not in json.dumps(saved)
        assert events[-2]["message"]["sources"][0]["id"] == application_id


def test_application_tool_does_not_expose_another_members_record(monkeypatch):
    other, _ = _seed(user=True)
    application_id, _ = _saved_application(other)
    calls = _model(
        monkeypatch,
        _tool("get_application", application_id=application_id),
        LLMResponse(text="I cannot access that application."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(f"{path}/chat", json={"content": "Read that application."})
        )
        error = json.loads(calls[1]["messages"][-1]["content"])
        assert error["code"] == "not_found_or_inaccessible"
        assert "My saved research notes" not in json.dumps(error)
        assert not events[-2]["message"]["sources"]


@pytest.mark.parametrize("approved", [True, False])
def test_application_update_is_owned_and_requires_approval(monkeypatch, approved):
    application_id, _ = _saved_application()
    _model(
        monkeypatch,
        _tool(
            "update_application",
            application_id=application_id,
            changes={"benefits": "Verified benefit"},
        ),
        LLMResponse(text="Done."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(f"{path}/chat", json={"content": "Update the saved benefit."})
        )
        pending = next(e["call"] for e in events if e["event"] == "confirm_required")
        assert pending["note"] == "Benefits: Verified benefit"
        endpoint = f"/api/app/applications/{application_id}"
        assert client.get(endpoint).json()["benefits"] == "Saved benefit"
        _events(
            client.post(
                f"{path}/confirm", json={"call_id": pending["id"], "approved": approved}
            )
        )
        saved = client.get(endpoint).json()
        assert saved["benefits"] == (
            "Verified benefit" if approved else "Saved benefit"
        )
        assert saved["requirements"] == [{"label": "Existing reference", "done": True}]


def test_lookup_budget_reserves_a_final_answer_round(monkeypatch):
    monkeypatch.setattr(service, "MAX_STEPS", 2)
    calls = _model(
        monkeypatch,
        _tool("search_catalog", query="absent-record"),
        _tool("search_catalog", query="another-absent-record"),
        LLMResponse(
            text="No published catalog matches were found. Your saved records may still be available."
        ),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(f"{path}/chat", json={"content": "Look for these records."})
        )
        assert calls[-1]["tools"] == []
        assert "tool budget is exhausted" in calls[-1]["system"]
        assert (
            events[-2]["message"]["content"]
            == "No published catalog matches were found. Your saved records may still be available."
        )
        assert events[-2]["message"]["can_continue"] is True
        stored = client.get(path).json()["messages"][-1]
        assert stored["can_continue"] is True


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
    _model(monkeypatch, _tool("add_todo", title=title), LLMResponse(text=""))
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
        receipt = next(e["message"] for e in events if e["event"] == "message")
        assert receipt["sources"] == (
            [
                {
                    "key": "p1",
                    "kind": "todo",
                    "id": todos[0]["id"],
                    "title": title,
                    "detail": "",
                    "url": None,
                    "opportunity": None,
                    "preview": True,
                    "available_at": None,
                }
            ]
            if approved
            else []
        )


def test_private_chat_searches_with_a_query_written_without_private_history(
    monkeypatch,
):
    monkeypatch.setattr(service.web, "search_chain", lambda: [{"configured": True}])
    queries = []

    async def search(query):
        queries.append(query)
        return []

    monkeypatch.setattr(service.web, "search_web", search)
    calls = _model(
        monkeypatch,
        _tool("search_catalog", query="unique-no-match"),
        LLMResponse(
            tool_calls=[
                ToolCall("private", "list_applications"),
                ToolCall("web", "search_web", {"query": "my private application"}),
            ]
        ),
        LLMResponse(text="astronomy research grants Ghana"),
        LLMResponse(text="Nothing public turned up."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(
                f"{path}/chat", json={"content": "Find astronomy grants for me."}
            )
        )
        steps = [e["step"] for e in events if e["event"] == "tool_result"]
        assert steps[-1]["tool"] == "search_web" and steps[-1]["ok"]
    assert queries == ["astronomy research grants Ghana"]
    rewrite = calls[2]
    assert rewrite["tools"] == [] and rewrite["system"] == service.PUBLIC_QUERY
    assert rewrite["messages"] == [
        {"role": "user", "content": "Find astronomy grants for me."}
    ]
    searched = json.loads(calls[3]["messages"][-1]["content"])
    assert searched["query"] == "astronomy research grants Ghana"


def test_a_reply_with_only_thinking_is_asked_once_more(monkeypatch):
    calls = _model(
        monkeypatch,
        LLMResponse(text="", reasoning="I'll greet them back."),
        LLMResponse(text="Hi! What can I help you find?"),
        LLMResponse(text="", reasoning="Greeting."),
        LLMResponse(text="", reasoning="Greeting again."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        first = _events(client.post(f"{path}/chat", json={"content": "hello"}))
        assert first[-2]["message"]["content"] == "Hi! What can I help you find?"
        second = _events(client.post(f"{path}/chat", json={"content": "how are you"}))
        assert second[-2]["message"]["content"] == (
            "I didn't get an answer back this time. Send that again."
        )
    assert len(calls) == 4


def test_private_chat_does_not_repeat_a_query_within_a_reply(monkeypatch):
    monkeypatch.setattr(service.web, "search_chain", lambda: [{"configured": True}])
    queries = []

    async def search(query):
        queries.append(query)
        return []

    monkeypatch.setattr(service.web, "search_web", search)
    calls = _model(
        monkeypatch,
        _tool("search_catalog", query="unique-no-match"),
        LLMResponse(
            tool_calls=[
                ToolCall("private", "list_applications"),
                ToolCall("web", "search_web", {"query": "grant"}),
            ]
        ),
        LLMResponse(text="IIASA summer program"),
        _tool("search_web", query="grant again"),
        LLMResponse(text="iiasa  Summer program"),
        LLMResponse(text="Nothing new."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(client.post(f"{path}/chat", json={"content": "Find IIASA."}))
        steps = [e["step"] for e in events if e["event"] == "tool_result"]
        assert not steps[-1]["ok"]
    assert queries == ["IIASA summer program"]
    assert "Earlier queries: IIASA summer program" in calls[4]["messages"][0]["content"]


def test_private_chat_skips_search_when_no_public_query_fits(monkeypatch):
    monkeypatch.setattr(service.web, "search_chain", lambda: [{"configured": True}])

    async def never_search(*args):
        pytest.fail("No search should run")

    monkeypatch.setattr(service.web, "search_web", never_search)
    _model(
        monkeypatch,
        _tool("search_catalog", query="unique-no-match"),
        LLMResponse(
            tool_calls=[
                ToolCall("private", "list_applications"),
                ToolCall("web", "search_web", {"query": "my application"}),
            ]
        ),
        LLMResponse(text="NONE"),
        LLMResponse(text="I checked your applications."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(f"{path}/chat", json={"content": "Check my applications."})
        )
        steps = [e["step"] for e in events if e["event"] == "tool_result"]
        assert steps[-1]["tool"] == "search_web" and not steps[-1]["ok"]


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
        _tool("track_opportunity", opportunity_id=opp_id),
        LLMResponse(text=""),
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
        receipt = completed[-2]["message"]
        assert receipt["content"] == "Saved to your applications."
        assert [(c["kind"], c["title"], c["preview"]) for c in receipt["sources"]] == [
            ("application", title, True)
        ]
        assert opp_id in client.get("/api/app/opportunities/tracked").json()


def test_retry_answers_the_last_question_again(monkeypatch):
    _model(
        monkeypatch,
        LLMResponse(text="First answer."),
        LLMResponse(text="Second answer."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        _events(client.post(f"{path}/chat", json={"content": "Which grant first?"}))
        events = _events(client.post(f"{path}/retry"))
        assert events[0]["event"] == "user_message"
        assert events[0]["message"]["content"] == "Which grant first?"
        messages = client.get(path).json()["messages"]
        assert [(m["role"], m["content"]) for m in messages] == [
            ("user", "Which grant first?"),
            ("assistant", "Second answer."),
        ]


def test_retry_needs_a_question(monkeypatch):
    _model(monkeypatch)
    with TestClient(app) as client:
        path = _chat(client)
        assert client.post(f"{path}/retry").status_code == 404
        assert client.get(path).json()["running"] is False


def test_application_update_cannot_propose_changes_to_another_members_record(
    monkeypatch,
):
    owner, _ = _seed(user=True)
    application_id, _ = _saved_application(owner)
    calls = _model(
        monkeypatch,
        _tool(
            "update_application",
            application_id=application_id,
            changes={"notes": "Changed"},
        ),
        LLMResponse(text="I cannot update that application."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(f"{path}/chat", json={"content": "Update this application."})
        )
        assert not any(e["event"] == "confirm_required" for e in events)
        error = json.loads(calls[-1]["messages"][-1]["content"])
        assert error["ok"] is False
        assert error["code"] == "not_found_or_inaccessible"
        assert "My saved research notes" not in json.dumps(error)


def test_application_ownership_is_rechecked_when_approving(monkeypatch):
    application_id, _ = _saved_application()
    other, _ = _seed(user=True)
    calls = _model(
        monkeypatch,
        _tool(
            "update_application",
            application_id=application_id,
            changes={"benefits": "Changed"},
        ),
        LLMResponse(text="That application is no longer available."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(
            client.post(f"{path}/chat", json={"content": "Update this application."})
        )
        pending = next(e["call"] for e in events if e["event"] == "confirm_required")

        async def change_owner():
            async with SessionLocal() as session:
                record = await session.get(Application, application_id)
                record.user_id = other
                await session.commit()

        asyncio.run(change_owner())
        events = _events(
            client.post(
                f"{path}/confirm", json={"call_id": pending["id"], "approved": True}
            )
        )
        assert (
            events[-2]["message"]["content"]
            == "That application is no longer available."
        )
        failed = json.loads(calls[-1]["messages"][-1]["content"])
        assert failed["code"] == "change_failed"
        assert failed["ok"] is False

        async def saved_benefits():
            async with SessionLocal() as session:
                return (await session.get(Application, application_id)).benefits

        assert asyncio.run(saved_benefits()) == "Saved benefit"


def _calls(*calls):
    return LLMResponse(
        tool_calls=[ToolCall(new_id(), name, arguments) for name, arguments in calls]
    )


def _last_tool_results(call):
    return [
        json.loads(item["content"])
        for item in call["messages"]
        if item["role"] == "tool"
    ]


def test_approval_hands_the_result_back_and_the_reply_carries_on(monkeypatch):
    title = f"Reference {new_id()}"
    calls = _model(
        monkeypatch,
        _calls(("add_todo", {"title": title}), ("list_todos", {})),
        LLMResponse(text="Added it. You have one open to-do now."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(client.post(f"{path}/chat", json={"content": "Add it."}))
        pending = next(e["call"] for e in events if e["event"] == "confirm_required")
        assert pending["type"] == "change"
        assert pending["action"] == "Approve"
        assert pending["tone"] == "default"
        assert "resume" not in pending
        assert "resume" not in client.get(path).json()["pending_call"]
        events = _events(
            client.post(
                f"{path}/confirm", json={"call_id": pending["id"], "approved": True}
            )
        )
        results = _last_tool_results(calls[-1])
        assert results[-2]["approved"] is True
        assert results[-2]["title"] == title
        assert results[-1]["code"] == "not_run"
        message = events[-2]["message"]
        assert message["content"] == "Added it. You have one open to-do now."
        assert [(s["key"], s["kind"], s["preview"]) for s in message["sources"]] == [
            ("p1", "todo", True)
        ]
        assert message["trace"][-1]["label"] == "Add a to-do"
        thread = client.get(path).json()
        assert thread["pending_call"] is None
        assert [m["role"] for m in thread["messages"]] == ["user", "assistant"]


def test_a_declined_change_tells_the_model_not_to_ask_again(monkeypatch):
    application_id, _ = _saved_application()
    calls = _model(
        monkeypatch,
        _tool("delete_application", application_id=application_id),
        LLMResponse(text="I left it as it is."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(client.post(f"{path}/chat", json={"content": "Delete it."}))
        pending = next(e["call"] for e in events if e["event"] == "confirm_required")
        assert pending["tone"] == "danger"
        assert pending["action"] == "Delete"
        events = _events(
            client.post(
                f"{path}/confirm", json={"call_id": pending["id"], "approved": False}
            )
        )
        declined = _last_tool_results(calls[-1])[-1]
        assert declined["code"] == "declined"
        assert (
            events[-2]["message"]["trace"][-1]["label"]
            == "Delete an application skipped"
        )
        assert client.get(f"/api/app/applications/{application_id}").status_code == 200


def test_each_message_has_a_limit_of_approval_cards(monkeypatch):
    monkeypatch.setattr(service, "MAX_CARDS", 1)
    calls = _model(
        monkeypatch,
        _tool("add_todo", title=f"First {new_id()}"),
        _tool("add_todo", title=f"Second {new_id()}"),
        LLMResponse(text="I added the first one. Ask again for the rest."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(client.post(f"{path}/chat", json={"content": "Add two."}))
        pending = next(e["call"] for e in events if e["event"] == "confirm_required")
        events = _events(
            client.post(
                f"{path}/confirm", json={"call_id": pending["id"], "approved": True}
            )
        )
        assert not any(e["event"] == "confirm_required" for e in events)
        assert "add_todo" not in {tool["name"] for tool in calls[1]["tools"]}
        assert "limit of approval cards" in calls[1]["system"]
        assert _last_tool_results(calls[2])[-1]["code"] == "tool_unavailable"


def test_a_used_up_scan_allowance_shows_a_card_with_the_next_free_time(monkeypatch):
    from datetime import UTC, datetime

    from api.scans import service as scans

    free_at = datetime(2026, 11, 21, 21, 39, tzinfo=UTC)

    async def used_up(session, user_id):
        return {
            "enabled": True,
            "per_hour": 3,
            "left_this_hour": 0,
            "per_day": 10,
            "left_today": 4,
            "next_at": free_at,
        }

    monkeypatch.setattr(scans, "scan_allowance", used_up)
    calls = _model(
        monkeypatch,
        _tool("start_scan", category="student"),
        LLMResponse(text="I can start it once a slot frees up."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(client.post(f"{path}/chat", json={"content": "Scan for me."}))
        assert not any(e["event"] == "confirm_required" for e in events)
        assert "don't repeat the time" in _last_tool_results(calls[1])[-1]["error"]
        [card] = [
            s for s in events[-2]["message"]["sources"] if s["kind"] == "scan_limit"
        ]
        assert card["title"] == "No scans left this hour"
        assert card["available_at"].startswith("2026-11-21T21:39")


QUESTIONS = {
    "title": "A few details before I start the scan",
    "questions": [
        {
            "id": "region",
            "prompt": "Which region?",
            "type": "single",
            "options": ["Ghana", "West Africa"],
            "allow_other": True,
        },
        {
            "id": "kinds",
            "prompt": "What kinds?",
            "type": "multiple",
            "options": ["Grants", "Fellowships", "Prizes"],
            "max_choices": 2,
        },
        {"id": "start", "prompt": "From when?", "type": "date", "required": False},
    ],
}


def test_questions_open_a_questionnaire_and_answers_carry_the_reply_on(monkeypatch):
    calls = _model(
        monkeypatch,
        _tool("ask_member", **QUESTIONS),
        LLMResponse(text="Thanks. I'll look in Kumasi for grants."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(client.post(f"{path}/chat", json={"content": "Scan for me."}))
        pending = next(e["call"] for e in events if e["event"] == "questions_required")
        assert pending["type"] == "questions"
        assert pending["summary"] == QUESTIONS["title"]
        assert [q["id"] for q in pending["questions"]] == ["region", "kinds", "start"]
        assert client.get(path).json()["pending_call"]["type"] == "questions"
        assert client.post(f"{path}/chat", json={"content": "Hi"}).status_code == 409
        decision = {"call_id": pending["id"], "approved": True}
        assert client.post(f"{path}/confirm", json=decision).status_code == 404

        answer = f"{path}/answer"
        for bad in (
            {"kinds": ["Grants"]},
            {"region": "Ghana", "kinds": ["Grants", "Fellowships", "Prizes"]},
            {"region": "Ghana", "kinds": ["Jobs"]},
            {"region": "Ghana", "kinds": ["Grants"], "start": "soon"},
            {"region": "Ghana", "kinds": ["Grants"], "other": "x"},
        ):
            response = client.post(
                answer, json={"call_id": pending["id"], "answers": bad}
            )
            assert response.status_code == 400, bad
        assert (
            client.post(answer, json={"call_id": "old", "answers": {}}).status_code
            == 404
        )

        events = _events(
            client.post(
                answer,
                json={
                    "call_id": pending["id"],
                    "answers": {"region": "Kumasi", "kinds": ["Grants"]},
                },
            )
        )
        answered = next(e for e in events if e["event"] == "questions_answered")
        assert answered["asked"]["content"] == QUESTIONS["title"]
        assert (
            answered["message"]["content"]
            == "Which region?\nKumasi\n\nWhat kinds?\nGrants"
        )
        result = _last_tool_results(calls[-1])[-1]
        assert result["answers"] == {"region": "Kumasi", "kinds": ["Grants"]}
        thread = client.get(path).json()
        assert thread["pending_call"] is None
        assert [(m["role"], m["content"]) for m in thread["messages"]] == [
            ("user", "Scan for me."),
            ("assistant", QUESTIONS["title"]),
            ("user", "Which region?\nKumasi\n\nWhat kinds?\nGrants"),
            ("assistant", "Thanks. I'll look in Kumasi for grants."),
        ]
        assert thread["messages"][-1]["trace"][0]["label"] == "Asked a few questions"


def test_skipping_questions_lets_the_assistant_choose(monkeypatch):
    calls = _model(
        monkeypatch,
        _tool("ask_member", **QUESTIONS),
        LLMResponse(text="I'll scan Ghana for grants."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(client.post(f"{path}/chat", json={"content": "Scan."}))
        pending = next(e["call"] for e in events if e["event"] == "questions_required")
        events = _events(client.post(f"{path}/answer", json={"call_id": pending["id"]}))
        assert _last_tool_results(calls[-1])[-1]["skipped"] is True
        messages = client.get(path).json()["messages"]
        assert messages[2]["content"] == "I skipped the questions."


def test_bad_questions_are_sent_back_to_the_model(monkeypatch):
    calls = _model(
        monkeypatch,
        _tool(
            "ask_member",
            title="Which one?",
            questions=[
                {"id": "pick", "prompt": "Pick", "type": "single", "options": ["Only"]}
            ],
        ),
        LLMResponse(text="Which one do you mean?"),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(client.post(f"{path}/chat", json={"content": "Help."}))
        assert not any(e["event"] == "questions_required" for e in events)
        assert _last_tool_results(calls[-1])[-1]["code"] == "invalid_input"


def test_a_card_saved_before_replies_could_carry_on_still_completes(monkeypatch):
    title = f"Legacy {new_id()}"
    _model(monkeypatch)
    with TestClient(app) as client:
        path = _chat(client)
        chat_id = path.rsplit("/", 1)[1]

        async def legacy():
            from api.assistant.models import AssistantConversation

            async with SessionLocal() as session:
                chat = await session.get(AssistantConversation, chat_id)
                chat.pending = {
                    "id": "legacy-call",
                    "tool": "add_todo",
                    "summary": f"Add “{title}” to your to-dos?",
                    "arguments": {"title": title, "due_date": None},
                    "trace": [],
                    "note": "",
                }
                await session.commit()

        asyncio.run(legacy())
        assert client.get(path).json()["pending_call"]["type"] == "change"
        events = _events(
            client.post(
                f"{path}/confirm", json={"call_id": "legacy-call", "approved": True}
            )
        )
        assert events[-2]["message"]["content"] == "Added to your to-dos."
        assert any(t["title"] == title for t in client.get("/api/app/todos").json())

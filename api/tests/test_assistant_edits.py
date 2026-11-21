from fastapi.testclient import TestClient

from api.agent.llm.base import LLMResponse, ToolCall
from api.core.ids import new_id
from api.main import app
from tests.test_assistant import _chat, _events, _model, _saved_application, _tool


def _ask(client, monkeypatch_calls, text="Do it."):
    path = _chat(client)
    events = _events(client.post(f"{path}/chat", json={"content": text}))
    pending = next(e["call"] for e in events if e["event"] == "confirm_required")
    return path, pending


def _decide(client, path, pending, approved=True):
    events = _events(
        client.post(
            f"{path}/confirm", json={"call_id": pending["id"], "approved": approved}
        )
    )
    return events[-2]["message"]


def test_profile_edit_waits_for_approval_and_keeps_the_rest(monkeypatch):
    _model(
        monkeypatch,
        _tool("enable_changes"),
        _tool(
            "update_profile",
            changes={"headline": "Climate engineer", "skills": ["Python"]},
        ),
    )
    with TestClient(app) as client:
        client.put("/api/app/profile", json={"city": "Accra", "headline": "Old"})
        path, pending = _ask(client, monkeypatch)
        assert pending["summary"] == "Update your profile (headline, skills)?"
        assert "Headline: Climate engineer" in pending["note"]
        assert client.get("/api/app/profile").json()["headline"] == "Old"
        reply = _decide(client, path, pending)
        assert reply["content"] == "Updated your profile."
        saved = client.get("/api/app/profile").json()
        assert saved["headline"] == "Climate engineer"
        assert saved["skills"] == ["Python"]
        assert saved["city"] == "Accra"


def test_declined_edit_changes_nothing(monkeypatch):
    _model(
        monkeypatch,
        _tool("enable_changes"),
        _tool("add_answer", question="Why us?", answer="Because."),
    )
    with TestClient(app) as client:
        before = len(client.get("/api/app/answers").json())
        path, pending = _ask(client, monkeypatch)
        reply = _decide(client, path, pending, approved=False)
        assert reply["content"] == "I left your records as they were."
        assert len(client.get("/api/app/answers").json()) == before


def test_project_added_then_deleted_with_approval(monkeypatch):
    _model(
        monkeypatch,
        _tool("enable_changes"),
        LLMResponse(
            tool_calls=[
                ToolCall(
                    new_id(),
                    "add_project",
                    {"name": "Solar Kiosk", "tagline": "Power for markets"},
                )
            ]
        ),
    )
    with TestClient(app) as client:
        path, pending = _ask(client, monkeypatch)
        reply = _decide(client, path, pending)
        card = reply["sources"][0]
        assert (card["kind"], card["title"]) == ("project", "Solar Kiosk")
        project_id = card["id"]

        _model(
            monkeypatch,
            _tool("enable_changes"),
            _tool("delete_project", project_id=project_id),
        )
        path, pending = _ask(client, monkeypatch)
        assert "can't be undone" in pending["summary"]
        _decide(client, path, pending)
        ids = [p["id"] for p in client.get("/api/app/projects").json()]
        assert project_id not in ids


def test_invalid_edit_is_rejected_before_asking(monkeypatch):
    _model(
        monkeypatch,
        _tool("enable_changes"),
        _tool("update_profile", changes={"linkedin_url": "not a url"}),
        _tool("update_profile", changes={"headline": "Fine"}),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(client.post(f"{path}/chat", json={"content": "Set my link."}))
        asked = [e["call"] for e in events if e["event"] == "confirm_required"]
        assert [c["summary"] for c in asked] == ["Update your profile (headline)?"]


def test_another_members_application_cannot_be_removed(monkeypatch):
    from tests.test_assistant import _seed

    other, _ = _seed(user=True)
    application_id, _ = _saved_application(other)
    _model(
        monkeypatch,
        _tool("enable_changes"),
        _tool("delete_application", application_id=application_id),
        LLMResponse(text="I can't find that application."),
    )
    with TestClient(app) as client:
        path = _chat(client)
        events = _events(client.post(f"{path}/chat", json={"content": "Remove it."}))
        assert not any(e["event"] == "confirm_required" for e in events)
        assert events[-2]["message"]["content"] == "I can't find that application."

from fastapi.testclient import TestClient

from api.agent.llm.base import LLMResponse
from api.main import app
from tests.test_assistant import _chat, _events, _model, _saved_application


def _ask(client, context, text="What is this?"):
    path = _chat(client)
    events = _events(
        client.post(f"{path}/chat", json={"content": text, "context": context})
    )
    return path, events


def test_open_application_is_named_to_the_model(monkeypatch):
    application_id, _ = _saved_application()
    calls = _model(monkeypatch, LLMResponse(text="It is your application."))
    with TestClient(app) as client:
        _ask(
            client,
            {
                "page": f"/applications/{application_id}",
                "application_id": application_id,
                "chips": [
                    {"key": "application", "label": "Application", "detail": "Grant"}
                ],
            },
        )
    system = calls[0]["system"]
    assert "[Page context" in system
    assert f"id {application_id}" in system


def test_chips_are_kept_on_the_message_and_reused_on_retry(monkeypatch):
    application_id, _ = _saved_application()
    calls = _model(monkeypatch, LLMResponse(text="First."), LLMResponse(text="Second."))
    chip = {"key": "application", "label": "Application", "detail": "Grant"}
    with TestClient(app) as client:
        path, events = _ask(client, {"application_id": application_id, "chips": [chip]})
        user = next(e for e in events if e["event"] == "user_message")["message"]
        assert user["chips"] == [chip]
        _events(client.post(f"{path.replace('/chat', '')}/retry"))
    assert f"id {application_id}" in calls[1]["system"]


def test_another_members_record_is_not_revealed(monkeypatch):
    from tests.test_assistant import _seed

    other, _ = _seed(user=True)
    application_id, _ = _saved_application(other)
    calls = _model(monkeypatch, LLMResponse(text="I can't tell."))
    with TestClient(app) as client:
        _ask(client, {"application_id": application_id})
    assert application_id not in calls[0]["system"]


def test_private_context_blocks_web_search(monkeypatch):
    application_id, _ = _saved_application()
    calls = _model(monkeypatch, LLMResponse(text="Done."))
    with TestClient(app) as client:
        _ask(client, {"application_id": application_id})
    assert "search_web" not in {t["name"] for t in calls[0]["tools"]}


def test_context_is_optional_and_bounded(monkeypatch):
    _model(monkeypatch, LLMResponse(text="Hi."))
    with TestClient(app) as client:
        path = _chat(client)
        too_long = client.post(
            f"{path}/chat",
            json={"content": "Hi", "context": {"selection": "x" * 5001}},
        )
        assert too_long.status_code == 422
        assert _events(client.post(f"{path}/chat", json={"content": "Hi"}))

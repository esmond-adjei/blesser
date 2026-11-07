import asyncio

from api.assistant import live
from tests.test_assistant import ScriptProvider, _client, _sse_events


def test_turn_keeps_running_when_its_reader_hangs_up():
    finished = []

    async def turn():
        for i in range(3):
            await asyncio.sleep(0.01)
            yield {"event": "token", "text": str(i)}
        finished.append(True)

    async def scenario():
        running = live.start("conv-live-1", "user-1", turn(), lambda exc: {"event": "error"})
        first = running.follow()
        assert (await anext(first))["text"] == "0"
        await first.aclose()  # the browser reloads
        await running.task
        assert [e["text"] async for e in running.follow()] == ["0", "1", "2"]

    asyncio.run(scenario())
    assert finished == [True]
    assert not live.running("conv-live-1")


def test_stop_cancels_the_turn_and_runs_its_cleanup():
    cleaned = []

    async def turn():
        try:
            yield {"event": "token", "text": "partial"}
            await asyncio.sleep(60)
        finally:
            cleaned.append(True)

    async def scenario():
        running = live.start("conv-live-2", "user-1", turn(), lambda exc: {"event": "error"})
        await asyncio.sleep(0.01)
        assert await live.stop("conv-live-2") is True
        assert [e["event"] async for e in running.follow()] == ["token", "stopped"]
        assert await live.stop("conv-live-2") is False

    asyncio.run(scenario())
    assert cleaned == [True]


def test_failed_turn_ends_with_the_error_event():
    async def turn():
        yield {"event": "token", "text": "hi"}
        raise RuntimeError("boom")

    async def scenario():
        running = live.start("conv-live-3", "user-1", turn(), lambda exc: {"event": "error", "message": type(exc).__name__})
        await running.task
        return [e async for e in running.follow()]

    assert asyncio.run(scenario())[-1] == {"event": "error", "message": "RuntimeError"}


def test_chat_routes_follow_stop_and_context_chips(monkeypatch):
    import api.assistant.service as gradis

    monkeypatch.setattr(gradis, "get_provider", lambda: ScriptProvider([(["Here you go."], [])]))
    chips = [{"key": "run", "label": "Run", "detail": "a1b2c3"}, {"key": "page", "label": "Page", "detail": "/runs/a1b2c3"}]
    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        assert client.get(f"/api/assistant/conversations/{conv_id}/live").status_code == 404
        assert client.post(f"/api/assistant/conversations/{conv_id}/stop").json() == {"stopped": False}
        resp = client.post(
            f"/api/assistant/conversations/{conv_id}/chat",
            json={"content": "summarise this run", "context": {"page": "/runs/a1b2c3", "chips": chips}},
        )
        assert resp.status_code == 200, resp.text
        assert _sse_events(resp.text)[-1][0] == "done"
        conv = client.get(f"/api/assistant/conversations/{conv_id}").json()
    assert conv["running"] is False
    user, reply = conv["messages"]
    assert user["context"] == chips
    assert reply["content"] == "Here you go." and not reply.get("context")

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.core.db import SessionLocal
from api.main import app
from api.providers import models as providers_models
from api.providers import service as providers_service
from tests.conftest import TEST_USER_ID


@pytest.fixture(autouse=True)
def _clean_providers():
    async def _wipe():
        async with SessionLocal() as session:
            await session.execute(delete(providers_models.ProviderConfig))
            await session.commit()

    asyncio.run(_wipe())
    yield
    asyncio.run(_wipe())


def _client():
    return TestClient(app)


def test_list_seeds_supported_providers_without_keys():
    client = _client()
    rows = client.get("/api/providers").json()
    assert {r["provider"] for r in rows} >= {"anthropic", "openai", "ollama"}
    assert all(r["has_key"] is False for r in rows)
    assert all(r["is_active"] is False for r in rows)
    assert all("api_key" not in r for r in rows)


def test_update_model_key_and_active_is_exclusive():
    client = _client()
    updated = client.patch(
        "/api/providers/ollama",
        json={
            "model": "qwen3:8b",
            "api_key": "test-key",
            "base_url": "http://localhost:11434/v1",
            "is_active": True,
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["model"] == "qwen3:8b"
    assert body["has_key"] is True
    assert body["is_active"] is True

    second = client.patch(
        "/api/providers/openai", json={"model": "gpt-5-mini", "is_active": True}
    )
    assert second.status_code == 200, second.text
    rows = {r["provider"]: r for r in client.get("/api/providers").json()}
    assert rows["openai"]["is_active"] is True
    assert rows["ollama"]["is_active"] is False
    assert rows["ollama"]["has_key"] is True

    cleared = client.patch("/api/providers/ollama", json={"api_key": ""})
    assert cleared.json()["has_key"] is False

    assert client.patch("/api/providers/nope", json={"model": "x"}).status_code == 404


def test_resolve_active_config_prefers_db_then_env():
    async def check():
        async with SessionLocal() as session:
            assert (
                await providers_service.resolve_active_config(session, TEST_USER_ID)
                is None
            )
            await providers_service.update_config(
                session,
                TEST_USER_ID,
                "ollama",
                {"model": "qwen3:8b", "is_active": True},
            )
            cfg = await providers_service.resolve_active_config(session, TEST_USER_ID)
            assert cfg is not None
            assert cfg["provider"] == "ollama"
            assert cfg["model"] == "qwen3:8b"

    asyncio.run(check())


def test_connection_uses_explicit_credentials(monkeypatch):
    calls = []

    async def fake_get_json(url, headers):
        calls.append((url, headers))
        return 200, {"data": [{"id": "qwen3:8b"}, {"id": "llama3.1"}]}

    monkeypatch.setattr(providers_service, "_get_json", fake_get_json)

    async def check():
        async with SessionLocal() as session:
            result = await providers_service.test_connection(
                session, TEST_USER_ID, "ollama", base_url="http://localhost:11434/v1"
            )
            assert result["ok"] is True
            assert result["models"] == ["qwen3:8b", "llama3.1"]
            assert result["count"] == 2
            bad = await providers_service.test_connection(
                session, TEST_USER_ID, "openai-compatible"
            )
            assert bad["ok"] is False
            assert "base URL" in (bad["error"] or "")

    asyncio.run(check())
    assert calls and calls[0][0].endswith("/models")


OPERATOR_KEY = "operator-marker-key"


def _capture_server():
    """Local fake upstream that records every Authorization header and
    answers a minimal chat completion."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(self.headers.get("Authorization", ""))
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            body = json.dumps(
                {
                    "id": "x",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "m",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "ok"},
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def _operator_env(monkeypatch, provider="anthropic", base_url=None):
    from api.core.config import settings

    monkeypatch.setattr(settings, "llm_provider", provider)
    monkeypatch.setattr(settings, "llm_api_key", OPERATOR_KEY)
    monkeypatch.setattr(settings, "llm_base_url", base_url)


def test_custom_base_url_row_never_receives_operator_key(monkeypatch, prefer_own_model):
    from api.agent.llm.factory import get_provider
    from api.core.config import settings

    _operator_env(monkeypatch)
    # The fake upstream is local: allowlist it past the egress guard.
    monkeypatch.setattr(settings, "allowed_provider_hosts", "127.0.0.1")
    server, seen = _capture_server()
    base = f"http://127.0.0.1:{server.server_port}/v1"

    async def check():
        async with SessionLocal() as session:
            await providers_service.update_config(
                session,
                TEST_USER_ID,
                "openai-compatible",
                {"model": "m", "base_url": base, "is_active": True},
            )
            kwargs = await providers_service.resolve_llm_kwargs(session, TEST_USER_ID)
            assert kwargs["base_url"] == base
            assert kwargs["api_key"] == ""
            provider = get_provider(**kwargs)
            await provider.chat([{"role": "user", "content": "hi"}], "", [])

    try:
        asyncio.run(check())
    finally:
        server.shutdown()
    assert seen, "the fake upstream was never called"
    assert all(OPERATOR_KEY not in h for h in seen)


def test_keyless_row_on_system_provider_and_base_keeps_operator_key(monkeypatch, prefer_own_model):
    _operator_env(monkeypatch, provider="openai")

    async def check():
        async with SessionLocal() as session:
            await providers_service.update_config(
                session, TEST_USER_ID, "openai", {"model": "gpt-x", "is_active": True}
            )
            kwargs = await providers_service.resolve_llm_kwargs(session, TEST_USER_ID)
            assert kwargs["api_key"] == OPERATOR_KEY
            assert kwargs["base_url"] == "https://api.openai.com/v1"

            # Same provider, user-chosen host: the operator key stays home.
            await providers_service.update_config(
                session,
                TEST_USER_ID,
                "openai",
                {"base_url": "https://attacker.invalid/v1"},
            )
            steered = await providers_service.resolve_llm_kwargs(session, TEST_USER_ID)
            assert steered["api_key"] == ""

            picked = await providers_service.resolve_llm_kwargs(
                session, TEST_USER_ID, "openai"
            )
            assert picked["api_key"] == ""

    asyncio.run(check())


def test_keyless_row_for_other_provider_gets_no_operator_key(monkeypatch, prefer_own_model):
    _operator_env(monkeypatch, provider="anthropic")

    async def check():
        async with SessionLocal() as session:
            await providers_service.update_config(
                session,
                TEST_USER_ID,
                "ollama",
                {"model": "llama3.1", "is_active": True},
            )
            kwargs = await providers_service.resolve_llm_kwargs(session, TEST_USER_ID)
            assert kwargs["api_key"] == ""

    asyncio.run(check())


def test_saved_row_key_is_used_as_is(monkeypatch, prefer_own_model):
    _operator_env(monkeypatch)

    async def check():
        async with SessionLocal() as session:
            await providers_service.update_config(
                session,
                TEST_USER_ID,
                "openai-compatible",
                {
                    "model": "m",
                    "api_key": "user-own-key",
                    "base_url": "https://example.invalid/v1",
                    "is_active": True,
                },
            )
            kwargs = await providers_service.resolve_llm_kwargs(session, TEST_USER_ID)
            assert kwargs["api_key"] == "user-own-key"

    asyncio.run(check())


def test_context_window_is_set_once_and_follows_the_model():
    client = _client()
    saved = client.patch(
        "/api/providers/ollama", json={"model": "qwen3:8b", "context_window": 32768}
    ).json()
    assert saved["context_window"] == 32768
    assert client.patch("/api/providers/ollama", json={"enabled": True}).json()["context_window"] == 32768
    assert client.patch("/api/providers/ollama", json={"model": "qwen3:8b"}).json()["context_window"] == 32768
    info = client.get("/api/assistant/model-info", params={"provider": "ollama"}).json()
    assert info["model"] == "qwen3:8b"
    assert info["context_window"] == 32768
    assert client.patch("/api/providers/ollama", json={"model": "llama3"}).json()["context_window"] is None
    assert client.patch("/api/providers/ollama", json={"context_window": 8192}).json()["context_window"] == 8192
    assert client.patch("/api/providers/ollama", json={"context_window": None}).json()["context_window"] is None
    assert client.patch("/api/providers/ollama", json={"context_window": 0}).status_code == 422


def test_system_model_context_window_comes_from_the_environment(monkeypatch):
    from api.core.config import settings

    monkeypatch.setattr(settings, "llm_context_window", 200_000)
    client = _client()
    assert client.get("/api/providers/catalog").json()["system"]["context_window"] == 200_000
    info = client.get("/api/assistant/model-info", params={"provider": "system"}).json()
    assert info["context_window"] == 200_000

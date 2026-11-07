import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from api.agent.llm.factory import get_provider
from api.core import egress
from api.core.config import settings
from api.main import app
from api.prospects import web
from api.providers import service as providers_service

PUBLIC = "93.184.216.34"


def _dns(monkeypatch, table: dict[str, str]):
    async def resolve(host, port):
        if host not in table:
            raise OSError("no such host")
        return [table[host]]

    monkeypatch.setattr(egress, "_resolve", resolve)


def _fetch_mock(monkeypatch, handler):
    seen: list[str] = []

    def record(req):
        seen.append(str(req.url))
        return handler(req)

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    monkeypatch.setattr(web, "fetch_client", lambda: client)
    return seen


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/ready",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://100.64.0.1/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://localhost/",
        "http://db:5432/",
        "file:///etc/passwd",
        "http://user:pw@example.edu/",
    ],
)
def test_fetch_page_refuses_internal_targets(monkeypatch, url):
    _dns(monkeypatch, {"localhost": "127.0.0.1", "db": "172.18.0.2"})
    seen = _fetch_mock(monkeypatch, lambda req: httpx.Response(200, text="secret"))
    text = asyncio.run(web.fetch_page(url))
    assert text.startswith("[Could not fetch: that address is not allowed")
    assert seen == []


def test_redirect_to_loopback_is_refused(monkeypatch):
    _dns(monkeypatch, {"uni.example": PUBLIC})

    def handler(req):
        if req.url.host == "uni.example":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/"})
        return httpx.Response(200, text="internal")

    seen = _fetch_mock(monkeypatch, handler)
    text = asyncio.run(web.fetch_page("https://uni.example/faculty"))
    assert "not allowed" in text
    assert seen == ["https://uni.example/faculty"]


def test_public_redirects_are_followed(monkeypatch):
    _dns(monkeypatch, {"uni.example": PUBLIC, "www.uni.example": PUBLIC})
    page = "<html><body><article><p>Faculty: Prof. Ada Lovelace, robotics.</p></article></body></html>"

    def handler(req):
        if req.url.host == "uni.example":
            return httpx.Response(
                301, headers={"location": "https://www.uni.example/people"}
            )
        return httpx.Response(200, text=page)

    _fetch_mock(monkeypatch, handler)
    assert "Ada Lovelace" in asyncio.run(web.fetch_page("https://uni.example/"))


def test_body_is_capped(monkeypatch):
    _dns(monkeypatch, {"uni.example": PUBLIC})
    monkeypatch.setattr(settings, "fetch_max_bytes", 1000)
    _fetch_mock(monkeypatch, lambda req: httpx.Response(200, text="x" * 50_000))

    async def run():
        async with web._fetch_sem():
            _, text = await egress.safe_get(
                web.fetch_client(), "https://uni.example/", max_bytes=1000
            )
        return text

    assert len(asyncio.run(run())) == 1000


@pytest.mark.parametrize(
    "base_url",
    [
        "http://10.0.0.1/v1",
        "https://10.0.0.1/v1",
        "https://169.254.169.254/v1",
        "https://api.example.com/v1?",
        "https://api.example.com/v1#",
        "https://user:pw@api.example.com/v1",
        "http://api.example.com/v1",
    ],
)
def test_patch_rejects_unsafe_base_urls(base_url):
    client = TestClient(app)
    resp = client.patch("/api/providers/openai-compatible", json={"base_url": base_url})
    assert resp.status_code == 422, resp.text


def test_patch_accepts_https_default_and_allowlisted(monkeypatch):
    client = TestClient(app)
    ok = client.patch(
        "/api/providers/openai-compatible",
        json={"base_url": "https://api.together.xyz/v1"},
    )
    assert ok.status_code == 200, ok.text
    default = client.patch(
        "/api/providers/ollama", json={"base_url": "http://localhost:11434/v1"}
    )
    assert default.status_code == 200, default.text
    monkeypatch.setattr(settings, "allowed_provider_hosts", "vllm.internal:8000")
    allowed = client.patch(
        "/api/providers/openai-compatible",
        json={"base_url": "http://vllm.internal:8000/v1"},
    )
    assert allowed.status_code == 200, allowed.text


def test_connection_test_refuses_private_hosts(monkeypatch):
    _dns(monkeypatch, {"sneaky.example": "10.1.2.3"})
    client = TestClient(app)
    for base in ("http://127.0.0.1:5432", "https://sneaky.example/v1"):
        body = client.post(
            "/api/providers/openai-compatible/test", json={"base_url": base}
        ).json()
        assert body["ok"] is False
        assert body["error"]


def test_guarded_provider_client_refuses_private_resolution(monkeypatch):
    _dns(monkeypatch, {"sneaky.example": "10.1.2.3"})
    kwargs = providers_service._factory_kwargs(
        "openai-compatible", "m", "k", "https://sneaky.example/v1"
    )
    assert kwargs["egress_guard"] is True
    provider = get_provider(**kwargs)

    async def call():
        await provider.chat([{"role": "user", "content": "hi"}], "", [])

    with pytest.raises(Exception) as info:
        asyncio.run(call())
    chain, exc = [], info.value
    while exc is not None:
        chain.append(exc)
        exc = exc.__cause__ or exc.__context__
    assert any(isinstance(e, egress.EgressBlocked) for e in chain)


def test_default_and_allowlisted_bases_are_not_guarded(monkeypatch):
    assert "egress_guard" not in providers_service._factory_kwargs(
        "ollama", "m", "", ""
    )
    monkeypatch.setattr(settings, "allowed_provider_hosts", "vllm.internal:8000")
    kwargs = providers_service._factory_kwargs(
        "openai-compatible", "m", "", "http://vllm.internal:8000/v1"
    )
    assert "egress_guard" not in kwargs


def test_public_error_never_echoes_upstream_bodies():
    req = httpx.Request("POST", "https://up.example/v1/chat")
    resp = httpx.Response(400, request=req, text="MARKER-BODY from internal host")
    exc = httpx.HTTPStatusError("MARKER-BODY", request=req, response=resp)
    text = egress.public_error(exc)
    assert "MARKER-BODY" not in text and "400" in text

    class APIStatusError(Exception):
        status_code = 502

    assert "MARKER" not in egress.public_error(APIStatusError("MARKER-BODY"))
    assert egress.public_error(RuntimeError("key missing")) == "key missing"


def test_public_error_says_what_to_do_about_common_provider_failures():
    class BadRequestError(Exception):
        status_code = 400

    class AuthenticationError(Exception):
        status_code = 401

    broke = egress.public_error(BadRequestError("Your credit balance is too low to access the Anthropic API. MARKER"))
    assert "out of credit" in broke and "400" in broke and "MARKER" not in broke
    assert "API key" in egress.public_error(AuthenticationError("MARKER"))
    assert egress.public_error(BadRequestError("MARKER")).endswith("HTTP 400.")

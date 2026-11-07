import asyncio

import httpx
import pytest

from api.candidates import scoring
from api.core import egress
from api.core.config import settings
from api.core.ttlcache import TTLCache
from api.prospects import openalex, web


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    async def resolve(host, port):
        return ["93.184.216.34"]

    monkeypatch.setattr(egress, "_resolve", resolve)


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_ttl_cache_expires_and_evicts_oldest_used():
    ttl = {"s": 60.0}
    cache: TTLCache[int] = TTLCache(2, lambda: ttl["s"])
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1  # "a" is now the most recently used
    cache.put("c", 3)
    assert cache.get("b") is None and cache.get("a") == 1 and cache.get("c") == 3
    ttl["s"] = 0  # switched off: nothing is served
    assert cache.get("a") is None


def test_search_reuses_a_recent_identical_query(monkeypatch):
    monkeypatch.setattr(settings, "search_providers", "tavily")
    monkeypatch.setattr(settings, "tavily_api_key", "t")
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(
            200, json={"results": [{"title": "A", "url": "https://a", "content": "x"}]}
        )

    client = _client(handler)
    monkeypatch.setattr(web, "search_client", lambda: client)
    first = asyncio.run(web.search_web("MIT robotics faculty"))
    again = asyncio.run(web.search_web("mit robotics faculty "))
    assert calls["n"] == 1
    assert first[0]["source"] == "tavily"
    assert again[0]["source"] == "cache:tavily" and "stale" not in again[0]


def test_search_tool_reuse_skips_the_search_quota(monkeypatch):
    import importlib
    from types import SimpleNamespace

    dispatch_module = importlib.import_module("api.agent.tools.dispatch")

    web._cache_put("ucl robotics", "brave", [{"title": "T", "url": "https://t"}])

    async def refuse(*_args, **_kwargs):
        raise AssertionError("a reused result must not reach the quota gate")

    monkeypatch.setattr(dispatch_module.billing, "tool_call_refusal", refuse)
    out = asyncio.run(
        dispatch_module._search_web({"query": "UCL robotics"}, SimpleNamespace(user_id="u"))
    )
    assert out["results"][0]["source"] == "cache:brave"


def test_page_is_fetched_once_and_reused(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(
            200,
            text="<html><body><article><p>Faculty: Ada Lovelace, robotics.</p></article></body></html>",
        )

    client = _client(handler)
    monkeypatch.setattr(web, "fetch_client", lambda: client)
    first = asyncio.run(web.fetch_page("https://uni.example/faculty"))
    second = asyncio.run(web.fetch_page("https://uni.example/faculty"))
    assert "Ada Lovelace" in first and first == second
    assert calls["n"] == 1


def test_openalex_success_is_cached_and_failure_is_not(monkeypatch):
    monkeypatch.setattr(openalex, "_RETRY_DELAYS", ())
    state = {"n": 0, "up": False}

    def handler(req):
        state["n"] += 1
        if not state["up"]:
            return httpx.Response(503)
        return httpx.Response(200, json={"results": [{"id": "A1"}]})

    client = _client(handler)
    monkeypatch.setattr(openalex, "client", lambda: client)
    with pytest.raises(openalex.OpenAlexUnavailable):
        asyncio.run(openalex._get_json("/authors", {"search": "Ada"}))
    state["up"] = True
    first = asyncio.run(openalex._get_json("/authors", {"search": "Ada"}))
    first["results"].clear()  # a caller changing its copy can't touch the cache
    again = asyncio.run(openalex._get_json("/authors", {"search": "Ada"}))
    assert again == {"results": [{"id": "A1"}]}
    assert state["n"] == 2  # the failure, then one success


def test_embeddings_send_only_texts_not_seen(monkeypatch):
    sent: list[list[str]] = []

    def fake(texts, input_type="query"):
        sent.append(list(texts))
        return [[float(len(t)), 1.0] for t in texts]

    monkeypatch.setattr(scoring, "_embed_uncached", fake)
    first = scoring.embed_texts(["alpha", "beta"])
    second = scoring.embed_texts(["beta", "gamma", "alpha"])
    assert sent == [["alpha", "beta"], ["gamma"]]
    assert first == [[5.0, 1.0], [4.0, 1.0]]
    assert second == [[4.0, 1.0], [5.0, 1.0], [5.0, 1.0]]
    monkeypatch.setattr(settings, "embedding_model", "other-model")
    scoring.embed_texts(["alpha"])
    assert sent[-1] == ["alpha"]


def test_query_and_document_vectors_are_cached_apart(monkeypatch):
    sent: list[tuple[str, list[str]]] = []

    def fake(texts, input_type="query"):
        sent.append((input_type, list(texts)))
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(scoring, "_embed_uncached", fake)
    scoring.embed_texts(["robots"])
    scoring.embed_texts(["robots"], input_type="document")
    # Voyage embeds the two differently: a query vector is never reused
    # as a document vector.
    assert sent == [("query", ["robots"]), ("document", ["robots"])]

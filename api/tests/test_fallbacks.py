import asyncio

import httpx
import pytest

from api import web
from api.core import egress
from api.core.config import settings

DDG_HTML = """<html><body>
<div class="result results_links"><h2><a class="result__a"
 href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fethz.ch%2Frobotics">ETH Robotics PhD</a></h2>
<a class="result__snippet">Doctoral programme in robotics.</a></div>
</body></html>"""


def _mock(monkeypatch, handler, target="search"):
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    )
    if target == "search":
        monkeypatch.setattr(web, "search_client", lambda: client)
    else:
        monkeypatch.setattr(web, "fetch_client", lambda: client)


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    """Mocked hosts don't resolve; treat them as public for the egress guard."""

    async def resolve(host, port):
        return ["93.184.216.34"]

    monkeypatch.setattr(egress, "_resolve", resolve)


@pytest.fixture(autouse=True)
def _chain(monkeypatch):
    web._CACHE.clear()
    monkeypatch.setattr(settings, "search_providers", "tavily,brave,duckduckgo")
    monkeypatch.setattr(settings, "tavily_api_key", "t")
    monkeypatch.setattr(settings, "brave_api_key", "b")


def test_next_provider_answers_when_first_fails(monkeypatch):
    def handler(req):
        if "tavily" in req.url.host:
            return httpx.Response(500)
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [{"title": "T", "url": "https://u", "description": "d"}]
                }
            },
        )

    _mock(monkeypatch, handler)
    results = asyncio.run(web.search_web("robotics phd"))
    assert results == [
        {"title": "T", "url": "https://u", "snippet": "d", "source": "brave"}
    ]


def test_keyless_duckduckgo_is_the_last_resort(monkeypatch):
    def handler(req):
        if "duckduckgo" in req.url.host:
            return httpx.Response(200, text=DDG_HTML)
        return httpx.Response(429)

    _mock(monkeypatch, handler)
    [r] = asyncio.run(web.search_web("eth robotics"))
    assert r["url"] == "https://ethz.ch/robotics" and r["source"] == "duckduckgo"
    assert r["snippet"] == "Doctoral programme in robotics."


def test_cache_then_honest_unavailability(monkeypatch):
    monkeypatch.setattr(settings, "search_reuse_seconds", 0)
    calls = {"ok": True}

    def handler(req):
        if calls["ok"] and "tavily" in req.url.host:
            return httpx.Response(
                200,
                json={"results": [{"title": "A", "url": "https://a", "content": "x"}]},
            )
        return httpx.Response(503)

    _mock(monkeypatch, handler)
    assert asyncio.run(web.search_web("Same Query"))[0]["source"] == "tavily"
    calls["ok"] = False
    stale = asyncio.run(web.search_web("same query"))
    assert stale[0]["source"] == "cache:tavily" and stale[0]["stale"] is True
    with pytest.raises(web.SearchUnavailable, match="tried: tavily"):
        asyncio.run(web.search_web("never seen before"))


def test_fetch_falls_back_to_the_archive_with_a_note(monkeypatch):
    monkeypatch.setattr(settings, "fetch_cache_seconds", 0)  # fetch each time

    def handler(req):
        if req.url.host == "web.archive.org":
            return httpx.Response(
                200,
                text="<html><body><article><p>Faculty: Prof. Ada Lovelace, robotics.</p></article></body></html>",
            )
        return httpx.Response(403)

    _mock(monkeypatch, handler, "fetch")
    text = asyncio.run(web.fetch_page("https://uni.example/faculty"))
    assert text.startswith("[Live page unavailable") and "Ada Lovelace" in text
    monkeypatch.setattr(settings, "fetch_fallbacks", "")
    assert asyncio.run(web.fetch_page("https://uni.example/faculty")).startswith(
        "[Could not fetch"
    )

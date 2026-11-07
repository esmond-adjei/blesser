import asyncio
import types

from api.agent.tools import ToolContext
from api.agent.tools.dispatch import HANDLERS
from api.core.config import settings
from api.prospects import grounding, openalex, web
from tests.conftest import TEST_USER_ID

LONG = " ".join(f"word{i}" for i in range(400))


def _ctx():
    return ToolContext(session=None, run=types.SimpleNamespace(user_id=TEST_USER_ID))  # type: ignore[arg-type]


def test_searches_show_five_short_results():
    results = [{"title": f"T{i}", "url": f"https://u.example/{i}", "snippet": LONG} for i in range(8)]
    brief = web.brief_results(results)
    assert len(brief) == settings.search_results_for_model == 5
    for r in brief:
        assert len(r["snippet"]) <= settings.search_snippet_chars + 1
        assert r["snippet"].endswith("…") and LONG.startswith(r["snippet"][:-1])
    assert brief[0]["url"] == "https://u.example/0"
    assert web.brief_results([{"title": "a", "url": "u", "snippet": "  short\n  text "}])[0]["snippet"] == "short text"
    assert web.brief_results([{"title": "a", "url": "u"}])[0]["snippet"] == ""


def test_the_search_tool_returns_the_brief_results(monkeypatch):
    async def search(query, max_results=8):
        return [{"title": f"T{i}", "url": f"https://u.example/{i}", "snippet": LONG, "source": "tavily"} for i in range(8)]

    async def allowed(*args, **kwargs):
        return None

    from api.billing import service as billing

    monkeypatch.setattr(web, "search_web", search)
    monkeypatch.setattr(billing, "tool_call_refusal", allowed)
    out = asyncio.run(HANDLERS["search_web"]({"query": "robotics faculty"}, _ctx()))
    assert len(out["results"]) == 5
    assert out["results"][0]["source"] == "tavily"
    assert all(len(r["snippet"]) <= 201 for r in out["results"])


def test_the_research_agent_reads_short_abstracts_but_scoring_keeps_them_whole(monkeypatch):
    works = [{"title": "Legged robots on rough terrain", "abstract": LONG, "year": 2024, "venue": "ICRA", "url": None}]

    async def recent(openalex_id, limit=15, years=None):
        return [dict(w) for w in works]

    monkeypatch.setattr(openalex, "get_recent_works", recent)
    ctx = _ctx()
    out = asyncio.run(HANDLERS["get_author_works"]({"openalex_id": "A1"}, ctx))
    shown = out["works"][0]["abstract"]
    assert len(shown) <= settings.works_abstract_chars + 1 and shown.endswith("…")
    assert out["works"][0]["venue"] == "ICRA" and out["works"][0]["title"] == works[0]["title"]
    assert ctx.works_by_author[grounding.canonical_openalex_id("A1")][0]["abstract"] == LONG
    full = asyncio.run(HANDLERS["get_author_works"]({"openalex_id": "A1", "full": True}, ctx))
    assert full["works"][0]["abstract"] == LONG


def test_works_carry_their_venue(monkeypatch):
    async def fetched(path, params):
        return {
            "results": [
                {
                    "title": "Paper",
                    "publication_year": 2025,
                    "primary_location": {"landing_page_url": "https://doi.example/1", "source": {"display_name": "NeurIPS"}},
                    "id": "https://openalex.org/W1",
                }
            ]
        }

    monkeypatch.setattr(openalex, "_get_json", fetched)
    works = asyncio.run(openalex.get_recent_works("A1"))
    assert works[0]["venue"] == "NeurIPS" and works[0]["url"] == "https://doi.example/1"
    assert openalex.brief_works([{"title": "x", "abstract": None}])[0]["abstract"] is None

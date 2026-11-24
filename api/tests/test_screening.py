import asyncio
from types import SimpleNamespace as N

from api.opportunities import screening
from api.opportunities.page_content import Page


def answers(category="research", region="eligible", open_="open", conf=0.97):
    return {
        "category": N(choice=category, confidence=conf),
        "region": N(choice=region, confidence=conf),
        "open": N(choice=open_, confidence=conf),
    }


def test_screen_skips_only_what_it_is_sure_of():
    decide = screening.decide
    assert decide(answers(), "research", 0.9).skip is None
    assert decide(answers(open_="closed"), "research", 0.9).skip == "deadline_passed"
    assert decide(answers(region="excluded"), "research", 0.9).skip == "region_excluded"
    deferred = decide(answers(category="student"), "research", 0.9)
    assert deferred.skip == "category_deferred" and deferred.category == "student"
    assert decide(answers(open_="closed", conf=0.6), "research", 0.9).skip is None
    assert decide(answers(category=screening.NOT_ONE), "research", 0.9).skip is None


def test_screen_off_or_failing_lets_extraction_run(monkeypatch):
    page = Page(url="https://example.org/x", title="x", text="Grant", content_hash="h")
    monkeypatch.setattr(screening.settings, "screen_with_jev", False)
    assert (
        asyncio.run(
            screening.screen_page(
                page, category="research", region="Ghana", today="2026-11-23"
            )
        ).skip
        is None
    )

    class Broken:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            raise RuntimeError("down")

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(screening.settings, "screen_with_jev", True)
    monkeypatch.setattr(screening.settings, "typesafe_api_key", "test")
    monkeypatch.setattr(screening, "AsyncTypeSafeClient", Broken)
    assert (
        asyncio.run(
            screening.screen_page(
                page, category="research", region="Ghana", today="2026-11-23"
            )
        ).skip
        is None
    )

import asyncio
from datetime import timedelta

import httpx
import pytest

from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.prospects import openalex
from api.prospects.models import OpenAlexResponse

pytestmark = pytest.mark.openalex_store

ROSTER = [
    {"id": "https://openalex.org/A1", "display_name": "Jane Q. Smith", "works_count": 120},
    {"id": "https://openalex.org/A2", "display_name": "Hiroshi Tanaka", "display_name_alternatives": ["Tanaka Hiroshi"], "works_count": 90},
    {"id": "https://openalex.org/A3", "display_name": "José Álvarez", "works_count": 40},
    {"id": "https://openalex.org/A4", "display_name": "Wei Wang", "works_count": 30},
    {"id": "https://openalex.org/A5", "display_name": "Wang Wei", "works_count": 20},
]


@pytest.fixture(autouse=True)
def _empty_store():
    async def clear():
        async with SessionLocal() as session:
            await session.execute(OpenAlexResponse.__table__.delete())
            await session.commit()

    asyncio.run(clear())
    yield
    asyncio.run(clear())


@pytest.mark.parametrize(
    ("name", "found"),
    [
        ("Jane Smith", ["A1"]),
        ("Smith, Jane", ["A1"]),
        ("Prof. Hiroshi Tanaka", ["A2"]),
        ("Tanaka Hiroshi", ["A2"]),
        ("Jose Alvarez", ["A3"]),
        ("Wei Wang", ["A4", "A5"]),  # two people: the caller disambiguates
        ("Ada Lovelace", []),
        ("Smith", []),
    ],
)
def test_names_are_matched_against_the_school_list(name, found):
    matched = openalex.roster_matches(name, ROSTER)
    assert [m["id"].rsplit("/", 1)[-1] for m in matched] == found


def test_a_professor_on_the_list_needs_no_search(monkeypatch):
    calls = []

    async def fetch(path, params):
        calls.append(dict(params))
        if "sort" in params:
            return {"results": ROSTER if params["page"] == 1 else []}
        raise AssertionError("no search by name")

    monkeypatch.setattr(openalex, "_fetch_json", fetch)
    found = asyncio.run(openalex.find_author("Dr. Jane Smith", institution_id="I123"))
    assert [c["openalex_id"] for c in found] == ["https://openalex.org/A1"]
    roster_call = calls[0]
    assert roster_call["filter"] == "last_known_institutions.id:I123"
    assert roster_call["sort"] == "works_count:desc" and roster_call["per_page"] == 200
    assert len(calls) == 1  # a short page ends the list
    openalex._RESPONSES.clear()
    asyncio.run(openalex.find_author("Hiroshi Tanaka", institution_id="I123"))
    assert len(calls) == 1


def test_a_name_not_on_the_list_is_still_searched(monkeypatch):
    searches = []

    async def fetch(path, params):
        if "sort" in params:
            return {"results": ROSTER}
        searches.append(params["search"])
        return {"results": [{"id": "https://openalex.org/A9", "display_name": "Ada Lovelace"}]}

    monkeypatch.setattr(openalex, "_fetch_json", fetch)
    found = asyncio.run(openalex.find_author("Ada Lovelace", institution_id="I123"))
    assert found[0]["openalex_id"].endswith("A9") and searches == ["Ada Lovelace"]


def test_a_refused_list_call_falls_back_to_searching(monkeypatch):
    async def fetch(path, params):
        if "sort" in params:
            raise httpx.HTTPStatusError("bad", request=httpx.Request("GET", "https://x"), response=httpx.Response(400))
        return {"results": [{"id": "https://openalex.org/A1", "display_name": "Jane Smith"}]}

    monkeypatch.setattr(openalex, "_fetch_json", fetch)
    assert asyncio.run(openalex.find_author("Jane Smith", institution_id="I123"))[0]["openalex_id"].endswith("A1")


def test_responses_are_kept_in_postgres_across_processes(monkeypatch):
    fetched = []

    async def fetch(path, params):
        fetched.append(path)
        return {"results": [{"title": "Paper"}]}

    monkeypatch.setattr(openalex, "_fetch_json", fetch)
    first = asyncio.run(openalex._get_json("/works", {"filter": "author.id:A1"}))
    # A fresh process: nothing in memory, the row in Postgres serves it.
    openalex._RESPONSES.clear()
    again = asyncio.run(openalex._get_json("/works", {"filter": "author.id:A1"}))
    assert first == again and fetched == ["/works"]

    async def expire():
        async with SessionLocal() as session:
            row = await session.get(OpenAlexResponse, "/works?filter=author.id:A1")
            assert row is not None
            assert row.expires_at - row.fetched_at == timedelta(days=7)
            row.expires_at = utcnow_naive() - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire())
    openalex._RESPONSES.clear()
    asyncio.run(openalex._get_json("/works", {"filter": "author.id:A1"}))
    assert fetched == ["/works", "/works"]


def test_school_lists_and_institutions_are_kept_longer(monkeypatch):
    async def fetch(path, params):
        return {"results": []}

    monkeypatch.setattr(openalex, "_fetch_json", fetch)
    asyncio.run(openalex.find_institution("Uni of Examples"))

    async def ttl():
        async with SessionLocal() as session:
            row = (await session.execute(OpenAlexResponse.__table__.select())).first()
            return row.expires_at - row.fetched_at

    assert asyncio.run(ttl()) == timedelta(days=30)


def test_failures_are_never_stored(monkeypatch):
    monkeypatch.setattr(openalex, "_RETRY_DELAYS", (0, 0))

    async def down(path, params):
        raise openalex.OpenAlexUnavailable("down")

    monkeypatch.setattr(openalex, "_fetch_json", down)
    with pytest.raises(openalex.OpenAlexUnavailable):
        asyncio.run(openalex._get_json("/works", {"filter": "author.id:A2"}))

    async def count():
        async with SessionLocal() as session:
            return len((await session.execute(OpenAlexResponse.__table__.select())).all())

    assert asyncio.run(count()) == 0


def test_expired_responses_are_pruned(monkeypatch):
    async def fetch(path, params):
        return {"results": []}

    monkeypatch.setattr(openalex, "_fetch_json", fetch)
    asyncio.run(openalex._get_json("/works", {"filter": "author.id:A1"}))
    asyncio.run(openalex._get_json("/works", {"filter": "author.id:A2"}))

    async def expire_one_and_prune():
        async with SessionLocal() as session:
            row = await session.get(OpenAlexResponse, "/works?filter=author.id:A1")
            row.expires_at = utcnow_naive() - timedelta(seconds=1)
            await session.commit()
            pruned = await openalex.prune_stored_responses(session)
            left = [r.key for r in (await session.execute(OpenAlexResponse.__table__.select())).all()]
            return pruned, left

    assert asyncio.run(expire_one_and_prune()) == (1, ["/works?filter=author.id:A2"])

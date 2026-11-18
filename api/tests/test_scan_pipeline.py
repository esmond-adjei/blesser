import asyncio
import json
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from api.agent import orchestrator
from api.agent.llm.base import LLMResponse, ToolCall
from api.agent.tools.context import ToolContext
from api.agent.tools.dispatch import _fetch_page
from api.core.db import SessionLocal
from api.core.exceptions import NotFoundError
from api.core.time import utcnow_naive
from api.opportunities import crawler, extraction, page_cache, pipeline, service
from api.opportunities.crawl_models import CrawlCandidate, PageCache, Source
from api.opportunities.page_content import (
    Page,
    deadline_dates,
    expired,
    normalized_url,
    parse_page,
)
from api.opportunities.schemas import AgentOpportunityIn
from api.opportunities.tools import validate_grounding
from api.opportunities.triage import duplicate_url, triage_page


def run(coro):
    return asyncio.run(coro)


def url():
    return f"https://example.org/{uuid.uuid4().hex}"


def payload(source, **values):
    return {
        "title": "Accra Innovation Award",
        "organization": "Accra Fund",
        "category": "startup",
        "source_url": source,
        "deadline": "2027-04-30",
        **values,
    }


def test_urls_ignore_tracking_case_fragments_and_query_order():
    assert (
        normalized_url("http://www.EXAMPLE.org/call/?utm_source=x&b=2&a=1#top")
        == "https://example.org/call?a=1&b=2"
    )


def test_only_explicit_unambiguous_deadlines_reject():
    today = date(2026, 11, 9)
    assert expired("Deadline: 30 April 2026", {}, today)
    assert expired("Information", {"deadlines": ["2026-04-30T23:59:59Z"]}, today)
    assert not expired("Published 30 April 2026. Apply for funding.", {}, today)
    assert not expired(
        "Deadline: 30 April 2026\nNext deadline: 30 April 2027", {}, today
    )
    assert not expired("Deadline: 03/04/2026", {}, today)
    assert not expired(
        "Deadline: 30 April 2026. Applications are accepted year-round.", {}, today
    )
    assert not expired("Deadline: 9 November 2026", {}, today)


def test_main_content_and_structured_deadlines():
    page = parse_page(
        '<html><title>Accra Fund</title><nav>Navigation noise</nav><main><h1>Accra Innovation Award</h1><p>Funding for researchers in Ghana.</p></main><footer>Footer noise</footer><script type="application/ld+json">{"validThrough":"2027-04-30"}</script></html>',
        url(),
    )
    assert "Navigation noise" not in page.text and "Footer noise" not in page.text
    assert deadline_dates(page.text, page.metadata) == [date(2027, 4, 30)]


@pytest.mark.parametrize(
    ("kind", "raw", "expected"),
    [
        (
            "rss",
            "<rss><channel><item><title>Grant</title><link>https://example.org/grant</link><pubDate>Mon, 09 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>",
            "https://example.org/grant",
        ),
        (
            "rss",
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Award</title><link href="https://example.org/award"/><published>2026-11-09T00:00:00Z</published></entry></feed>',
            "https://example.org/award",
        ),
        (
            "sitemap",
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.org/call</loc></url></urlset>',
            "https://example.org/call",
        ),
        (
            "listing",
            '<html><nav><a href="/bad">Grant</a></nav><main><a href="/grant">New grant</a><a href="/contact">Contact</a></main></html>',
            "https://example.org/grant",
        ),
    ],
)
def test_source_parsers(kind, raw, expected):
    items, maps = crawler.parse_items(raw, "https://example.org/", kind, 20)
    assert [item["url"] for item in items] == [expected]
    assert not maps


def test_grounding_requires_page_name_and_complete_deadline():
    source = url()
    data = AgentOpportunityIn(**payload(source))
    assert validate_grounding(data, {}) is not None
    assert validate_grounding(data, {source: "Different scheme"}) is not None
    assert (
        validate_grounding(
            data,
            {source: "Accra Innovation Award. Published in 2027. April news. Day 30."},
        )
        is not None
    )
    assert (
        validate_grounding(
            data, {source: "Accra Innovation Award. Deadline: 30 April 2027"}
        )
        is None
    )
    assert (
        validate_grounding(
            AgentOpportunityIn(**payload(source, deadline="soon")),
            {source: "Accra Innovation Award"},
        )
        is not None
    )


def test_extraction_json_is_strict():
    valid = {
        "relevant": True,
        "region_eligible": True,
        "reason": "Open",
        "confidence": 0.9,
        "opportunity": AgentOpportunityIn(**payload(url())).model_dump(mode="json"),
    }
    assert (
        extraction.Extraction.model_validate_json(json.dumps(valid)).opportunity.title
        == "Accra Innovation Award"
    )
    with pytest.raises(ValueError):
        extraction.Extraction.model_validate_json(
            json.dumps({**valid, "confidence": 1.5})
        )
    with pytest.raises(ValueError):
        extraction.Extraction.model_validate_json(
            json.dumps({**valid, "relevant": "true"})
        )
    with pytest.raises(ValueError):
        extraction.Extraction.model_validate_json(
            json.dumps({**valid, "invented": "value"})
        )
    schema = extraction.extraction_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_shared_page_cache_concurrent_ttl_and_conditional_get(monkeypatch):
    source = url()
    calls = []

    async def fetch(target, **kwargs):
        calls.append(kwargs.get("headers"))
        await asyncio.sleep(0.02)
        status = 304 if len(calls) > 1 else 200
        return httpx.Response(
            status, headers={"etag": '"one"'}, request=httpx.Request("GET", target)
        ), "<html><main>Accra Innovation Award. Deadline: 30 April 2027.</main></html>"

    monkeypatch.setattr(page_cache, "get_document", fetch)

    async def check():
        first, second = await asyncio.gather(
            page_cache.get_page(source), page_cache.get_page(source + "/#top")
        )
        assert first.text == second.text
        assert len(calls) == 1 and (first.cached or second.cached)
        async with SessionLocal() as session:
            row = await session.get(PageCache, source)
            row.expires_at = utcnow_naive() - timedelta(seconds=1)
            await session.commit()
        renewed = await page_cache.get_page(source)
        assert renewed.cached and renewed.text == first.text
        assert calls[-1] == {"If-None-Match": '"one"'}

    run(check())


def test_failed_pages_are_cached(monkeypatch):
    source = url()
    calls = []

    async def fail(target, **kwargs):
        calls.append(target)
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(page_cache, "get_document", fail)

    async def check():
        assert (await page_cache.get_page(source)).error == "ConnectError"
        assert (await page_cache.get_page(source)).cached
        assert len(calls) == 1

    run(check())


def test_candidate_url_and_content_dedupe(monkeypatch):
    source = url()

    async def check():
        async with SessionLocal() as session:
            assert await crawler.record_candidate(session, source)
            assert not await crawler.record_candidate(
                session, source + "/?utm_source=test"
            )
            first = (
                await session.execute(
                    select(CrawlCandidate).where(CrawlCandidate.url == source)
                )
            ).scalar_one()
            first.content_hash, first.status = "samehash", "rejected"
            second = CrawlCandidate(url=url(), category_hints=["startup"])
            session.add(second)
            await session.flush()
            assert (
                await triage_page(
                    session,
                    second,
                    Page(url=second.url, text="content " * 50, content_hash="samehash"),
                    date(2026, 11, 9),
                )
                == "content_duplicate"
            )
            assert (
                await triage_page(
                    session,
                    second,
                    Page(url=second.url, text="Deadline: 30 April 2025. " * 10),
                    date(2026, 11, 9),
                )
                == "deadline_passed"
            )
            second.status = "rejected"
            await session.commit()

    run(check())


def test_refetch_suppression_keeps_grounding_and_unread_offsets(monkeypatch):
    source = url()
    calls = []

    async def fetch(target, max_chars, offset, **kwargs):
        calls.append(offset)
        return "Accra Innovation Award. Deadline: 30 April 2027."

    from api import web

    monkeypatch.setattr(web, "fetch_page", fetch)

    async def check():
        ctx = ToolContext(None, None)
        first, second = await asyncio.gather(
            _fetch_page({"url": source}, ctx),
            _fetch_page({"url": source + "/#top"}, ctx),
        )
        assert calls == [0]
        assert second["cached_summary"] is True
        assert "2027-04-30" in second["text"]
        assert source in ctx.fetched_pages
        await _fetch_page({"url": source, "offset": 4000}, ctx)
        assert calls == [0, 4000]
        history = [
            {
                "role": "tool",
                "name": "fetch_page",
                "content": first["text"],
                "_summary": first["page_note"],
                "_turn": 1,
            }
        ]
        compacted = orchestrator.compact_old_tool_results(history, 8, 2)
        assert (
            "2027-04-30" in compacted[0]["content"]
            and source in compacted[0]["content"]
        )

    run(check())


def test_agent_stops_without_yield_and_summarizes(monkeypatch):
    calls = []

    class Model:
        async def chat(self, **kwargs):
            calls.append(1)
            return LLMResponse(
                tool_calls=[
                    ToolCall(
                        id=str(len(calls)),
                        name="search_web",
                        arguments={"query": "grant"},
                    )
                ]
            )

    async def dispatch(calls, ctx):
        return [{"results": []}]

    monkeypatch.setattr(orchestrator, "get_provider", Model)
    monkeypatch.setattr(orchestrator, "dispatch_batch", dispatch)
    result = run(
        orchestrator.run_agent_task(
            "sys", "go", SimpleNamespace(session=None, run=None), no_yield_turns=3
        )
    )
    assert len(calls) == 3
    assert (
        "without a new save" in result["final_text"]
        and "Saved: None" in result["final_text"]
    )


def test_worker_crawls_extracts_and_holds_low_confidence(monkeypatch):
    from api.opportunities.models import Opportunity
    from api.scans import queue
    from api.scans import service as scans
    from tests.conftest import TEST_USER_ID

    source_url, candidate_url = url(), url()

    async def config(session):
        return {
            "crawler": {
                "hours": 6,
                "max_sources": 1,
                "max_items_per_source": 5,
                "max_candidates_per_task": 1,
                "host_interval_seconds": 0.5,
                "page_cache_seconds": 3600,
            }
        }

    async def fetch(target, **kwargs):
        raw = (
            f"<rss><channel><item><title>Accra Innovation Award</title><link>{candidate_url}</link></item></channel></rss>"
            if target == source_url
            else "<html><title>Accra Innovation Award</title><main><h1>Accra Innovation Award by Accra Fund</h1><p>Applications from Ghana are invited for this innovation award. Research and venture support. Deadline: 30 April 2027.</p></main></html>"
        )
        return httpx.Response(200, request=httpx.Request("GET", target)), raw

    class Model:
        async def chat(self, tools, **kwargs):
            if tools[0]["name"] == "extract_opportunity":
                return LLMResponse(
                    tool_calls=[
                        ToolCall(
                            id="extract",
                            name="extract_opportunity",
                            arguments={
                                "relevant": True,
                                "region_eligible": True,
                                "reason": "Eligibility needs review",
                                "confidence": 0.7,
                                "opportunity": AgentOpportunityIn(
                                    **payload(candidate_url)
                                ).model_dump(mode="json"),
                            },
                        )
                    ],
                    usage={"input_tokens": 200, "output_tokens": 80},
                )
            return LLMResponse(
                text="Saved: None\nSkipped: Already processed by crawler",
                usage={"input_tokens": 100, "output_tokens": 20},
            )

    monkeypatch.setattr(crawler, "get_settings", config)
    monkeypatch.setattr(pipeline, "get_settings", config)
    monkeypatch.setattr(page_cache, "get_settings", config)
    monkeypatch.setattr(crawler, "get_document", fetch)
    monkeypatch.setattr(page_cache, "get_document", fetch)
    monkeypatch.setattr(extraction, "get_provider", Model)
    monkeypatch.setattr(orchestrator, "get_provider", Model)

    async def check():
        async with SessionLocal() as session:
            session.add(
                Source(
                    url=source_url,
                    kind="rss",
                    category_hints=["startup"],
                    next_crawl_at=utcnow_naive() - timedelta(days=10000),
                )
            )
            scan = await scans.start_scan(session, TEST_USER_ID, categories=["startup"])
            task = await queue.claim_next_task(session, scan_id=scan.id)
            await queue.process_claimed(session, task)
            assert task.status.value == "done", task.error
            assert task.metrics["model_calls"] == 2
            assert task.input_tokens == 300 and task.output_tokens == 100
            assert task.metrics["saved"] == 1
            row = (
                await session.execute(
                    select(Opportunity).where(Opportunity.scan_id == scan.id)
                )
            ).scalar_one()
            assert row.status == "in_review" and row.review_reason == "agent_find"
            assert await duplicate_url(session, candidate_url + "?utm_source=elsewhere")
            candidate = (
                await session.execute(
                    select(CrawlCandidate).where(CrawlCandidate.url == candidate_url)
                )
            ).scalar_one()
            assert candidate.status == "extracted"
            source = await session.get(Source, candidate.source_id)
            assert source.candidates_found == source.opportunities_saved == 1
            assert candidate.content_hash
            detail = await scans.scan_detail(session, TEST_USER_ID, scan.id)
            assert detail["metrics"]["saved"] == 1
            assert [
                (find["opportunity_id"], find["source"], find["in_review"])
                for find in detail["finds"]
            ] == [(row.id, "web", True)]
            with pytest.raises(NotFoundError):
                await service.track(session, "other-user", row.id)
            app, created = await service.track(session, TEST_USER_ID, row.id)
            assert created and app["opportunity_id"] == row.id

    run(check())


def test_grant_detail_url_survives_navigation_triage():
    from api.opportunities.triage import triage_url

    async def check():
        async with SessionLocal() as session:
            candidate = CrawlCandidate(
                url=url() + "/grants/ghana-research-award", dedupe_key=""
            )
            assert await triage_url(session, candidate) is None

    run(check())


def test_candidate_claims_skip_only_the_excluded_region():
    async def check():
        async with SessionLocal() as session:
            candidate = CrawlCandidate(
                url=url(), category_hints=["research"], reason="region_excluded:ghana"
            )
            session.add(candidate)
            await session.commit()
            assert await pipeline.claim_candidate(session, "research", "Ghana") is None
            claimed = await pipeline.claim_candidate(session, "research", "Kenya")
            assert claimed.id == candidate.id
            claimed.status = "rejected"
            await session.commit()

    run(check())


def test_known_url_does_not_fetch_again(monkeypatch):
    from api import web

    source = url()

    async def forbidden(*args, **kwargs):
        raise AssertionError("known pages must not be fetched")

    monkeypatch.setattr(web, "fetch_page", forbidden)
    ctx = ToolContext(None, None)
    ctx.known_pages[source] = "Award | deadline: 2027-04-30 | published"
    result = run(_fetch_page({"url": source}, ctx))
    assert result["cached_summary"] and "2027-04-30" in result["text"]
    assert not ctx.fetched_pages


@pytest.mark.robots
def test_robots_disallow_and_unreachable_robots_block_crawling(monkeypatch):
    from api import web
    from api.core import egress
    from api.opportunities.crawl_http import get_document

    source = url()
    calls = []

    async def reserve(*args):
        return None

    async def safe_get(client, target, **kwargs):
        calls.append(target)
        assert target.endswith("/robots.txt")
        return httpx.Response(
            200, request=httpx.Request("GET", target)
        ), "User-agent: BlesserBot\nDisallow: /"

    monkeypatch.setattr("api.opportunities.crawl_http.reserve_host", reserve)

    async def route(client, target, **kwargs):
        if target.endswith("/robots.txt"):
            return await safe_get(client, target, **kwargs)
        await kwargs["before_request"](target)
        raise AssertionError("disallowed page must not be requested")

    monkeypatch.setattr(egress, "safe_get", route)

    async def check():
        with pytest.raises(egress.EgressBlocked):
            await get_document(source, interval=0.5)
        assert len(calls) == 1
        web._ROBOTS.clear()

        async def unavailable(client, target, **kwargs):
            raise httpx.ConnectError("robots unreachable")

        monkeypatch.setattr(egress, "safe_get", unavailable)
        assert not await web._robots_allows(source)

    run(check())


def test_extraction_cache_reuses_judgment_for_other_categories(monkeypatch):
    source = url()
    calls = []
    data = AgentOpportunityIn(**payload(source)).model_dump(mode="json")

    class Model:
        async def chat(self, **kwargs):
            calls.append(1)
            return LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="extract",
                        name="extract_opportunity",
                        arguments={
                            "relevant": True,
                            "region_eligible": True,
                            "reason": "Open",
                            "confidence": 0.95,
                            "opportunity": data,
                        },
                    )
                ]
            )

    monkeypatch.setattr(extraction, "get_provider", Model)

    async def check():
        async with SessionLocal() as session:
            session.add(
                PageCache(
                    url=source,
                    text="Accra Innovation Award. Deadline: 30 April 2027.",
                    title="Award",
                    metadata_json={},
                    content_hash="unique",
                    expires_at=utcnow_naive() + timedelta(hours=1),
                )
            )
            await session.commit()
        page = Page(
            url=source,
            text="Accra Innovation Award. Deadline: 30 April 2027.",
            content_hash="unique",
        )
        first = await extraction.extract_page(
            page, category="startup", region="Ghana", today="2026-11-09"
        )
        second = await extraction.extract_page(
            page, category="student", region="Ghana", today="2026-11-09"
        )
        assert first == second and len(calls) == 1

    run(check())


@pytest.mark.parametrize("invalid_response", [False, True])
def test_stale_candidate_claim_cannot_save(monkeypatch, invalid_response):
    from api.scans import service as scans
    from api.scans.models import ScanTask
    from tests.conftest import TEST_USER_ID

    source = url()

    async def crawl(*args, **kwargs):
        return {"candidates_found": 0, "sources": {}}

    async def config(session):
        return {"crawler": {"max_candidates_per_task": 1}}

    async def fetch(target):
        return Page(
            url=target,
            text="Accra Innovation Award by Accra Fund. Deadline: 30 April 2027. " * 3,
            content_hash=uuid.uuid4().hex,
        )

    async def extract(*args, **kwargs):
        async with SessionLocal() as session:
            candidate = (
                await session.execute(
                    select(CrawlCandidate).where(CrawlCandidate.url == source)
                )
            ).scalar_one()
            candidate.claim_token = "new-owner"
            await session.commit()
        if invalid_response:
            raise ValueError("invalid extraction from expired claim")
        return extraction.Extraction.model_validate_json(
            json.dumps(
                {
                    "relevant": True,
                    "region_eligible": True,
                    "reason": "Open",
                    "confidence": 0.95,
                    "opportunity": AgentOpportunityIn(**payload(source)).model_dump(
                        mode="json"
                    ),
                }
            )
        )

    monkeypatch.setattr(pipeline, "crawl_due", crawl)
    monkeypatch.setattr(pipeline, "get_settings", config)
    monkeypatch.setattr(pipeline, "get_page", fetch)
    monkeypatch.setattr(pipeline, "extract_page", extract)

    async def check():
        async with SessionLocal() as session:
            candidate = CrawlCandidate(
                url=source,
                category_hints=["startup"],
                created_at=utcnow_naive() - timedelta(days=10000),
            )
            session.add(candidate)
            scan = await scans.start_scan(session, TEST_USER_ID, categories=["startup"])
            task = (
                await session.execute(
                    select(ScanTask).where(ScanTask.scan_id == scan.id)
                )
            ).scalar_one()
            await pipeline.run_pipeline(session, task, scan, "startup")
            await session.refresh(candidate)
            assert candidate.claim_token == "new-owner" and candidate.status == "new"
            assert (await scans.scan_detail(session, TEST_USER_ID, scan.id))[
                "opportunities_added"
            ] == 0
            candidate.status = "rejected"
            await session.commit()

    run(check())


def test_agent_save_metrics_survive_a_later_failure(monkeypatch):
    from api import web
    from api.scans import queue
    from api.scans import service as scans
    from tests.conftest import TEST_USER_ID

    source = url()
    title = "New Innovation Award " + uuid.uuid4().hex

    class Model:
        turn = 0

        async def chat(self, **kwargs):
            self.turn += 1
            if self.turn == 1:
                return LLMResponse(
                    tool_calls=[
                        ToolCall(
                            id="fetch", name="fetch_page", arguments={"url": source}
                        )
                    ]
                )
            if self.turn == 2:
                return LLMResponse(
                    tool_calls=[
                        ToolCall(
                            id="save",
                            name="save_opportunity",
                            arguments=payload(source, title=title),
                        )
                    ]
                )
            raise ValueError("failed after save")

    model = Model()

    async def fetch(*args, **kwargs):
        return title + ". Accra Fund. Deadline: 30 April 2027."

    monkeypatch.setattr(web, "fetch_page", fetch)
    monkeypatch.setattr(orchestrator, "get_provider", lambda: model)

    async def check():
        async with SessionLocal() as session:
            scan = await scans.start_scan(session, TEST_USER_ID, categories=["startup"])
            task = await queue.claim_next_task(session, scan_id=scan.id)
            await queue.process_claimed(session, task)
            assert task.status.value == "error"
            assert task.metrics["saved"] == 1
            assert (await scans.scan_detail(session, TEST_USER_ID, scan.id))[
                "opportunities_added"
            ] == 1

    run(check())


def test_agent_irrelevance_is_scoped_to_its_region_and_category():
    from api.opportunities.tools import handle_reject_candidate

    source = url()

    async def check():
        async with SessionLocal() as session:
            await crawler.record_candidate(session, source, category_hints=["startup"])
            ctx = ToolContext(session, SimpleNamespace(region="Ghana", user_id=None))
            ctx.category = "startup"
            ctx.fetched_pages[source] = (
                "Student awards open to Kenyan residents. Deadline: 30 April 2027."
            )
            rejected = await handle_reject_candidate(
                {"url": source, "reason": "Outside target", "closed": True}, ctx
            )
            assert rejected["verdict"] == "rejected"
            assert rejected["reason"].startswith("scope:ghana:startup:")
            assert await pipeline.claim_candidate(session, "startup", "Ghana") is None
            claimed = await pipeline.claim_candidate(session, "student", "Kenya")
            assert claimed.url == source
            claimed.status = "extracted"
            await session.commit()

    run(check())


def test_scoped_rejection_does_not_duplicate_other_scopes():
    async def check():
        async with SessionLocal() as session:
            previous = CrawlCandidate(
                url=url(),
                category_hints=[],
                status="rejected",
                content_hash=uuid.uuid4().hex,
                reason="scope:ghana:startup:student only",
            )
            candidate = CrawlCandidate(url=url(), category_hints=["student"])
            session.add_all([previous, candidate])
            await session.flush()
            page = Page(
                url=candidate.url,
                text="An open student scholarship. " * 10,
                content_hash=previous.content_hash,
            )
            assert (
                await triage_page(session, candidate, page, date(2026, 11, 9)) is None
            )
            candidate.status = "rejected"
            await session.commit()

    run(check())


def test_cache_releases_pool_connection_before_host_reservation(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from api.opportunities import crawl_http
    from tests.conftest import TEST_DATABASE_URL

    source = url()

    async def check():
        engine = create_async_engine(
            TEST_DATABASE_URL, pool_size=1, max_overflow=0, pool_timeout=0.2
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(page_cache, "SessionLocal", sessions)
        monkeypatch.setattr(crawl_http, "SessionLocal", sessions)

        async def fetch(target, **kwargs):
            await crawl_http.reserve_host(target, 0)
            return (
                httpx.Response(200, request=httpx.Request("GET", target)),
                "<html><main>Accra Innovation Award. Deadline: 30 April 2027.</main></html>",
            )

        monkeypatch.setattr(page_cache, "get_document", fetch)
        try:
            page = await page_cache.get_page(source)
            assert not page.error and "Accra Innovation Award" in page.text
        finally:
            await engine.dispose()

    run(check())


def test_empty_response_completes_cache_claim_as_failure(monkeypatch):
    source = url()
    calls = []

    async def fetch(target, **kwargs):
        calls.append(target)
        return httpx.Response(204, request=httpx.Request("GET", target)), ""

    monkeypatch.setattr(page_cache, "get_document", fetch)

    async def check():
        first = await page_cache.get_page(source)
        second = await page_cache.get_page(source)
        assert first.error == "ParserError"
        assert second.cached and second.error == first.error and len(calls) == 1

    run(check())


@pytest.mark.parametrize("superseded", [False, True])
def test_cache_lease_recovers_and_discards_stale_completion(monkeypatch, superseded):
    source = url()

    async def fetch(target, **kwargs):
        if superseded:
            async with SessionLocal() as session:
                row = await session.get(PageCache, source)
                row.metadata_json = {}
                row.error = ""
                row.text = "Newer worker's page"
                row.content_hash = "new-worker-hash"
                row.expires_at = utcnow_naive() + timedelta(hours=1)
                await session.commit()
        return httpx.Response(
            200, request=httpx.Request("GET", target)
        ), "<html><main>Old worker page</main></html>"

    monkeypatch.setattr(page_cache, "get_document", fetch)

    async def check():
        async with SessionLocal() as session:
            session.add(
                PageCache(
                    url=source,
                    error="fetch_in_progress",
                    metadata_json={"_fetch_token": "dead-worker"},
                    expires_at=utcnow_naive() - timedelta(seconds=1),
                )
            )
            await session.commit()
        page = await page_cache.get_page(source)
        assert not page.error
        assert (
            page.text == "Newer worker's page"
            if superseded
            else "Old worker page" in page.text
        )

    run(check())

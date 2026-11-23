"""Aggregator finds are stored with the official page, never the aggregator's."""

import asyncio
import json
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from api.agent.tools.context import ToolContext
from api.auth import security
from api.auth.models import User
from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.editorial import models as em
from api.editorial.service import defaults
from api.main import app
from api.opportunities import extraction, page_cache, pipeline
from api.opportunities import service as opp_service
from api.opportunities.crawl_models import CrawlCandidate, PageCache
from api.opportunities.models import Opportunity
from api.opportunities.official import (
    clean_hosts,
    names_title,
    ranked_links,
    resolve_official,
    settle_deadline,
)
from api.opportunities.official_backfill import run_backfill, scheduled_pass
from api.opportunities.page_content import Page, normalized_url, parse_page
from api.opportunities.schemas import AgentOpportunityIn
from api.opportunities.tools import handle_save_opportunity, record_fetch
from api.opportunities.triage import duplicate_url
from api.scans.models import Scan, ScanFind, ScanTask

HOSTS = frozenset({"opportunitydesk.org", "opportunitiesforafricans.com"})
TITLE = "Accra Climate Innovation Fellowship"
ORG = "Volta Research Trust"
OFFICIAL_TEXT = (
    f"{TITLE}\nThe {ORG} invites applications for the {TITLE}. "
    "Fellows receive a stipend and mentoring. Application deadline: 30 April 2027. "
)


def run(coro):
    return asyncio.run(coro)


async def _clean():
    async with SessionLocal() as session:
        for model in (ScanFind, ScanTask, Scan, CrawlCandidate, PageCache):
            await session.execute(delete(model))
        await session.execute(delete(Opportunity))
        await session.execute(delete(em.SiteSetting))
        await session.execute(delete(User).where(User.id.like("official-%")))
        session.add_all([em.SiteSetting(key=k, value=v) for k, v in defaults().items()])
        await session.commit()


@pytest.fixture(autouse=True)
def isolated():
    run(_clean())
    yield
    run(_clean())


def post_url():
    return f"https://www.opportunitydesk.org/2026/11/{uuid.uuid4().hex}/"


def aggregator_page(url, links, text=None):
    return Page(
        url=normalized_url(url),
        text=text or OFFICIAL_TEXT + " Shared by Opportunity Desk.",
        title=TITLE,
        metadata={"outbound": links},
        content_hash=uuid.uuid4().hex,
    )


def official_page(url, text=OFFICIAL_TEXT, **metadata):
    return Page(
        url=normalized_url(url),
        text=text,
        title=TITLE,
        metadata=metadata,
        content_hash=uuid.uuid4().hex,
    )


def fake_fetch(pages: dict):
    calls = []

    async def fetch(url, need=None):
        calls.append(url)
        page = pages.get(normalized_url(url))
        return page or Page(url=normalized_url(url), error="http_404")

    fetch.calls = calls
    return fetch


# --- Reading and ranking links ---------------------------------------------------


def test_parse_page_keeps_outbound_links_with_labels():
    raw = """<html><head><title>Fellowship</title></head><body>
    <nav><a href="https://navsite.example/apply">Apply nav</a></nav>
    <article>
      <p>Read about it.</p>
      <a href="/category/fellowships">More fellowships</a>
      <a href="https://volta.example.org/fellowship">Official website</a>
      <a href="https://volta.example.org/fellowship#top">duplicate</a>
      <a href="https://apply.volta.example.org/form">Apply here</a>
      <a href="mailto:hi@example.com">Mail</a>
    </article></body></html>"""
    page = parse_page(raw, "https://opportunitydesk.org/post")
    assert page.metadata["outbound"] == [
        {"url": "https://volta.example.org/fellowship", "label": "Official website"},
        {"url": "https://apply.volta.example.org/form", "label": "Apply here"},
    ]


def test_ranked_links_prefer_the_funders_site_and_skip_social_and_aggregators():
    page = aggregator_page(
        "https://opportunitydesk.org/post",
        [
            {"url": "https://ads.example.com/banner", "label": "Sponsored"},
            {"url": "https://facebook.com/share?u=x", "label": "Share on Facebook"},
            {"url": "https://opportunitiesforafricans.com/x", "label": "Apply"},
            {"url": "https://wa.me/123", "label": "Apply on WhatsApp"},
            {"url": "https://voltaresearch.example/about", "label": "Visit website"},
            {"url": "https://portal.example.net/apply", "label": "Apply now"},
            {"url": "https://opportunitydesk.org/other", "label": "Apply"},
        ],
    )
    # A host carrying the organization's name beats an "apply" label elsewhere.
    assert ranked_links(page, hosts=HOSTS, organization=ORG) == [
        normalized_url("https://voltaresearch.example/about"),
        normalized_url("https://portal.example.net/apply"),
    ]
    assert ranked_links(page, hosts=HOSTS) == [
        normalized_url("https://portal.example.net/apply"),
        normalized_url("https://voltaresearch.example/about"),
    ]
    assert ranked_links(
        page,
        hosts=HOSTS,
        organization=ORG,
        preferred="https://volta.example.org/call",
    )[0] == normalized_url("https://volta.example.org/call")


def test_title_check_and_deadline_settling():
    assert names_title(OFFICIAL_TEXT, TITLE + " 2027 (Fully Funded)", ORG)
    # The organization's name alone does not name the call.
    assert not names_title(f"Welcome to the {ORG}.", TITLE, ORG)
    page = official_page("https://volta.example.org/f")
    assert settle_deadline("2027-04-30", page) == ("2027-04-30", False, False)
    assert settle_deadline("2027-05-15", page) == ("2027-04-30", True, False)
    assert settle_deadline("", page) == ("2027-04-30", True, False)
    two = official_page(
        "https://volta.example.org/f",
        text=OFFICIAL_TEXT + " Second round deadline: 30 June 2027.",
    )
    assert settle_deadline("2027-05-15", two) == ("", True, True)


def test_clean_hosts_trims_urls_and_www():
    assert clean_hosts(
        ["https://www.Example.com/path", "example.com", " other.org ", "nodot", ""]
    ) == ["example.com", "other.org"]


def test_resolver_skips_broken_redirected_and_unrelated_pages():
    official = "https://fellows.example.org/accra"
    post = aggregator_page(
        "https://opportunitydesk.org/post",
        [
            {"url": "https://gone.example.org/apply", "label": "Apply"},
            {"url": "https://moved.example.org/apply", "label": "Apply"},
            {"url": "https://other.example.org/apply", "label": "Apply"},
            {"url": official, "label": "Details"},
        ],
    )
    moved = official_page(
        "https://moved.example.org/apply",
        final_url="https://opportunitiesforafricans.com/copy",
    )
    unrelated = official_page(
        "https://other.example.org/apply", text="A different call. " * 10
    )
    fetch = fake_fetch(
        {
            moved.url: moved,
            unrelated.url: unrelated,
            normalized_url(official): official_page(official),
        }
    )

    def resolve(**kwargs):
        return run(
            resolve_official(
                post,
                title=TITLE,
                organization=ORG,
                deadline="2027-04-30",
                hosts=HOSTS,
                fetch=fetch,
                **kwargs,
            )
        )

    # Only MAX_TRIES (3) links are read, best first: the official one ranks fourth.
    found = resolve()
    assert found.page is None and len(found.tried) == 3
    # The extracted application link is tried first.
    found = resolve(preferred_link=official)
    assert found.url == normalized_url(official)
    assert found.tried == [normalized_url(official)]
    assert not found.deadline_changed


# --- Crawler pipeline --------------------------------------------------------------


def _extraction(source, link=""):
    return extraction.Extraction.model_validate_json(
        json.dumps(
            {
                "relevant": True,
                "region_eligible": True,
                "reason": "Open",
                "confidence": 0.95,
                "opportunity": AgentOpportunityIn(
                    title=TITLE,
                    organization=ORG,
                    category="research",
                    source_url=source,
                    link=link,
                    deadline="2027-04-30",
                ).model_dump(mode="json"),
            }
        )
    )


def _run_pipeline(monkeypatch, post, pages):
    from api.scans import service as scans
    from tests.conftest import TEST_USER_ID

    async def crawl(*args, **kwargs):
        return {"candidates_found": 0, "sources": {}}

    async def config(session):
        return {"crawler": {"max_candidates_per_task": 1}}

    async def extract(page, **kwargs):
        return _extraction(page.url)

    monkeypatch.setattr(pipeline, "crawl_due", crawl)
    monkeypatch.setattr(pipeline, "get_settings", config)
    monkeypatch.setattr(pipeline, "get_page", fake_fetch(pages))
    monkeypatch.setattr(pipeline, "extract_page", extract)

    async def go():
        async with SessionLocal() as session:
            session.add(
                CrawlCandidate(
                    url=normalized_url(post),
                    category_hints=["research"],
                    created_at=utcnow_naive() - timedelta(days=10000),
                )
            )
            await session.commit()
            scan = await scans.start_scan(
                session, TEST_USER_ID, categories=["research"], kind="member"
            )
            task = (
                await session.execute(
                    select(ScanTask).where(ScanTask.scan_id == scan.id)
                )
            ).scalar_one()
            metrics = await pipeline.run_pipeline(session, task, scan, "research")
            opp = (await session.execute(select(Opportunity))).scalar_one_or_none()
            return metrics, opp

    return run(go())


def test_pipeline_stores_the_official_page_for_an_aggregator_find(monkeypatch):
    post = post_url()
    official = "https://volta.example.org/fellowship"
    pages = {
        normalized_url(post): aggregator_page(
            post, [{"url": official, "label": "Apply here"}]
        ),
        normalized_url(official): official_page(official),
    }
    metrics, opp = _run_pipeline(monkeypatch, post, pages)
    assert metrics["official_found"] == 1
    assert opp.source_url == normalized_url(official)
    assert opp.link == normalized_url(official)
    assert opp.found_via_url == normalized_url(post)
    assert opp.status == "published" and opp.review_reason is None
    assert opp.deadline == "2027-04-30"

    async def check_dupes():
        async with SessionLocal() as session:
            return await duplicate_url(session, post)

    # The aggregator post is never processed again.
    assert run(check_dupes())


def test_pipeline_holds_an_aggregator_find_without_an_official_page(monkeypatch):
    post = post_url()
    pages = {
        normalized_url(post): aggregator_page(
            post, [{"url": "https://gone.example.org/apply", "label": "Apply"}]
        )
    }
    metrics, opp = _run_pipeline(monkeypatch, post, pages)
    assert metrics["official_missing"] == 1
    assert opp.status == "in_review" and opp.review_reason == "no_official_link"
    assert opp.found_via_url == normalized_url(post)
    assert "no official page" in opp.editor_note


def test_pipeline_takes_the_official_deadline(monkeypatch):
    post = post_url()
    official = "https://volta.example.org/fellowship"
    pages = {
        normalized_url(post): aggregator_page(
            post, [{"url": official, "label": "Official website"}]
        ),
        normalized_url(official): official_page(
            official,
            text=OFFICIAL_TEXT.replace("30 April 2027", "15 May 2027"),
        ),
    }
    _, opp = _run_pipeline(monkeypatch, post, pages)
    assert opp.deadline == "2027-05-15"
    assert opp.deadline_date.isoformat() == "2027-05-15"


# --- Agent saves -----------------------------------------------------------------


def test_agent_saves_on_aggregator_pages_are_refused():
    async def go():
        async with SessionLocal() as session:
            ctx = ToolContext(session, SimpleNamespace(id=None, region="Ghana"))
            ctx.category = "research"
            post = post_url()
            record_fetch(ctx, post, OFFICIAL_TEXT)
            refused = await handle_save_opportunity(
                {
                    "title": TITLE,
                    "organization": ORG,
                    "category": "research",
                    "source_url": post,
                    "deadline": "2027-04-30",
                },
                ctx,
            )
            official = "https://volta.example.org/fellowship"
            record_fetch(ctx, official, OFFICIAL_TEXT)
            link_refused = await handle_save_opportunity(
                {
                    "title": TITLE,
                    "organization": ORG,
                    "category": "research",
                    "source_url": official,
                    "link": "https://opportunitiesforafricans.com/apply",
                },
                ctx,
            )
            saved = await handle_save_opportunity(
                {
                    "title": TITLE,
                    "organization": ORG,
                    "category": "research",
                    "source_url": official,
                    "deadline": "2027-04-30",
                },
                ctx,
            )
            return refused, link_refused, saved

    refused, link_refused, saved = run(go())
    assert "aggregator" in refused["error"]
    assert link_refused["error"].startswith("link is on an aggregator")
    assert saved["created"] is True


def test_staff_edit_the_aggregator_list():
    async def make_admin():
        async with SessionLocal() as session:
            session.add(
                User(
                    id="official-admin",
                    email="official-admin@example.com",
                    role="admin",
                    password_hash="!unused",
                    email_verified_at=utcnow_naive(),
                )
            )
            await session.commit()

    run(make_admin())
    token = security.issue_access_token("official-admin", "admin")
    c = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    values = c.get("/api/admin/settings").json()
    assert "opportunitydesk.org" in values["aggregators"]
    assert values["official_backfill"] is False
    values["aggregators"] = ["https://www.NewBlog.example/posts", "newblog.example"]
    values["official_backfill"] = True
    saved = c.put("/api/admin/settings", json=values)
    assert saved.status_code == 200, saved.text
    assert saved.json()["aggregators"] == ["newblog.example"]
    values.pop("aggregators")
    c.put("/api/admin/settings", json=values)
    assert c.get("/api/admin/settings").json()["aggregators"] == ["newblog.example"]


# --- Page cache ------------------------------------------------------------------


def test_page_cache_reparses_pages_cached_before_outbound_links(monkeypatch):
    target = "https://opportunitydesk.org/" + uuid.uuid4().hex
    fetches = []

    async def config(session):
        return {
            "crawler": {**defaults()["crawler"], "host_interval_seconds": 0},
        }

    async def fetch(url, **kwargs):
        fetches.append(kwargs.get("headers") or {})
        body = (
            "<html><body><p>" + OFFICIAL_TEXT + "</p>"
            '<a href="https://volta.example.org/f">Apply</a></body></html>'
        )
        return SimpleNamespace(status_code=200, headers={}, url=url), body

    monkeypatch.setattr(page_cache, "get_settings", config)
    monkeypatch.setattr(page_cache, "get_document", fetch)

    async def go():
        async with SessionLocal() as session:
            session.add(
                PageCache(
                    url=normalized_url(target),
                    text="old text",
                    metadata_json={"links": []},
                    content_hash="old",
                    etag="abc",
                    expires_at=utcnow_naive() + timedelta(hours=1),
                )
            )
            await session.commit()
        plain = await page_cache.get_page(target)
        fresh = await page_cache.get_page(target, need="outbound")
        again = await page_cache.get_page(target, need="outbound")
        return plain, fresh, again

    plain, fresh, again = run(go())
    assert plain.cached and plain.text == "old text"
    assert not fresh.cached and fresh.metadata["outbound"][0]["label"] == "Apply"
    assert again.cached
    # The refetch asked for the full body, not a 304.
    assert fetches == [{}]


# --- Backfill --------------------------------------------------------------------


def add_listing(source_url, link=None, status="published", deadline="2027-04-30"):
    async def create():
        async with SessionLocal() as session:
            row = Opportunity(
                title=TITLE,
                organization=ORG,
                category="research",
                slug=uuid.uuid4().hex,
                source_url=source_url,
                link=link or source_url,
                status=status,
                deadline=deadline,
                deadline_date=opp_service.parse_deadline(deadline),
                dedupe_key=uuid.uuid4().hex,
            )
            session.add(row)
            await session.commit()
            return row.id

    return run(create())


def read(id):
    async def get():
        async with SessionLocal() as session:
            return await session.get(Opportunity, id)

    return run(get())


def test_backfill_dry_run_then_apply():
    good_post, bad_post = post_url(), post_url()
    official = "https://volta.example.org/fellowship"
    good = add_listing(good_post)
    bad = add_listing(bad_post)
    untouched = add_listing("https://volta.example.org/other-call")
    fetch = fake_fetch(
        {
            normalized_url(good_post): aggregator_page(
                good_post, [{"url": official, "label": "Apply"}]
            ),
            normalized_url(bad_post): aggregator_page(bad_post, []),
            normalized_url(official): official_page(official),
        }
    )

    async def backfill(apply):
        async with SessionLocal() as session:
            return await run_backfill(session, apply=apply, fetch=fetch)

    dry = run(backfill(False))
    assert dry["counts"] == {
        "checked": 2,
        "resolved": 1,
        "deadline_unclear": 0,
        "unresolved": 1,
    }
    assert read(good).source_url == good_post and read(good).found_via_url == ""

    applied = run(backfill(True))
    assert applied["counts"]["checked"] == 2
    row = read(good)
    assert (row.source_url, row.link) == (normalized_url(official),) * 2
    assert row.found_via_url == normalized_url(good_post)
    assert row.status == "published" and row.official_checked_at is not None
    row = read(bad)
    assert row.status == "in_review" and row.review_reason == "no_official_link"
    assert "Add the official link" in row.editor_note
    assert read(untouched).official_checked_at is None
    # Nothing is due again: resolved rows left aggregators, held rows wait for staff.
    assert run(backfill(True))["counts"]["checked"] == 0


def test_backfill_sends_unclear_deadlines_to_review():
    post = post_url()
    official = "https://volta.example.org/fellowship"
    listing = add_listing(post, deadline="2027-05-20")
    fetch = fake_fetch(
        {
            normalized_url(post): aggregator_page(
                post, [{"url": official, "label": "Apply"}]
            ),
            normalized_url(official): official_page(
                official,
                text=OFFICIAL_TEXT + " Final deadline: 30 June 2027.",
            ),
        }
    )

    async def go():
        async with SessionLocal() as session:
            return await run_backfill(session, apply=True, fetch=fetch)

    assert run(go())["counts"]["deadline_unclear"] == 1
    row = read(listing)
    assert row.source_url == normalized_url(official)
    assert row.status == "in_review" and row.review_reason == "source_changed"


def test_scheduled_backfill_is_off_until_staff_switch_it_on():
    add_listing(post_url())

    async def go():
        async with SessionLocal() as session:
            return await scheduled_pass(session)

    assert run(go()) is None

"""Scheduled listing checks, undated expiry, new cycles and duplicate review."""

import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from api.applications.models import Application
from api.auth import security
from api.auth.models import User
from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.editorial import models as em
from api.editorial.service import defaults
from api.main import app
from api.opportunities import dedupe, freshness, triage
from api.opportunities import service as opp_service
from api.opportunities.archive import auto_archive
from api.opportunities.crawl_models import CrawlCandidate, PageCache
from api.opportunities.models import (
    DuplicateDismissal,
    Opportunity,
    OrganizationAlias,
)
from api.opportunities.page_content import Page, normalized_url
from api.opportunities.schemas import AgentOpportunityIn
from api.scans import service as scan_service
from api.scans.models import Scan, ScanFind, ScanTask, TaskStatus

pytestmark = pytest.mark.real_auth

URL = "https://funder.example.org/programmes/seed-grant"


def run(coro):
    return asyncio.run(coro)


async def _clean():
    async with SessionLocal() as session:
        for model in (
            ScanFind,
            ScanTask,
            Scan,
            Application,
            CrawlCandidate,
            PageCache,
            em.AuditLog,
            em.SlugHistory,
            em.SiteSetting,
            DuplicateDismissal,
            OrganizationAlias,
            Opportunity,
        ):
            await session.execute(delete(model))
        await session.execute(delete(User).where(User.id.like("fresh-%")))
        session.add_all([em.SiteSetting(key=k, value=v) for k, v in defaults().items()])
        await session.commit()


@pytest.fixture(autouse=True)
def isolated():
    run(_clean())
    yield
    run(_clean())


def staff(role="editor", name=None):
    id = f"fresh-{name or role}"

    async def create():
        async with SessionLocal() as session:
            session.add(
                User(
                    id=id,
                    email=f"{id}@example.com",
                    role=role,
                    password_hash="!unused",
                    email_verified_at=utcnow_naive(),
                )
            )
            await session.commit()

    run(create())
    token = security.issue_access_token(id, "admin")
    return id, TestClient(app, headers={"Authorization": f"Bearer {token}"})


def add(title="Seed Grant", organization="Accra Fund", **values):
    async def create():
        async with SessionLocal() as session:
            row = Opportunity(
                title=title,
                organization=organization,
                category=values.pop("category", "startup"),
                slug=values.pop("slug", None) or title.lower().replace(" ", "-"),
                source_url=values.pop("source_url", URL),
                link=values.pop("link", URL),
                status=values.pop("status", "published"),
                dedupe_key=values.pop(
                    "dedupe_key", opp_service.dedupe_key(organization, title)
                ),
                **values,
            )
            session.add(row)
            await session.commit()
            return row.id

    return run(create())


def read(id):
    async def fetch():
        async with SessionLocal() as session:
            return await session.get(Opportunity, id)

    return run(fetch())


def days_ago(days):
    return utcnow_naive() - timedelta(days=days)


# --- Dedupe key ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            ("Mastercard Foundation", "Mastercard Foundation Scholars Program 2027"),
            ("Mastercard Foundation", "Mastercard Foundation Scholars Program"),
        ),
        (("Wellcome Trust", "Discovery Awards"), ("Wellcome", "Discovery Awards")),
        (
            ("The MEST", "MEST Africa Challenge 2026/27: Call for Applications"),
            ("MEST", "MEST Africa Challenge"),
        ),
        (
            ("Seedstars", "Seedstars Accelerator Cohort 5"),
            ("Seedstars", "Seedstars Accelerator 6th cohort"),
        ),
        (
            ("Grand Challenges", "Round 3 Innovation Grants - Applications now open"),
            ("Grand Challenges", "Innovation Grants"),
        ),
    ],
)
def test_cycle_and_filler_words_share_a_key(first, second):
    assert opp_service.dedupe_key(*first) == opp_service.dedupe_key(*second)


def test_key_keeps_distinct_programmes_and_numbers_apart():
    assert opp_service.dedupe_key("A", "Top 50 Women in Tech") != (
        opp_service.dedupe_key("A", "Top Women in Tech")
    )
    assert opp_service.dedupe_key("Ghana Education Trust Fund", "Grant") == (
        opp_service.dedupe_key("Ghana Education Trust", "Grant")
    )
    assert opp_service.dedupe_key("Bank of Ghana", "Grant") != (
        opp_service.dedupe_key("Bank", "Grant")
    )
    # A title made only of cycle words keeps its plain form.
    assert dedupe.title_key("2026 Call") == "2026 call"


def test_aliases_map_organizations_to_one_key():
    async def go():
        async with SessionLocal() as session:
            session.add(
                OrganizationAlias(
                    alias="german academic exchange service", canonical="daad"
                )
            )
            await session.commit()
            return await dedupe.key_for(
                session, "German Academic Exchange Service", "In-Country Scholarships"
            ), await dedupe.key_for(session, "DAAD", "In-Country Scholarships 2026")

    long, short = run(go())
    assert long == short == "daad|in country scholarships"


# --- New cycles ------------------------------------------------------------------


def agent_save(title, deadline="", rolling=False, low_confidence=False):
    async def go():
        async with SessionLocal() as session:
            row, created, updated = await opp_service.upsert_from_agent(
                session,
                user_id=None,
                scan_id=None,
                data=AgentOpportunityIn(
                    title=title,
                    organization="Accra Fund",
                    category="startup",
                    source_url=URL,
                    deadline=deadline,
                    rolling=rolling,
                ),
                low_confidence=low_confidence,
            )
            await session.commit()
            return row.id, created, updated

    return run(go())


def test_new_cycle_reopens_an_archived_listing_under_its_new_name():
    today = opp_service.today()
    old = add(
        "Seed Grant 2026",
        status="archived",
        deadline="2026-01-01",
        deadline_date=today - timedelta(days=60),
    )
    ahead = today + timedelta(days=40)
    id, created, updated = agent_save("Seed Grant 2027", ahead.isoformat())
    row = read(old)
    assert id == old and not created and "status" in updated
    assert row.status == "published" and row.title == "Seed Grant 2027"
    assert row.deadline_date == ahead and row.check_outcome == "reopened"


def test_unsure_new_cycle_reopens_into_review():
    today = opp_service.today()
    old = add(
        status="archived",
        deadline_date=today - timedelta(days=60),
        published_at=days_ago(400),
    )
    agent_save(
        "Seed Grant", (today + timedelta(days=9)).isoformat(), low_confidence=True
    )
    row = read(old)
    assert row.status == "in_review" and row.review_reason == "agent_find"


def test_staff_archive_with_future_deadline_is_not_reopened():
    ahead = opp_service.today() + timedelta(days=30)
    old = add(status="archived", deadline=ahead.isoformat(), deadline_date=ahead)
    agent_save("Seed Grant", ahead.isoformat())
    assert read(old).status == "archived"


def test_archived_key_does_not_block_a_new_cycle_on_another_page():
    async def go(key):
        async with SessionLocal() as session:
            return await opp_service.blocks_save(session, key)

    key = opp_service.dedupe_key("Accra Fund", "Seed Grant")
    add(status="archived")
    assert run(go(key)) is False
    add("Other Grant", status="published")
    assert run(go(opp_service.dedupe_key("Accra Fund", "Other Grant 2027"))) is True


def test_structured_page_key_ignores_archived_listings():
    page = Page(
        url="https://funder.example.org/new-call",
        text="Seed Grant 2027 applications. " * 10,
        metadata={
            "structured": [{"name": "Seed Grant 2027", "funder": "Accra Fund"}],
            "deadlines": [],
        },
        content_hash="new",
    )

    async def go():
        async with SessionLocal() as session:
            candidate = CrawlCandidate(url=page.url, status="new")
            session.add(candidate)
            await session.flush()
            return await triage.triage_page(
                session, candidate, page, opp_service.today()
            )

    add(status="archived")
    assert run(go()) is None
    run(_clean())
    add(status="published")
    assert run(go()) == "dedupe_key"


# --- Scheduled checks ------------------------------------------------------------


def page(text="Seed Grant by Accra Fund. Apply now.", *, error="", **metadata):
    return Page(
        url=normalized_url(URL),
        text=text,
        metadata={"deadlines": [], **metadata},
        content_hash=str(hash(text)),
        error=error,
    )


def checks(monkeypatch, served, *, now=None):
    async def get_page(url):
        return served

    monkeypatch.setattr(freshness, "get_page", get_page)

    async def go():
        async with SessionLocal() as session:
            return await freshness.run_checks(session, now=now)

    return run(go())


def tasks():
    async def go():
        async with SessionLocal() as session:
            return (
                (await session.execute(select(ScanTask).order_by(ScanTask.created_at)))
                .scalars()
                .all()
            )

    return run(go())


def test_due_listings_are_claimed_most_urgent_first():
    today = opp_service.today()
    closing = add(
        "Closing Grant",
        deadline_date=today + timedelta(days=3),
        verified_at=days_ago(20),
    )
    undated = add("Undated Grant", verified_at=days_ago(45))
    archived = add(
        "Closed Grant",
        status="archived",
        deadline_date=today - timedelta(days=30),
    )
    add("Fresh Grant", verified_at=days_ago(2))
    add("Far Grant", deadline_date=today + timedelta(days=60), verified_at=days_ago(90))
    add("Recently Checked", verified_at=days_ago(45), checked_at=days_ago(0.5))
    add(
        "Old Closed",
        status="archived",
        deadline_date=today - timedelta(days=500),
    )
    add("Hidden Grant", status="hidden", verified_at=days_ago(90))
    add("No Link Grant", source_url="", link="", verified_at=days_ago(90))

    async def go():
        async with SessionLocal() as session:
            cfg = freshness.config(await freshness.get_settings(session))
            return [
                r.id for r in await freshness.claim_due(session, cfg, utcnow_naive())
            ]

    assert run(go()) == [closing, undated, archived]
    assert read(undated).checked_at is not None
    assert run(go()) == []


def test_unchanged_page_confirms_without_a_model(monkeypatch):
    served = page()
    id = add(verified_at=days_ago(45), source_hash=served.content_hash)
    assert checks(monkeypatch, served) == {"unchanged": 1}
    row = read(id)
    assert row.verified_at > days_ago(0.01) and row.check_outcome == "unchanged"
    assert row.status == "published" and tasks() == []


@pytest.mark.parametrize(
    ("served", "outcome"),
    [
        (page(error="http_404"), "missing"),
        (page(final_url="https://funder.example.org/"), "moved"),
    ],
)
def test_lost_pages_go_to_review(monkeypatch, served, outcome):
    id = add(verified_at=days_ago(45))
    assert checks(monkeypatch, served) == {outcome: 1}
    row = read(id)
    assert row.status == "in_review" and row.review_reason == "source_changed"


def test_unreachable_page_changes_nothing_and_retries_later(monkeypatch):
    id = add(verified_at=days_ago(45))
    assert checks(monkeypatch, page(error="http_503")) == {"unreachable": 1}
    assert read(id).status == "published"
    assert checks(monkeypatch, page()) == {}
    later = utcnow_naive() + timedelta(hours=25)
    assert checks(monkeypatch, page(error="http_503"), now=later) == {"unreachable": 1}


def test_undated_listing_whose_page_closed_is_archived(monkeypatch):
    id = add(verified_at=days_ago(45))
    closed = page("Seed Grant. Application deadline: 3 January 2020.")
    assert checks(monkeypatch, closed) == {"closed": 1}
    row = read(id)
    assert row.status == "archived" and row.source_hash == closed.content_hash


def test_dated_listing_whose_page_closed_goes_to_review(monkeypatch):
    soon = opp_service.today() + timedelta(days=3)
    id = add(deadline_date=soon, verified_at=days_ago(20))
    checks(monkeypatch, page("Seed Grant. Application deadline: 3 January 2020."))
    row = read(id)
    assert row.status == "in_review" and row.review_reason == "source_changed"


def test_changed_page_queues_one_agent_check_within_budget(monkeypatch):
    owner, _ = staff("admin")
    first = add(verified_at=days_ago(45))
    second = add("Second Grant", verified_at=days_ago(44))

    async def budget():
        async with SessionLocal() as session:
            await session.execute(
                delete(em.SiteSetting).where(em.SiteSetting.key == "freshness")
            )
            session.add(em.SiteSetting(key="freshness", value={"max_agent_checks": 1}))
            await session.commit()

    run(budget())
    assert checks(monkeypatch, page()) == {"queued": 1, "changed": 1}
    queued = tasks()
    assert len(queued) == 1 and queued[0].target == first
    assert queued[0].user_id == owner and queued[0].metrics == {"scheduled_check": True}
    assert read(second).check_outcome == "changed"

    async def scan():
        async with SessionLocal() as session:
            return await session.get(Scan, queued[0].scan_id)

    assert run(scan()).focus == freshness.CHECK_FOCUS
    # An in-flight check is not claimed again, even once the retry window passes.
    later = utcnow_naive() + timedelta(days=2)
    assert checks(monkeypatch, page(), now=later) == {"queued": 1}
    assert [t.target for t in tasks()] == [first, second]


def test_no_owner_means_no_agent_checks(monkeypatch):
    id = add(verified_at=days_ago(45))
    assert checks(monkeypatch, page()) == {"changed": 1}
    assert tasks() == [] and read(id).source_hash == ""


def test_archived_listing_with_a_new_deadline_is_queued(monkeypatch):
    staff("admin")
    today = opp_service.today()
    id = add(status="archived", deadline_date=today - timedelta(days=200))
    ahead = (today + timedelta(days=50)).strftime("%d %B %Y")
    opened = page(f"Seed Grant 2027. Application deadline: {ahead}.")
    assert checks(monkeypatch, opened) == {"queued": 1}
    assert [t.target for t in tasks()] == [id]
    assert read(id).status == "archived"


def test_archived_listing_without_a_new_cycle_waits(monkeypatch):
    staff("admin")
    id = add(status="archived", deadline_date=opp_service.today() - timedelta(days=9))
    assert checks(monkeypatch, page("Seed Grant. Thanks to all applicants.")) == {
        "closed": 1
    }
    assert tasks() == [] and read(id).source_hash
    later = utcnow_naive() + timedelta(days=31)
    assert checks(
        monkeypatch, page("Seed Grant. Thanks to all applicants."), now=later
    ) == {"unchanged": 1}


def agent_result(id, *, verified, scheduled=True):
    async def go():
        async with SessionLocal() as session:
            started = utcnow_naive()
            if verified:
                row = await session.get(Opportunity, id)
                row.verified_at = utcnow_naive() + timedelta(seconds=1)
            session.add(
                PageCache(
                    url=normalized_url(URL),
                    content_hash="agent-read",
                    expires_at=utcnow_naive() + timedelta(hours=1),
                )
            )
            task = ScanTask(
                target=id, metrics={"scheduled_check": True} if scheduled else {}
            )
            await freshness.record_agent_check(session, task, started)
            await session.commit()

    run(go())
    return read(id)


def test_agent_check_outcomes():
    confirmed = agent_result(add(), verified=True)
    assert (
        confirmed.check_outcome == "verified" and confirmed.source_hash == "agent-read"
    )
    run(_clean())
    lost = agent_result(add(), verified=False)
    assert lost.status == "in_review" and lost.review_reason == "source_changed"
    run(_clean())
    staff_run = agent_result(add(), verified=False, scheduled=False)
    assert staff_run.status == "published" and staff_run.check_outcome == "unconfirmed"
    run(_clean())
    closed = agent_result(add(status="archived"), verified=False)
    assert closed.check_outcome == "closed" and closed.source_hash == "agent-read"


def test_check_scans_do_not_notify_their_owner():
    owner, _ = staff("admin")

    async def go():
        async with SessionLocal() as session:
            scan = Scan(
                user_id=owner,
                region="Ghana",
                categories=["startup"],
                focus=freshness.CHECK_FOCUS,
            )
            session.add(scan)
            await session.flush()
            calls = []

            async def finished(session, scan):
                calls.append(scan.id)

            from api.notifications import events

            original = events.scan_finished
            events.scan_finished = finished
            try:
                await scan_service.note_tasks_drained(session, scan.id)
            finally:
                events.scan_finished = original
            return scan.status, calls

    assert run(go()) == ("done", [])


# --- Expiry ---------------------------------------------------------------------


def test_undated_listings_nothing_confirms_expire():
    stale = add("Stale Grant", verified_at=days_ago(130))
    never = add("Never Verified", created_at=days_ago(200))
    rolling = add("Rolling Grant", rolling=True, verified_at=days_ago(150))
    fresh = add("Fresh Grant", verified_at=days_ago(100))
    dated = add(
        "Dated Grant",
        deadline_date=opp_service.today() + timedelta(days=30),
        verified_at=days_ago(300),
    )

    async def archive():
        async with SessionLocal() as session:
            return await auto_archive(session)

    assert run(archive()) == 3
    for id in (stale, never, rolling):
        row = read(id)
        assert row.status == "archived" and row.check_outcome == "stale"
    assert read(fresh).status == read(dated).status == "published"


def test_stale_expiry_can_be_reopened_by_a_new_cycle():
    id = add(status="archived", check_outcome="stale")
    ahead = opp_service.today() + timedelta(days=20)
    agent_save("Seed Grant", ahead.isoformat())
    assert read(id).status == "published"


# --- Staff duplicate review -------------------------------------------------------


def test_possible_duplicates_dismiss_and_merge():
    _, client = staff()
    keep = add(
        "Seed Grant for Women Founders",
        slug="seed-grant",
        summary="Equity-free funding.",
        tags=["women"],
    )
    duplicate = add(
        "Seed Grants for Women Founders",
        slug="seed-grants",
        dedupe_key="accra|other",
        eligibility="Ghanaian founders",
        tags=["seed"],
        audience="public",
    )
    unrelated = add(
        "Climate Fellowship", organization="Other Org", source_url="https://x.org/c"
    )
    same_page = add(
        "Different Name Entirely", organization="Third Org", dedupe_key="third|x"
    )
    pairs = client.get("/api/admin/opportunities/duplicates").json()
    found = {frozenset((p["first"]["id"], p["second"]["id"])): p for p in pairs}
    assert found[frozenset((keep, duplicate))]["reason"] in (
        "same_page",
        "similar_title",
    )
    assert frozenset((keep, same_page)) in found
    assert not any(unrelated in pair for pair in found)

    dismissed = client.post(
        "/api/admin/opportunities/duplicates/dismiss",
        json={"first_id": same_page, "second_id": keep},
    )
    assert dismissed.status_code == 204
    pairs = client.get("/api/admin/opportunities/duplicates").json()
    assert not any(
        {p["first"]["id"], p["second"]["id"]} == {keep, same_page} for p in pairs
    )

    async def track():
        async with SessionLocal() as session:
            session.add(
                Application(
                    user_id="fresh-editor",
                    title="Seed Grants",
                    opportunity_id=duplicate,
                )
            )
            await session.commit()

    run(track())
    merged = client.post(
        f"/api/admin/opportunities/{duplicate}/merge", json={"into_id": keep}
    )
    assert merged.status_code == 200
    kept = read(keep)
    assert (
        kept.eligibility == "Ghanaian founders"
        and kept.summary == "Equity-free funding."
    )
    assert set(kept.tags) == {"women", "seed"}
    gone = read(duplicate)
    assert gone.status == "hidden" and gone.slug != "seed-grants"
    redirect = TestClient(app).get(
        "/api/public/opportunities/seed-grants", follow_redirects=False
    )
    assert redirect.status_code == 301

    async def moved():
        async with SessionLocal() as session:
            return (
                await session.execute(
                    select(Application.opportunity_id).where(
                        Application.user_id == "fresh-editor"
                    )
                )
            ).scalar_one(), await session.get(em.SlugHistory, "seed-grants")

    owner, history = run(moved())
    assert owner == keep and history.opportunity_id == keep
    hidden_target = client.post(
        f"/api/admin/opportunities/{keep}/merge", json={"into_id": duplicate}
    )
    assert hidden_target.status_code == 400


def test_aliases_rekey_existing_listings():
    _, client = staff()
    id = add("In-Country Scholarships", organization="German Academic Exchange Service")
    response = client.put(
        "/api/admin/organization-aliases",
        json={"alias": "German Academic Exchange Service", "canonical": "DAAD"},
    )
    assert response.status_code == 200
    assert read(id).dedupe_key == "daad|in country scholarships"
    listed = client.get("/api/admin/organization-aliases").json()
    assert listed == [
        {"alias": "german academic exchange service", "canonical": "daad"}
    ]
    assert (
        client.put(
            "/api/admin/organization-aliases",
            json={"alias": "DAAD", "canonical": "DAAD"},
        ).status_code
        == 400
    )
    removed = client.delete(
        "/api/admin/organization-aliases/german academic exchange service"
    )
    assert removed.status_code == 204
    assert (
        read(id).dedupe_key
        == "german academic exchange service|in country scholarships"
    )


def test_freshness_settings_round_trip():
    _, client = staff("admin")
    current = client.get("/api/admin/settings").json()
    assert current["freshness"]["recheck_days"] == 30
    current["freshness"]["max_agent_checks"] = 5
    saved = client.put("/api/admin/settings", json=current)
    assert saved.status_code == 200
    assert (
        client.get("/api/admin/settings").json()["freshness"]["max_agent_checks"] == 5
    )
    current.pop("freshness")
    assert client.put("/api/admin/settings", json=current).status_code == 200
    assert (
        client.get("/api/admin/settings").json()["freshness"]["max_agent_checks"] == 5
    )


def test_scheduled_agent_check_reopens_a_new_cycle_end_to_end(monkeypatch):
    from api import web
    from api.agent import orchestrator
    from api.agent.llm.base import LLMResponse, ToolCall
    from api.scans import queue

    staff("admin")
    today = opp_service.today()
    id = add(
        "Seed Grant 2026",
        status="archived",
        deadline="2026-01-10",
        deadline_date=today - timedelta(days=100),
    )
    ahead = today + timedelta(days=45)
    text = f"Seed Grant 2027 by Accra Fund. Application deadline: {ahead.isoformat()}."
    assert checks(monkeypatch, page(text, deadlines=[ahead.isoformat()])) == {
        "queued": 1
    }

    class Model:
        turn = 0

        async def chat(self, messages, system, tools, max_tokens=4096):
            Model.turn += 1
            if Model.turn == 1:
                assert "new cycle" in messages[0]["content"]
                return LLMResponse(
                    tool_calls=[
                        ToolCall(id="f", name="fetch_page", arguments={"url": URL})
                    ]
                )
            if Model.turn == 2:
                return LLMResponse(
                    tool_calls=[
                        ToolCall(
                            id="s",
                            name="save_opportunity",
                            arguments={
                                "title": "Seed Grant 2027",
                                "organization": "Accra Fund",
                                "category": "startup",
                                "source_url": URL,
                                "deadline": ahead.isoformat(),
                            },
                        )
                    ]
                )
            return LLMResponse(text="Reopened for 2027.")

    async def fetch(url, max_chars=None, offset=0, **kwargs):
        return text

    monkeypatch.setattr(web, "fetch_page", fetch)
    monkeypatch.setattr(orchestrator, "get_provider", lambda **kwargs: Model())

    async def process():
        async with SessionLocal() as session:
            task = (await session.execute(select(ScanTask))).scalar_one()
            task.status = TaskStatus.running
            await session.commit()
            await queue.process_claimed(session, task)
            await session.refresh(task)
            scan = await session.get(Scan, task.scan_id)
            return task.status, scan.status

    assert run(process()) == (TaskStatus.done, "done")
    row = read(id)
    assert row.status == "published" and row.title == "Seed Grant 2027"
    assert row.deadline_date == ahead and row.check_outcome == "reopened"

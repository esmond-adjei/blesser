"""Member scans: they follow the member's request, match the catalogue, read the
member's sites first, and keep crawler saves out of the member's budget."""

import asyncio
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.agent import orchestrator
from api.agent.llm.base import LLMResponse, ToolCall
from api.agent.tools import ToolContext
from api.core import egress
from api.core.db import SessionLocal
from api.core.exceptions import BadRequestError
from api.core.time import utcnow_naive
from api.main import app
from api.notifications.events import scan_summary
from api.notifications.models import Notification
from api.opportunities import service as opp_service
from api.opportunities import tasks as opp_tasks
from api.opportunities import tools as opp_tools
from api.opportunities.crawl_models import CrawlCandidate, Source
from api.opportunities.models import Opportunity
from api.scans import queue
from api.scans import service as scans
from api.scans.models import ScanFind
from tests.conftest import TEST_USER_ID

PUBLIC = "93.184.216.34"


def run(coro):
    return asyncio.run(coro)


def _token() -> str:
    return uuid.uuid4().hex[:10]


def _dns(monkeypatch, table: dict[str, str]):
    async def resolve(host, port):
        if host not in table:
            raise OSError("no such host")
        return [table[host]]

    monkeypatch.setattr(egress, "_resolve", resolve)


async def _listing(session, title: str, **fields) -> Opportunity:
    row = Opportunity(
        title=title,
        organization=fields.pop("organization", "Volta Fund"),
        category=fields.pop("category", "startup"),
        kind="grant",
        summary=fields.pop("summary", ""),
        source_url=fields.pop("source_url", f"https://volta.example/{_token()}"),
        link="",
        status=fields.pop("status", "published"),
        dedupe_key=f"volta|{title.casefold()}",
        **fields,
    )
    session.add(row)
    await session.flush()
    return row


class Script:
    """A fake model that plays back one list of tool calls per turn."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.messages = []

    def __call__(self):
        return self

    async def chat(self, **kwargs):
        self.messages.append(kwargs.get("messages"))
        if not self.turns:
            return LLMResponse(text="Saved: None\nSkipped: done")
        calls = self.turns.pop(0)
        return LLMResponse(
            tool_calls=[
                ToolCall(id=f"c{i}", name=name, arguments=args)
                for i, (name, args) in enumerate(calls)
            ]
        )


def test_member_scan_does_not_return_listings_the_member_already_has(monkeypatch):
    word = "agritech" + _token()
    script = Script(
        [
            [("search_catalogue", {"query": word})],
            [("add_catalogue_match", {"opportunity_id": "PLACEHOLDER"})],
        ]
    )
    monkeypatch.setattr(orchestrator, "get_provider", script)

    async def no_crawler(session):
        return False

    monkeypatch.setattr(opp_tasks, "_crawler_runs_in_member_scans", no_crawler)

    async def check():
        async with SessionLocal() as session:
            listing = await _listing(session, f"Volta {word} Grant")
            await _listing(session, f"Volta {word} Draft", status="in_review")
            candidate = CrawlCandidate(
                url=f"https://crawl.example/{_token()}",
                category_hints=["startup"],
                created_at=utcnow_naive() - timedelta(days=1),
            )
            session.add(candidate)
            await session.commit()
            script.turns[1][0][1]["opportunity_id"] = listing.id
            scan = await scans.start_scan(
                session, TEST_USER_ID, categories=["startup"], focus=word + " grants", kind="member"
            )
            task = await queue.claim_next_task(session, scan_id=scan.id)
            await queue.process_claimed(session, task)
            assert task.status.value == "done", task.error
            await session.refresh(candidate)
            assert candidate.status == "new" and not candidate.claim_token
            assert "pipeline_complete" not in task.metrics

            first_prompt = script.messages[0][0]["content"]
            assert "search_catalogue" in first_prompt and word in first_prompt

            detail = await scans.scan_detail(session, TEST_USER_ID, scan.id)
            assert detail["opportunities_found"] == 0
            assert detail["opportunities_added"] == 0
            assert detail["finds"] == []
            bodies = (
                await session.execute(
                    select(Notification.body).where(Notification.entity_id == scan.id)
                )
            ).scalars()
            assert scan_summary(scan.region, 0, 0) in list(bodies)
            candidate.status = "rejected"
            await session.commit()

    run(check())


def test_catalogue_search_lists_only_open_published_listings_in_the_category():
    word = "cassava" + _token()

    async def check():
        async with SessionLocal() as session:
            scan = await scans.start_scan(session, TEST_USER_ID, categories=["startup"], kind="member")
            fits = await _listing(session, f"{word} Processing Grant")
            await _listing(session, f"{word} Fellowship", category="research")
            await _listing(session, f"{word} Hidden", status="in_review")
            await _listing(
                session,
                f"{word} Closed",
                deadline_date=opp_service.today() - timedelta(days=3),
            )
            await session.commit()
            ctx = ToolContext(session=session, run=scan)
            ctx.category = "startup"
            found = await opp_tools.handle_search_catalogue(
                {"query": f"{word} unrelatedword"}, ctx
            )
            assert [r["opportunity_id"] for r in found["results"]] == [fits.id]

    run(check())


def test_catalogue_matches_only_open_published_listings():
    async def check():
        async with SessionLocal() as session:
            scan = await scans.start_scan(session, TEST_USER_ID, categories=["startup"], kind="member")
            held = await _listing(session, "Held " + _token(), status="in_review")
            closed = await _listing(
                session,
                "Closed " + _token(),
                deadline_date=opp_service.today() - timedelta(days=1),
            )
            open_ = await _listing(session, "Open " + _token())
            await session.commit()
            ctx = ToolContext(session=session, run=scan)
            for row in (held, closed):
                result = await opp_tools.handle_add_catalogue_match(
                    {"opportunity_id": row.id}, ctx
                )
                assert "error" in result
            first = await opp_tools.handle_add_catalogue_match(
                {"opportunity_id": open_.id}, ctx
            )
            again = await opp_tools.handle_add_catalogue_match(
                {"opportunity_id": open_.id}, ctx
            )
            assert first["added"] and not again["added"]
            find = await session.get(ScanFind, (scan.id, open_.id))
            assert find.via == "catalog" and not find.created

    run(check())


def test_crawler_saves_do_not_use_the_agents_budget(monkeypatch):
    monkeypatch.setattr(opp_tools.settings, "max_opportunities_per_run", 1)

    async def check():
        async with SessionLocal() as session:
            scan = await scans.start_scan(session, TEST_USER_ID, categories=["startup"], kind="member")
            crawled = await _listing(session, "Crawled " + _token())
            session.add(
                ScanFind(
                    scan_id=scan.id,
                    opportunity_id=crawled.id,
                    via="crawler",
                    created=True,
                )
            )
            await session.commit()
            assert await opp_tools._scan_created(session, scan.id) == 0
            assert await opp_tools._scan_created(session, scan.id, via="crawler") == 1
            source = f"https://grants.example/{_token()}"
            title = "Kumasi Makers Award " + _token()
            ctx = ToolContext(session=session, run=scan)
            opp_tools.record_fetch(
                ctx, source, f"{title}. Accra Fund. Deadline: 30 April 2027."
            )
            saved = await opp_tools.handle_save_opportunity(
                {
                    "title": title,
                    "organization": "Accra Fund",
                    "category": "startup",
                    "source_url": source,
                    "deadline": "2027-04-30",
                },
                ctx,
            )
            assert saved.get("created"), saved

    run(check())


def test_sweep_scans_run_the_pipeline_before_the_agent(monkeypatch):
    calls = []

    async def fake_pipeline(session, task, scan, category, on_event=None):
        calls.append("pipeline")
        return {}

    async def fake_agent(session, task, scan, category, **kwargs):
        calls.append("agent:" + ("member" if kwargs["member"] else "sweep"))
        return {"final_text": "done", "turns": 1}

    monkeypatch.setattr(opp_tasks, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(opp_tasks, "_run_agent", fake_agent)

    async def crawler_on(session):
        return True

    monkeypatch.setattr(opp_tasks, "_crawler_runs_in_member_scans", crawler_on)

    async def check():
        async with SessionLocal() as session:
            sweep = await scans.start_scan(
                session, TEST_USER_ID, categories=["startup"], kind="sweep"
            )
            member = await scans.start_scan(
                session, TEST_USER_ID, categories=["startup"], kind="member"
            )
            for scan in (sweep, member):
                task = await queue.claim_next_task(session, scan_id=scan.id)
                await opp_tasks.run_discover_opportunities(session, task, scan)
            # Without a sweep account, a member scan still clears the crawler
            # backlog, but only after its own agent.
            assert calls == ["pipeline", "agent:sweep", "agent:member", "pipeline"]

    run(check())


def test_scan_sites_must_be_public(monkeypatch):
    _dns(
        monkeypatch,
        {"grants.example": PUBLIC, "intranet.example": "10.0.0.5"},
    )

    async def check():
        assert await scans.check_sites(
            ["grants.example/calls", " https://grants.example/calls/ ", ""]
        ) == ["https://grants.example/calls"]
        for bad in (
            "http://127.0.0.1/admin",
            "intranet.example",
            "file:///etc/passwd",
            "https://user:pw@grants.example/",
        ):
            with pytest.raises(BadRequestError, match="public web address"):
                await scans.check_sites([bad])
        with pytest.raises(BadRequestError, match="couldn't find"):
            await scans.check_sites(["nowhere.example"])
        with pytest.raises(BadRequestError, match="at most 5"):
            await scans.check_sites([f"grants.example/{i}" for i in range(6)])

    run(check())


def test_scan_route_rejects_private_sites_and_keeps_good_ones(monkeypatch):
    _dns(monkeypatch, {"grants.example": PUBLIC})
    client = TestClient(app)
    bad = client.post(
        "/api/app/scans",
        json={"categories": ["startup"], "sites": ["http://169.254.169.254/latest"]},
    )
    assert bad.status_code == 400
    too_many = client.post(
        "/api/app/scans",
        json={"categories": ["startup"], "sites": ["grants.example"] * 6},
    )
    assert too_many.status_code == 422
    good = client.post(
        "/api/app/scans",
        json={"categories": ["startup"], "sites": ["grants.example/calls"]},
    )
    assert good.status_code == 200, good.text
    assert good.json()["sites"] == ["https://grants.example/calls"]
    assert good.json()["kind"] == "member"
    client.post(f"/api/app/scans/{good.json()['id']}/cancel")


def test_finds_on_member_sites_wait_for_review(monkeypatch):
    token = _token()
    site = f"https://{token}.example/calls"

    async def check():
        async with SessionLocal() as session:
            scan = await scans.start_scan(
                session, TEST_USER_ID, categories=["startup"], sites=[site], kind="member"
            )
            ctx = ToolContext(session=session, run=scan)
            ctx.member_hosts = await opp_tasks.member_only_hosts(session, scan.sites)
            assert ctx.member_hosts == {f"{token}.example"}
            title = "Tamale Youth Grant " + token
            page = f"{site}/youth"
            opp_tools.record_fetch(ctx, page, f"{title}. Tamale Trust.")
            saved = await opp_tools.handle_save_opportunity(
                {
                    "title": title,
                    "organization": "Tamale Trust",
                    "category": "startup",
                    "source_url": page,
                },
                ctx,
            )
            row = await session.get(Opportunity, saved["opportunity_id"])
            assert row.status == "in_review" and row.review_reason == "agent_find"
            assert f"{token}.example" in row.editor_note
            detail = await scans.scan_detail(session, TEST_USER_ID, scan.id)
            assert [(f["title"], f["in_review"]) for f in detail["finds"]] == [
                (title, True)
            ]
            # A member site that is already an enabled staff source is trusted.
            session.add(Source(url=f"https://{token}.example/feed.xml", kind="rss"))
            await session.commit()
            assert await opp_tasks.member_only_hosts(session, [site]) == set()

    run(check())


def test_member_prompt_lists_sites_and_order():
    text = opp_tasks.user_message(
        region="Ghana",
        category="student",
        focus="nursing scholarships",
        today="2026-11-20",
        known=[],
        sites=["https://moh.example/scholarships"],
        member=True,
    )
    assert "https://moh.example/scholarships" in text
    assert text.index("search_catalogue") < text.index("Read the member's sites")
    sweep = opp_tasks.user_message(
        region="Ghana", category="student", focus="", today="2026-11-20", known=[]
    )
    assert "search_catalogue" not in sweep and "member's sites" not in sweep


def test_scan_results_leave_out_listings_already_in_the_catalogue():
    async def check():
        async with SessionLocal() as session:
            old = await _listing(session, f"Already listed {_token()}")
            new = await _listing(session, f"Newly found {_token()}", status="in_review")
            scan = await scans.start_scan(session, TEST_USER_ID, categories=["startup"], kind="member")
            session.add_all(
                [
                    ScanFind(
                        scan_id=scan.id,
                        opportunity_id=old.id,
                        created=False,
                        updated=True,
                    ),
                    ScanFind(scan_id=scan.id, opportunity_id=new.id, created=True),
                ]
            )
            await session.commit()
            detail = await scans.scan_detail(session, TEST_USER_ID, scan.id)
            assert [f["opportunity_id"] for f in detail["finds"]] == [new.id]
            assert detail["opportunities_found"] == 1
            await scans.cancel_scan(session, TEST_USER_ID, scan.id)

    run(check())


def test_a_member_can_open_their_own_scan_finds_before_review():
    from api.auth.models import User

    other_id = "owner-" + uuid.uuid4().hex[:10]

    async def setup():
        async with SessionLocal() as session:
            session.add(
                User(
                    id=other_id,
                    email=f"{other_id}@example.com",
                    password_hash="x",
                    email_verified_at=utcnow_naive(),
                )
            )
            mine = await scans.start_scan(session, TEST_USER_ID, categories=["startup"], kind="member")
            theirs = await scans.start_scan(session, other_id, categories=["startup"], kind="member")
            own = await _listing(
                session, f"Mine {_token()}", status="in_review", scan_id=mine.id
            )
            other = await _listing(
                session, f"Theirs {_token()}", status="in_review", scan_id=theirs.id
            )
            session.add(ScanFind(scan_id=mine.id, opportunity_id=own.id, created=True))
            await session.commit()
            for scan in (mine, theirs):
                await scans.cancel_scan(session, scan.user_id, scan.id)
            return own.id, other.id, mine.id

    own, other, scan_id = run(setup())
    client = TestClient(app)
    opened = client.get(f"/api/app/opportunities/{own}")
    assert opened.status_code == 200 and opened.json()["in_review"] is True
    assert client.get(f"/api/app/opportunities/{other}").status_code == 404
    assert client.get(f"/api/app/opportunities/{own}/calendar.ics").status_code == 200
    [find] = client.get(f"/api/app/scans/{scan_id}").json()["finds"]
    assert find["opportunity_id"] == own and find["in_review"] is True

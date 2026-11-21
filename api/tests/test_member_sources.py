"""My sources: members' saved sites, checked on a schedule as `sources` scans."""

import asyncio
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from api.auth.models import User
from api.core import egress
from api.core.db import SessionLocal
from api.core.exceptions import BadRequestError, ConflictError, RateLimitError
from api.core.time import utcnow_naive
from api.main import app
from api.notifications import events
from api.notifications.models import Notification
from api.opportunities import tasks as opp_tasks
from api.opportunities.models import Opportunity
from api.scans import service as scans
from api.scans import sources
from api.scans.models import Scan, ScanFind, ScanTask
from tests.conftest import TEST_USER_ID

PUBLIC = "93.184.216.34"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    async def resolve(host, port):
        if host.endswith(".internal"):
            return ["10.1.2.3"]
        if host.endswith(".example"):
            return [PUBLIC]
        raise OSError("no such host")

    monkeypatch.setattr(egress, "_resolve", resolve)


def _user() -> str:
    user_id = "src-" + uuid.uuid4().hex[:10]

    async def go():
        async with SessionLocal() as session:
            session.add(
                User(
                    id=user_id,
                    email=f"{user_id}@example.com",
                    password_hash="x",
                    email_verified_at=utcnow_naive(),
                )
            )
            await session.commit()

    run(go())
    return user_id


async def _scans(session, user_id: str) -> list[Scan]:
    return list(
        (
            await session.execute(
                select(Scan).where(Scan.user_id == user_id).order_by(Scan.created_at)
            )
        )
        .scalars()
        .all()
    )


def test_members_add_up_to_the_limit_without_duplicates(monkeypatch):
    monkeypatch.setattr(sources.settings, "member_sources_max", 2)
    user, other = _user(), _user()

    async def check():
        async with SessionLocal() as session:
            first = await sources.add_source(
                session, user, url="ug.example/scholarships", category="student"
            )
            assert first.url == "https://ug.example/scholarships"
            with pytest.raises(ConflictError):
                await sources.add_source(
                    session,
                    user,
                    url="https://www.ug.example/scholarships/",
                    category="student",
                )
            await session.rollback()
            with pytest.raises(BadRequestError, match="public web address"):
                await sources.add_source(
                    session, user, url="http://db.internal/", category="startup"
                )
            await session.rollback()
            await sources.add_source(
                session, user, url="mest.example", category="startup"
            )
            with pytest.raises(BadRequestError, match="up to 2"):
                await sources.add_source(
                    session, user, url="third.example", category="startup"
                )
            await session.rollback()
            # Another member may save the same site.
            await sources.add_source(
                session, other, url="ug.example/scholarships", category="student"
            )

    run(check())


def test_due_sources_start_one_private_check_per_category():
    user = _user()

    async def check():
        async with SessionLocal() as session:
            for url, category, note in (
                ("ug.example/scholarships", "student", "nursing"),
                ("knust.example/grad", "student", ""),
                ("mest.example", "startup", "pre-seed"),
                ("paused.example", "startup", ""),
            ):
                row = await sources.add_source(
                    session, user, url=url, category=category, note=note
                )
            row.paused = True
            await session.commit()

            assert await sources.check_due_sources(session) >= 2
            mine = await _scans(session, user)
            assert sorted((s.categories[0], len(s.sites)) for s in mine) == [
                ("startup", 1),
                ("student", 2),
            ]
            assert {s.kind for s in mine} == {"sources"}
            student = next(s for s in mine if s.categories == ["student"])
            assert "nursing" in student.focus
            # Not due again until the next interval, and a running check blocks.
            await sources.check_due_sources(session)
            assert len(await _scans(session, user)) == len(mine)
            rows = await sources.list_sources(session, user)
            active = [r for r in rows if not r.paused]
            assert all(
                r.next_check_at > utcnow_naive() + timedelta(days=6) for r in active
            )
            paused = next(r for r in rows if r.paused)
            assert paused.last_checked_at is None
            assert sources.source_out(paused)["next_check_at"] is None

            # Source checks never use the member's scan quota.
            allowance = await scans.scan_allowance(session, user)
            assert allowance["left_this_hour"] == allowance["per_hour"]

            with pytest.raises(RateLimitError):
                await sources.check_now(session, user)

    run(check())


def test_disabled_members_are_not_checked():
    user = _user()

    async def check():
        async with SessionLocal() as session:
            await sources.add_source(
                session, user, url="quiet.example", category="research"
            )
            (await session.get(User, user)).disabled_at = utcnow_naive()
            await session.commit()
            await sources.check_due_sources(session)
            assert await _scans(session, user) == []

    run(check())


def test_source_checks_read_sites_without_web_search(monkeypatch):
    seen = {}

    async def fake_agent(system, message, ctx, **kwargs):
        seen["tools"] = kwargs["tools"]
        seen["message"] = message
        return {"final_text": "Saved: None", "turns": 1}

    monkeypatch.setattr(opp_tasks, "run_agent_task", fake_agent)

    async def crawler_on(session):
        return True

    monkeypatch.setattr(opp_tasks, "_crawler_runs_in_member_scans", crawler_on)
    pipeline_calls = []

    async def fake_pipeline(*args, **kwargs):
        pipeline_calls.append(1)

    monkeypatch.setattr(opp_tasks, "run_pipeline", fake_pipeline)

    async def check():
        async with SessionLocal() as session:
            scan = await scans.start_scan(
                session,
                TEST_USER_ID,
                categories=["research"],
                sites=["https://lab.example/calls"],
                kind="sources",
            )
            task = (
                await session.execute(
                    select(ScanTask).where(ScanTask.scan_id == scan.id)
                )
            ).scalar_one()
            await opp_tasks.run_discover_opportunities(session, task, scan)
            assert "search_web" not in seen["tools"]
            assert {"fetch_page", "search_catalogue"} <= set(seen["tools"])
            assert "add_catalogue_match" not in seen["tools"]
            assert "does not search the web" in seen["message"]
            assert "https://lab.example/calls" in seen["message"]
            assert pipeline_calls == []
            await scans.cancel_scan(session, TEST_USER_ID, scan.id)

    run(check())


def test_finished_checks_credit_sources_and_stay_quiet_when_empty():
    user = _user()

    async def check():
        async with SessionLocal() as session:
            await sources.add_source(
                session, user, url="ug.example/scholarships", category="student"
            )
            await sources.add_source(
                session, user, url="knust.example", category="student"
            )
            (scan,) = await sources.start_checks(session, user, due_only=True)
            opp = Opportunity(
                title="UG Nursing Bursary " + uuid.uuid4().hex[:6],
                category="student",
                source_url="https://www.ug.example/scholarships/nursing",
                status="in_review",
                dedupe_key="ug|" + uuid.uuid4().hex,
                scan_id=scan.id,
            )
            session.add(opp)
            await session.flush()
            session.add(
                ScanFind(
                    scan_id=scan.id,
                    opportunity_id=opp.id,
                    source_url=opp.source_url,
                    via="agent",
                    created=True,
                )
            )
            await session.execute(delete(ScanTask).where(ScanTask.scan_id == scan.id))
            await session.commit()
            await scans.note_tasks_drained(session, scan.id)
            await session.commit()
            rows = {r.url: r.finds for r in await sources.list_sources(session, user)}
            assert rows == {
                "https://ug.example/scholarships": 1,
                "https://knust.example": 0,
            }
            notes = (
                await session.execute(
                    select(Notification.body).where(Notification.entity_id == scan.id)
                )
            ).scalars()
            assert [n for n in notes] == [events.scan_summary(scan.region, 1, 1)]

            empty = await scans.start_scan(
                session, user, categories=["student"], kind="sources"
            )
            await session.commit()
            assert await events.scan_finished(session, empty) is False

    run(check())


def test_source_routes_round_trip():
    async def clear():
        async with SessionLocal() as session:
            await session.execute(
                delete(Scan).where(Scan.user_id == TEST_USER_ID, Scan.kind == "sources")
            )
            await session.commit()

    run(clear())
    client = TestClient(app)
    for row in client.get("/api/app/sources").json()["sources"]:
        client.delete(f"/api/app/sources/{row['id']}")
    bad = client.post(
        "/api/app/sources", json={"url": "http://10.0.0.1/", "category": "startup"}
    )
    assert bad.status_code == 400
    created = client.post(
        "/api/app/sources",
        json={"url": "grants.example/open", "category": "startup", "note": "agritech"},
    )
    assert created.status_code == 201, created.text
    source = created.json()
    listing = client.get("/api/app/sources").json()
    assert listing["max_sources"] == 10 and listing["check_days"] == 7
    assert [s["id"] for s in listing["sources"]] == [source["id"]]
    paused = client.patch(f"/api/app/sources/{source['id']}", json={"paused": True})
    assert paused.json()["paused"] is True and paused.json()["next_check_at"] is None
    resumed = client.patch(f"/api/app/sources/{source['id']}", json={"paused": False})
    assert resumed.json()["next_check_at"] is not None
    checked = client.post("/api/app/sources/check")
    assert checked.status_code == 202, checked.text
    assert checked.json()[0]["kind"] == "sources"
    assert checked.json()[0]["sites"] == ["https://grants.example/open"]
    for scan in checked.json():
        client.post(f"/api/app/scans/{scan['id']}/cancel")
    assert client.post("/api/app/sources/check").status_code == 429
    assert client.delete(f"/api/app/sources/{source['id']}").status_code == 204
    assert client.get("/api/app/sources").json()["sources"] == []

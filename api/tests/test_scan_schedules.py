"""Scan schedules: member scans that repeat weekly, and staff schedules (the sweep)."""

import asyncio
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from api.agent.tools.context import ToolContext
from api.auth import security
from api.auth.models import RefreshToken, User
from api.core import egress
from api.core.db import SessionLocal
from api.core.exceptions import BadRequestError, ConflictError
from api.core.time import utcnow_naive
from api.main import app
from api.notifications.models import Notification
from api.opportunities import tasks as opp_tasks
from api.opportunities import tools as opp_tools
from api.opportunities.dedupe import key_for
from api.opportunities.models import Opportunity
from api.scans import schedules
from api.scans import service as scans
from api.scans.models import Scan, ScanFind, ScanSchedule, ScanTask, TaskStatus
from tests.conftest import TEST_USER_ID

PUBLIC = "93.184.216.34"


def run(coro):
    return asyncio.run(coro)


def _token() -> str:
    return uuid.uuid4().hex[:10]


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """Schedules are global to the hourly pass: start every test with none."""

    async def resolve(host, port):
        if host.endswith(".example"):
            return [PUBLIC]
        raise OSError("no such host")

    monkeypatch.setattr(egress, "_resolve", resolve)

    async def clear():
        async with SessionLocal() as session:
            await session.execute(update(Scan).values(schedule_id=None))
            await session.execute(delete(ScanSchedule))
            await session.commit()

    run(clear())
    yield
    run(clear())


def _config(monkeypatch, **values):
    async def config(session):
        return {**schedules.defaults(), **values}

    monkeypatch.setattr(schedules, "_config", config)


def _staff_owner(monkeypatch, owner):
    async def run_as(session):
        return owner

    monkeypatch.setattr(schedules, "run_as_staff", run_as)


def _user(role: str = "member", **fields) -> str:
    user_id = "sch-" + _token()

    async def go():
        async with SessionLocal() as session:
            session.add(
                User(
                    id=user_id,
                    email=f"{user_id}@example.com",
                    password_hash="x",
                    role=role,
                    email_verified_at=utcnow_naive(),
                    **fields,
                )
            )
            await session.commit()

    run(go())
    return user_id


async def _scan(session, user_id: str, **kwargs) -> Scan:
    return await scans.start_scan(
        session, user_id, categories=kwargs.pop("categories", ["startup"]), **{"kind": "member", **kwargs}
    )


async def _finish(session, scan: Scan) -> None:
    """Close the scan's tasks and let the scan conclude as the worker would."""
    await session.execute(
        update(ScanTask)
        .where(ScanTask.scan_id == scan.id)
        .values(status=TaskStatus.done, finished_at=utcnow_naive())
    )
    await session.commit()
    await scans.note_tasks_drained(session, scan.id)
    await session.commit()


async def _listing(session, title: str, **fields) -> Opportunity:
    row = Opportunity(
        title=title,
        organization="Volta Fund",
        category="startup",
        kind="grant",
        summary="",
        source_url=f"https://volta.example/{_token()}",
        link="",
        status=fields.pop("status", "published"),
        dedupe_key=await key_for(session, "Volta Fund", title),
        **fields,
    )
    session.add(row)
    await session.flush()
    return row


async def _schedule(session, user_id: str) -> ScanSchedule:
    return (
        await session.execute(
            select(ScanSchedule).where(ScanSchedule.user_id == user_id)
        )
    ).scalar_one()


# --- members repeat their scans ---------------------------------------------------


def test_repeating_a_scan_starts_a_week_later_within_the_limit(monkeypatch):
    _config(monkeypatch, member_max=2)
    user = _user()

    async def check():
        async with SessionLocal() as session:
            first = await _scan(
                session, user, focus="agritech", sites=["https://mest.example"]
            )
            row = await schedules.repeat_scan(session, user, first.id)
            assert row.audience == "member" and row.interval_hours == 168
            assert row.focus == "agritech" and row.sites == ["https://mest.example"]
            assert row.next_run_at == first.created_at + timedelta(days=7)
            assert row.last_scan_id == first.id and row.runs == 0
            await session.refresh(first)
            assert first.schedule_id == row.id

            with pytest.raises(ConflictError):
                await schedules.repeat_scan(session, user, first.id)
            await session.rollback()

            # Same request with the default region spelled out is still a repeat.
            same = await _scan(
                session,
                user,
                focus="agritech",
                sites=["https://mest.example"],
                region="ghana",
            )
            with pytest.raises(ConflictError):
                await schedules.repeat_scan(session, user, same.id)
            await session.rollback()

            other = await _scan(session, user, categories=["research"])
            await schedules.repeat_scan(session, user, other.id)
            third = await _scan(session, user, categories=["student"])
            with pytest.raises(BadRequestError, match="up to 2"):
                await schedules.repeat_scan(session, user, third.id)
            await session.rollback()

            sweep = await _scan(session, user, kind="sweep")
            with pytest.raises(BadRequestError, match="Only scans you started"):
                await schedules.repeat_scan(session, user, sweep.id)

    run(check())


def test_member_routes_repeat_pause_resume_and_stop(monkeypatch):
    _config(monkeypatch, member_max=1)
    client = TestClient(app)
    started = client.post(
        "/api/app/scans",
        json={
            "categories": ["startup"],
            "focus": "fintech " + _token(),
            "repeat": True,
        },
    )
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["schedule_id"] and body["kind"] == "member"

    # The limit is checked before a second scan starts, so it costs nothing.
    async def count():
        async with SessionLocal() as session:
            return len(
                (
                    await session.execute(
                        select(Scan.id).where(Scan.user_id == TEST_USER_ID)
                    )
                )
                .scalars()
                .all()
            )

    before = run(count())
    refused = client.post(
        "/api/app/scans", json={"categories": ["research"], "repeat": True}
    )
    assert refused.status_code == 400
    assert run(count()) == before

    listed = client.get("/api/app/scans/schedules").json()
    assert listed["max_schedules"] == 1 and listed["interval_hours"] == 168
    (schedule,) = listed["schedules"]
    assert schedule["id"] == body["schedule_id"]
    assert schedule["last_run"]["scan_id"] == body["id"]

    paused = client.patch(
        f"/api/app/scans/schedules/{schedule['id']}", json={"paused": True}
    ).json()
    assert paused["paused"] and paused["next_run_at"] is None
    resumed = client.patch(
        f"/api/app/scans/schedules/{schedule['id']}",
        json={"paused": False, "focus": "payments"},
    ).json()
    assert not resumed["paused"] and resumed["focus"] == "payments"
    bad = client.patch(
        f"/api/app/scans/schedules/{schedule['id']}",
        json={"sites": ["http://db.internal"]},
    )
    assert bad.status_code == 400

    assert (
        client.delete(f"/api/app/scans/schedules/{schedule['id']}").status_code == 204
    )
    assert client.get("/api/app/scans/schedules").json()["schedules"] == []
    # The scan it repeated stays.
    assert client.get(f"/api/app/scans/{body['id']}").status_code == 200


def test_members_cannot_touch_other_schedules():
    owner = _user()

    async def make():
        async with SessionLocal() as session:
            scan = await _scan(session, owner)
            return (await schedules.repeat_scan(session, owner, scan.id)).id

    schedule_id = run(make())
    client = TestClient(app)
    assert (
        client.patch(
            f"/api/app/scans/schedules/{schedule_id}", json={"paused": True}
        ).status_code
        == 404
    )
    assert client.delete(f"/api/app/scans/schedules/{schedule_id}").status_code == 404


# --- the hourly pass --------------------------------------------------------------


def _due(session_row: ScanSchedule) -> None:
    session_row.next_run_at = utcnow_naive() - timedelta(minutes=1)


def test_due_member_schedules_run_once_and_move_a_week_on(monkeypatch):
    _config(monkeypatch)
    _staff_owner(monkeypatch, None)
    user = _user()

    async def check():
        async with SessionLocal() as session:
            first = await _scan(
                session, user, focus="solar", sites=["https://mest.example"]
            )
            await _finish(session, first)
            row = await schedules.repeat_scan(session, user, first.id)
            assert await schedules.run_due(session) == 0  # not due for a week
            _due(row)
            await session.commit()

            now = utcnow_naive()
            assert await schedules.run_due(session, now) == 1
            await session.refresh(row)
            assert row.runs == 1 and row.last_run_at == now
            assert row.next_run_at == now + timedelta(days=7)
            scan = await session.get(Scan, row.last_scan_id)
            assert scan.kind == "scheduled" and scan.schedule_id == row.id
            assert scan.focus == "solar" and scan.sites == ["https://mest.example"]
            assert scan.categories == ["startup"]

            # Never two runs of one schedule at once, even when it falls due again.
            _due(row)
            await session.commit()
            assert await schedules.run_due(session) == 0
            await _finish(session, scan)
            assert await schedules.run_due(session) == 1

    run(check())


def test_scheduled_runs_skip_the_members_quota(monkeypatch):
    _config(monkeypatch)
    _staff_owner(monkeypatch, None)

    async def check():
        async with SessionLocal() as session:
            scan = await _scan(session, TEST_USER_ID, kind="scheduled")
            assert scan.kind == "scheduled"
            allowance = await scans.scan_allowance(session, TEST_USER_ID)
            return allowance

    before = TestClient(app).get("/api/app/scans/allowance").json()
    run(check())
    after = TestClient(app).get("/api/app/scans/allowance").json()
    assert after["left_today"] == before["left_today"]


def test_paused_disabled_and_capped_schedules_wait(monkeypatch):
    _config(monkeypatch, runs_per_hour=2)
    _staff_owner(monkeypatch, None)
    users = [_user() for _ in range(4)]
    disabled = _user(disabled_at=utcnow_naive())

    async def check():
        async with SessionLocal() as session:
            rows = []
            for user in [*users, disabled]:
                scan = await _scan(session, user)
                await _finish(session, scan)
                row = await schedules.repeat_scan(session, user, scan.id)
                _due(row)
                rows.append(row)
            rows[0].paused = True
            await session.commit()

            assert await schedules.run_due(session) == 2  # the hourly cap
            assert await schedules.run_due(session) == 1  # the rest, next pass
            assert await schedules.run_due(session) == 0
            for row in rows:
                await session.refresh(row)
            assert rows[0].runs == 0  # paused
            assert rows[4].runs == 0  # disabled account
            assert sorted(r.runs for r in rows[1:4]) == [1, 1, 1]

            _config(monkeypatch, runs_per_hour=0)
            for row in rows[1:4]:
                _due(row)
            await session.commit()
            assert await schedules.run_due(session) == 0

    run(check())


def test_the_daily_token_budget_holds_runs_until_tomorrow(monkeypatch):
    _staff_owner(monkeypatch, None)
    user = _user()

    async def check():
        async with SessionLocal() as session:
            first = await _scan(session, user)
            await _finish(session, first)
            row = await schedules.repeat_scan(session, user, first.id)
            _due(row)
            await session.commit()
            # An earlier scheduled run today used 5,000 tokens.
            spent = await _scan(session, user, kind="scheduled", schedule_id=row.id)
            await session.execute(
                update(ScanTask)
                .where(ScanTask.scan_id == spent.id)
                .values(input_tokens=4000, output_tokens=1000)
            )
            await _finish(session, spent)
            assert await schedules.tokens_today(session) >= 5000

            _config(monkeypatch, daily_token_budget=5000)
            assert await schedules.run_due(session) == 0
            # Tomorrow the budget starts again.
            tomorrow = utcnow_naive().replace(hour=0, minute=5) + timedelta(days=1)
            assert await schedules.run_due(session, tomorrow) == 1

    run(check())


def test_schedules_of_members_away_for_sixty_days_pause(monkeypatch):
    _config(monkeypatch)
    _staff_owner(monkeypatch, None)
    away, active = _user(), _user()

    async def check():
        async with SessionLocal() as session:
            long_ago = utcnow_naive() - timedelta(days=90)
            rows = {}
            for user in (away, active):
                scan = await _scan(session, user)
                await _finish(session, scan)
                row = await schedules.repeat_scan(session, user, scan.id)
                row.created_at = row.touched_at = long_ago
                _due(row)
                rows[user] = row
            session.add(
                RefreshToken(
                    user_id=active,
                    token_hash="sch-" + _token(),
                    expires_at=utcnow_naive() + timedelta(days=30),
                    created_at=utcnow_naive() - timedelta(days=2),
                )
            )
            await session.commit()

            assert await schedules.run_due(session) == 1
            await session.refresh(rows[away])
            await session.refresh(rows[active])
            assert rows[away].paused and rows[away].pause_reason == "inactive"
            assert rows[active].runs == 1

            # Resuming counts as activity.
            await schedules.update_member(
                session, away, rows[away].id, {"paused": False}
            )
            assert await schedules.run_due(session) == 1

    run(check())


def test_staff_schedules_run_as_sweeps_for_the_scheduled_account(monkeypatch):
    _config(monkeypatch)
    owner = _user("admin")
    _staff_owner(monkeypatch, None)

    async def check():
        async with SessionLocal() as session:
            row = await schedules.create_staff(
                session,
                owner,
                {
                    "name": "Research grants",
                    "categories": ["research", "startup"],
                    "region": "West Africa",
                    "focus": "climate research",
                    "interval_hours": 72,
                },
            )
            await session.commit()
            # Without an account to run as, nothing starts and the slot is kept.
            assert await schedules.run_due(session) == 0
            await session.refresh(row)
            assert row.runs == 0
            assert not await schedules.staff_schedules_active(session)

            _staff_owner(monkeypatch, owner)
            assert await schedules.staff_schedules_active(session)
            assert await schedules.run_due(session) == 1
            await session.refresh(row)
            scan = await session.get(Scan, row.last_scan_id)
            assert scan.kind == "sweep" and scan.user_id == owner
            assert scan.categories == ["startup", "research"]
            assert scan.region == "West Africa" and scan.focus == "climate research"
            assert row.next_run_at - row.last_run_at == timedelta(hours=72)

            with pytest.raises(BadRequestError):
                await schedules.update_staff(session, row.id, {"interval_hours": 5})
            await schedules.update_staff(session, row.id, {"paused": True})
            await session.commit()
            assert not await schedules.staff_schedules_active(session)

    run(check())


def test_member_scans_run_the_crawler_only_without_a_staff_schedule(monkeypatch):
    _staff_owner(monkeypatch, "someone")

    async def check():
        async with SessionLocal() as session:
            assert await opp_tasks._crawler_runs_in_member_scans(session)
            await schedules.create_staff(
                session, None, {"categories": ["startup"], "interval_hours": 24}
            )
            await session.commit()
            assert not await opp_tasks._crawler_runs_in_member_scans(session)

    run(check())


# --- after a run ------------------------------------------------------------------


def test_quiet_runs_pause_the_schedule_after_four_weeks(monkeypatch):
    _config(monkeypatch)
    _staff_owner(monkeypatch, None)
    user = _user()

    async def notes(session):
        return (
            (
                await session.execute(
                    select(Notification).where(Notification.user_id == user)
                )
            )
            .scalars()
            .all()
        )

    async def run_once(session, row, find=None):
        _due(row)
        await session.commit()
        assert await schedules.run_due(session) == 1
        await session.refresh(row)
        scan = await session.get(Scan, row.last_scan_id)
        if find is not None:
            session.add(
                ScanFind(scan_id=scan.id, opportunity_id=find.id, via="catalog")
            )
            await session.commit()
        await _finish(session, scan)
        await session.refresh(row)
        return scan

    async def check():
        async with SessionLocal() as session:
            listing = await _listing(session, "Volta Seed Grant " + _token())
            first = await _scan(session, user)
            session.add(
                ScanFind(scan_id=first.id, opportunity_id=listing.id, via="catalog")
            )
            await session.commit()
            await _finish(session, first)
            before = len(await notes(session))
            row = await schedules.repeat_scan(session, user, first.id)

            # Finding the same listing again is not news.
            await run_once(session, row, find=listing)
            assert row.empty_runs == 1
            assert len(await notes(session)) == before

            fresh = await _listing(session, "Volta Growth Grant " + _token())
            await run_once(session, row, find=fresh)
            assert row.empty_runs == 0
            weekly = [
                n for n in await notes(session) if n.title == "Weekly scan finished"
            ]
            assert len(weekly) == 1
            assert "1 new opportunity" in weekly[0].body

            for _ in range(4):
                await run_once(session, row)
            assert row.paused and row.pause_reason == "empty"
            titles = [n.title for n in await notes(session)]
            assert titles.count("Weekly scan paused") == 1
            assert titles.count("Weekly scan finished") == 1  # quiet runs said nothing
            assert await schedules.run_due(session) == 0

            out = await schedules.schedule_out(session, row)
            assert out["pause_reason"] == "empty" and out["next_run_at"] is None

    run(check())


def test_saves_that_refresh_a_listing_count_as_updated():
    async def check():
        async with SessionLocal() as session:
            title = "Accra Climate Fellowship " + _token()
            existing = await _listing(session, title, deadline="", deadline_date=None)
            await session.commit()
            scan = await _scan(session, TEST_USER_ID, kind="scheduled")
            source = f"https://volta.example/{_token()}"
            ctx = ToolContext(session=session, run=scan)
            opp_tools.record_fetch(
                ctx, source, f"{title}. Volta Fund. Deadline: 30 April 2027."
            )
            saved = await opp_tools.handle_save_opportunity(
                {
                    "title": title,
                    "organization": "Volta Fund",
                    "category": "startup",
                    "source_url": source,
                    "deadline": "2027-04-30",
                },
                ctx,
            )
            assert not saved.get("created"), saved
            await session.commit()
            find = await session.get(ScanFind, (scan.id, existing.id))
            assert find is not None and find.updated and not find.created
            counts = await schedules.run_counts(session, [scan.id])
            assert counts[scan.id] == {"new": 0, "updated": 1}
            detail = await scans.scan_detail(session, TEST_USER_ID, scan.id)
            assert detail["opportunities_updated"] == 1

    run(check())


def test_repeat_runs_tell_the_agent_to_refresh_known_listings():
    message = opp_tasks.user_message(
        region="Ghana",
        category="startup",
        focus="",
        today="2026-11-21",
        member=True,
        repeat=True,
    )
    assert "repeats on a schedule" in message
    plain = opp_tasks.user_message(
        region="Ghana", category="startup", focus="", today="2026-11-21"
    )
    assert "repeats on a schedule" not in plain


# --- staff routes -----------------------------------------------------------------


@pytest.mark.real_auth
def test_admins_manage_staff_schedules_and_limits():
    admin, editor = _user("admin"), _user("editor")

    def client(user_id):
        token = security.issue_access_token(user_id, "admin")
        return TestClient(app, headers={"Authorization": f"Bearer {token}"})

    assert client(editor).get("/api/admin/scan-schedules").status_code == 403
    c = client(admin)
    created = c.post(
        "/api/admin/scan-schedules",
        json={
            "name": "Student scholarships",
            "categories": ["student"],
            "focus": "nursing",
            "interval_hours": 24,
        },
    )
    assert created.status_code == 201, created.text
    schedule = created.json()
    assert schedule["audience"] == "staff" and schedule["interval_hours"] == 24
    assert (
        c.post(
            "/api/admin/scan-schedules",
            json={"categories": ["student"], "interval_hours": 5},
        ).status_code
        == 422
    )

    listed = c.get("/api/admin/scan-schedules").json()
    assert [s["id"] for s in listed["schedules"]] == [schedule["id"]]
    assert listed["intervals"] == [24, 72, 168]
    assert listed["tokens_today"] >= 0

    edited = c.patch(
        f"/api/admin/scan-schedules/{schedule['id']}",
        json={"interval_hours": 168, "paused": True},
    ).json()
    assert edited["interval_hours"] == 168 and edited["paused"]

    settings_ = c.get("/api/admin/settings").json()
    assert settings_["scheduled_scans"] == {
        "member_max": 3,
        "runs_per_hour": 10,
        "daily_token_budget": 0,
    }
    assert "sweep_hours" not in settings_

    assert c.delete(f"/api/admin/scan-schedules/{schedule['id']}").status_code == 204
    assert c.get("/api/admin/scan-schedules").json()["schedules"] == []

"""Delivery tests use their own accounts so the shared test user's rows never mix in; push is stubbed at `push.send_web_push`."""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api.applications.dates import parse_deadline
from api.applications.models import Application
from api.auth import models as auth_models
from api.core import mailer
from api.core.config import settings
from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.main import app
from api.notifications import deadlines, delivery, events, push, service
from api.notifications.models import (
    Notification,
    NotificationPreference,
    PushSubscription,
)
from api.runs import queue as run_queue
from api.runs.lifecycle import note_tasks_drained
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID

SECRET_RATIONALE = "Professor Hidden Name works on exactly your CV topic"


def _run(coro):
    return asyncio.run(coro)


def _at(*parts: int) -> datetime:
    """Naive UTC, like the database columns."""
    return datetime(*parts, tzinfo=UTC).replace(tzinfo=None)


def _new_user(verified: bool = True, **prefs) -> str:
    user_id = f"notif-{uuid.uuid4().hex[:12]}"

    async def setup():
        async with SessionLocal() as session:
            session.add(
                auth_models.User(
                    id=user_id,
                    email=f"{user_id}@example.com",
                    password_hash="x",
                    email_verified_at=_at(2026, 1, 1) if verified else None,
                )
            )
            await session.flush()
            if prefs:
                session.add(NotificationPreference(user_id=user_id, channels={}, **prefs))
            await session.commit()

    _run(setup())
    return user_id


def _new_run(user_id: str, status: str = "running") -> str:
    async def setup():
        async with SessionLocal() as session:
            run = Run(
                user_id=user_id,
                region="Canada",
                field="Machine Learning",
                interest_statement="my private research statement",
                status=status,
            )
            session.add(run)
            await session.commit()
            return run.id

    return _run(setup())


def _subscribe(user_id: str, n: int = 1) -> list[str]:
    async def setup():
        async with SessionLocal() as session:
            endpoints = []
            for _ in range(n):
                endpoint = f"https://push.example.com/{uuid.uuid4().hex}"
                session.add(
                    PushSubscription(user_id=user_id, endpoint=endpoint, p256dh="k", auth="a")
                )
                endpoints.append(endpoint)
            await session.commit()
            return endpoints

    return _run(setup())


def _rows(user_id: str, kind: str | None = None) -> list[Notification]:
    async def fetch():
        async with SessionLocal() as session:
            stmt = select(Notification).where(Notification.user_id == user_id)
            if kind:
                stmt = stmt.where(Notification.kind == kind)
            return (await session.execute(stmt.order_by(Notification.created_at))).scalars().all()

    return _run(fetch())


@pytest.fixture
def pushes(monkeypatch):
    """Stub the push sender; `statuses` maps endpoint -> HTTP status."""
    monkeypatch.setattr(settings, "vapid_public_key", "BPublicKeyForTests")
    monkeypatch.setattr(settings, "vapid_private_key", "private-key-for-tests")
    sent: list[dict] = []
    statuses: dict[str, int] = {}

    async def fake_send(endpoint, p256dh, auth, payload):
        sent.append({"endpoint": endpoint, "payload": payload})
        return statuses.get(endpoint, 201)

    monkeypatch.setattr(push, "send_web_push", fake_send)
    return sent, statuses


def _to(sent: list[dict], endpoints) -> list[dict]:
    """Pushes to these endpoints only (a pass delivers every account's rows)."""
    return [s for s in sent if s["endpoint"] in set(endpoints)]


def _deliver(now: datetime | None = None) -> int:
    async def go():
        async with SessionLocal() as session:
            return await delivery.deliver_pending(session, now=now)

    return _run(go())


def _notify(user_id: str, key: str, kind: str = "run_finished", **kw) -> bool:
    async def go():
        async with SessionLocal() as session:
            created = await service.notify(
                session,
                user_id=user_id,
                kind=kind,
                title=kw.get("title", "Run finished"),
                body=kw.get("body", "Your run finished."),
                link=kw.get("link", "/runs/x"),
                dedupe_key=key,
            )
            await session.commit()
            return created

    return _run(go())


def test_dedupe_key_is_unique_per_account():
    alice, bob = _new_user(), _new_user()
    assert _notify(alice, "run:1:done:3") is True
    assert _notify(alice, "run:1:done:3") is False
    assert _notify(bob, "run:1:done:3") is True
    assert len(_rows(alice)) == 1
    assert len(_rows(bob)) == 1


def test_rolled_back_cause_leaves_no_notification():
    user = _new_user()

    async def go():
        async with SessionLocal() as session:
            await service.notify(
                session, user_id=user, kind="run_finished", title="t", dedupe_key="rollback"
            )
            await session.rollback()

    _run(go())
    assert _rows(user) == []


def test_preferences_turn_channels_off(pushes):
    sent, _ = pushes
    user = _new_user()
    mine = _subscribe(user)

    async def set_prefs():
        async with SessionLocal() as session:
            await service.update_prefs(
                session,
                user,
                {"channels": {"run_finished": {"push": False}, "first_candidate": {"inbox": False}}},
            )

    _run(set_prefs())
    _notify(user, "a", kind="run_finished")
    _notify(user, "b", kind="first_candidate", title="First candidate saved")
    _deliver()
    assert _to(sent, mine) == []
    rows = {r.kind: r for r in _rows(user)}
    assert rows["run_finished"].delivery == "none"
    assert rows["first_candidate"].in_inbox is False

    async def inbox():
        async with SessionLocal() as session:
            return await service.list_inbox(session, user)

    listed = _run(inbox())
    assert [i["kind"] for i in listed["items"]] == ["run_finished"]
    assert listed["unread"] == 1


def test_defaults_push_for_run_finished_but_not_first_candidate(pushes):
    sent, _ = pushes
    user = _new_user()
    mine = _subscribe(user)
    _notify(user, "a", kind="run_finished")
    _notify(user, "b", kind="first_candidate")
    _deliver()
    assert [s["payload"]["kind"] for s in _to(sent, mine)] == ["run_finished"]


def test_preferences_api_round_trip_and_validation():
    client = TestClient(app)
    got = client.get("/api/notifications/preferences")
    assert got.status_code == 200, got.text
    kinds = {k["kind"]: k for k in got.json()["kinds"]}
    assert kinds["deadline"]["channels"] == {"inbox": True, "push": True, "email": True}
    assert kinds["first_candidate"]["channels"]["push"] is False
    assert "test" not in kinds

    patched = client.patch(
        "/api/notifications/preferences",
        json={
            "channels": {"deadline": {"email": False}},
            "quiet_start": "22:00",
            "quiet_end": "07:30",
            "timezone": "Europe/Berlin",
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    deadline = next(k for k in body["kinds"] if k["kind"] == "deadline")
    assert deadline["channels"] == {"inbox": True, "push": True, "email": False}
    assert (body["quiet_start"], body["quiet_end"], body["timezone"]) == (
        "22:00",
        "07:30",
        "Europe/Berlin",
    )
    assert client.patch("/api/notifications/preferences", json={"quiet_start": "25:00"}).status_code == 422
    assert client.patch("/api/notifications/preferences", json={"timezone": "Mars/Base"}).status_code == 422
    client.patch("/api/notifications/preferences", json={"quiet_start": "", "quiet_end": ""})


def test_quiet_hours_window_in_the_users_timezone():
    prefs = NotificationPreference(quiet_start="22:00", quiet_end="07:00", timezone="Asia/Tokyo")
    # 14:00 UTC is 23:00 in Tokyo: quiet.
    assert service.in_quiet_hours(prefs, _at(2026, 10, 20, 14, 0)) is True
    # 23:00 UTC is 08:00 in Tokyo: not quiet.
    assert service.in_quiet_hours(prefs, _at(2026, 10, 20, 23, 0)) is False
    daytime = NotificationPreference(quiet_start="09:00", quiet_end="17:00", timezone="UTC")
    assert service.in_quiet_hours(daytime, _at(2026, 10, 20, 12, 0)) is True
    assert service.in_quiet_hours(daytime, _at(2026, 10, 20, 17, 0)) is False
    assert service.in_quiet_hours(None, _at(2026, 10, 20, 12, 0)) is False
    assert service.in_quiet_hours(NotificationPreference(), _at(2026, 10, 20, 12, 0)) is False


def test_quiet_hours_hold_push_until_the_window_ends(pushes):
    sent, _ = pushes
    user = _new_user(quiet_start="22:00", quiet_end="07:00", timezone="UTC")
    mine = _subscribe(user)
    _notify(user, "quiet")
    _deliver(now=_at(2026, 10, 20, 23, 30))
    assert _to(sent, mine) == []
    assert _rows(user)[0].delivered_at is None
    _deliver(now=_at(2026, 10, 21, 7, 5))
    assert len(_to(sent, mine)) == 1
    assert _rows(user)[0].delivery == "push"


def test_push_reaches_every_device_and_410_removes_the_subscription(pushes):
    sent, statuses = pushes
    user = _new_user()
    alive, gone, missing = _subscribe(user, 3)
    statuses[gone] = 410
    statuses[missing] = 404
    _notify(user, "every-device")
    _deliver()
    assert {s["endpoint"] for s in _to(sent, [alive, gone, missing])} == {alive, gone, missing}

    async def remaining():
        async with SessionLocal() as session:
            return (
                await session.execute(select(PushSubscription).where(PushSubscription.user_id == user))
            ).scalars().all()

    subs = _run(remaining())
    assert [s.endpoint for s in subs] == [alive]
    assert subs[0].last_ok_at is not None


def test_push_is_a_no_op_without_vapid_keys(monkeypatch, capsys):
    monkeypatch.setattr(settings, "vapid_public_key", "")
    monkeypatch.setattr(settings, "vapid_private_key", "")
    monkeypatch.setattr(push, "_warned", False)
    called = []

    async def fake_send(*args):
        called.append(args)
        return 201

    monkeypatch.setattr(push, "send_web_push", fake_send)
    user = _new_user()
    _subscribe(user)
    _notify(user, "no-keys")
    _deliver()
    assert called == []
    assert _rows(user)[0].delivery == "none"
    assert "push is off" in capsys.readouterr().out


def test_hourly_cap_keeps_the_rest_in_the_inbox(pushes, monkeypatch):
    sent, _ = pushes
    monkeypatch.setattr(settings, "notification_hourly_cap", 2)
    user = _new_user()
    mine = _subscribe(user)
    for i in range(4):
        _notify(user, f"cap-{i}")
    _deliver()
    assert len(_to(sent, mine)) == 2
    assert sorted(r.delivery for r in _rows(user)) == ["capped", "capped", "push", "push"]


def test_push_payload_says_what_happened_and_links_only(pushes):
    """The payload carries no interest statement, professor or rationale text."""
    sent, _ = pushes
    user = _new_user()
    mine = _subscribe(user)
    run_id = _new_run(user)

    async def fire():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            await events.run_finished(session, run)
            await events.first_candidate(session, run)
            await events.run_paused(session, run, "task-1", 1)
            await events.run_attention(session, run)
            await session.commit()

    _run(fire())
    with_push = {"run_finished", "run_paused"}
    _deliver()
    sent = _to(sent, mine)
    assert {s["payload"]["kind"] for s in sent} == with_push
    for item in sent:
        payload = item["payload"]
        assert set(payload) == {"id", "kind", "title", "body", "link"}
        assert payload["link"] == f"/runs/{run_id}"
        text = str(payload)
        assert "private research statement" not in text
        assert "Hidden Name" not in text
    finished = next(s["payload"] for s in sent if s["payload"]["kind"] == "run_finished")
    assert finished["body"] == "Your run Machine Learning in Canada finished: 0 candidates."


def test_test_endpoint_without_keys_reports_push_disabled(monkeypatch):
    monkeypatch.setattr(settings, "vapid_public_key", "")
    monkeypatch.setattr(settings, "vapid_private_key", "")
    client = TestClient(app)
    config = client.get("/api/notifications/push/config").json()
    assert config == {"enabled": False, "public_key": None}
    resp = client.post("/api/notifications/test")
    assert resp.status_code == 200, resp.text
    assert resp.json()["push_enabled"] is False
    assert resp.json()["pushed"] == 0
    inbox = client.get("/api/notifications").json()
    assert inbox["items"][0]["kind"] == "test"


def test_test_email_goes_to_the_verified_address():
    resp = TestClient(app).post("/api/notifications/test-email")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"to": "test@example.com", "sent": True, "backend": "console"}
    assert mailer.outbox[-1].to == "test@example.com"


def test_subscription_routes_and_inbox_read(pushes):
    sent, _ = pushes
    client = TestClient(app)
    endpoint = f"https://push.example.com/{uuid.uuid4().hex}"
    body = {"endpoint": endpoint, "keys": {"p256dh": "key", "auth": "secret"}}
    assert client.post(
        "/api/notifications/push/subscriptions",
        json={**body, "endpoint": "http://insecure.example.com/x"},
    ).status_code == 422
    resp = client.post("/api/notifications/push/subscriptions", json=body)
    assert resp.status_code == 200, resp.text
    client.post("/api/notifications/push/subscriptions", json={**body, "keys": {"p256dh": "k2", "auth": "a2"}})
    listed = client.get("/api/notifications/push/subscriptions").json()
    assert [s["endpoint"] for s in listed].count(endpoint) == 1

    tested = client.post("/api/notifications/test").json()
    assert tested["push_enabled"] is True
    assert tested["pushed"] >= 1
    assert any(s["endpoint"] == endpoint for s in sent)

    inbox = client.get("/api/notifications").json()
    first = inbox["items"][0]
    assert first["read_at"] is None
    assert client.post(f"/api/notifications/{first['id']}/read").json() == {"marked": 1}
    client.post("/api/notifications/read-all")
    assert client.get("/api/notifications").json()["unread"] == 0

    removed = client.request(
        "DELETE", "/api/notifications/push/subscriptions", json={"endpoint": endpoint}
    )
    assert removed.json() == {"removed": 1}


def _fake_claim_for(run_id):
    async def fake_claim(session):
        task = (
            (
                await session.execute(
                    select(ResearchTask)
                    .join(Run, ResearchTask.run_id == Run.id)
                    .where(
                        ResearchTask.run_id == run_id,
                        ResearchTask.status == TaskStatus.pending,
                        Run.status == "running",
                    )
                    .order_by(ResearchTask.created_at)
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if task is None:
            return None
        task.status = TaskStatus.running
        task.attempt = (task.attempt or 0) + 1
        await session.commit()
        return task

    return fake_claim


async def _ok_handler(session, task, run, on_event=None, resume_messages=None, on_checkpoint=None):
    return {"turns": 1, "final_text": "ok", "usage": {}}


def _add_tasks(run_id: str, user_id: str, task_type: str, n: int = 1) -> None:
    async def setup():
        async with SessionLocal() as session:
            for _ in range(n):
                session.add(
                    ResearchTask(
                        user_id=user_id, run_id=run_id, task_type=task_type, status=TaskStatus.pending
                    )
                )
            await session.commit()

    _run(setup())


def test_finishing_a_run_notifies_once_with_a_link(monkeypatch, pushes):
    sent, _ = pushes
    user = _new_user()
    mine = _subscribe(user, 2)
    run_id = _new_run(user)
    _add_tasks(run_id, user, "research_professor", 2)
    monkeypatch.setitem(run_queue.TASK_HANDLERS, "research_professor", _ok_handler)
    monkeypatch.setattr(run_queue, "_claim_next_task", _fake_claim_for(run_id))
    assert _run(run_queue.process_one()) is True
    assert _rows(user, "run_finished") == []
    assert _run(run_queue.process_one()) is True
    finished = _rows(user, "run_finished")
    assert len(finished) == 1
    assert finished[0].link == f"/runs/{run_id}"

    async def drain_again():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            run.status = "running"
            await note_tasks_drained(session, run_id)
            await session.commit()

    _run(drain_again())
    assert len(_rows(user, "run_finished")) == 1
    _deliver()
    assert {s["endpoint"] for s in _to(sent, mine)} == set(mine)
    assert all(s["payload"]["link"] == f"/runs/{run_id}" for s in _to(sent, mine))


def test_drafts_ready_only_when_the_last_draft_task_finishes(monkeypatch):
    user = _new_user()
    run_id = _new_run(user)
    _add_tasks(run_id, user, "draft_email", 2)
    monkeypatch.setitem(run_queue.TASK_HANDLERS, "draft_email", _ok_handler)
    monkeypatch.setattr(run_queue, "_claim_next_task", _fake_claim_for(run_id))
    _run(run_queue.process_one())
    assert _rows(user, "drafts_ready") == []
    _run(run_queue.process_one())
    ready = _rows(user, "drafts_ready")
    assert len(ready) == 1
    assert ready[0].link == "/outbox"


def test_task_failing_for_good_asks_for_attention_once_a_day(monkeypatch):
    user = _new_user()
    run_id = _new_run(user)
    _add_tasks(run_id, user, "research_professor", 3)

    async def boom(session, task, run, on_event=None, resume_messages=None, on_checkpoint=None):
        raise RuntimeError("broken page")

    monkeypatch.setitem(run_queue.TASK_HANDLERS, "research_professor", boom)
    monkeypatch.setattr(run_queue, "_claim_next_task", _fake_claim_for(run_id))
    for _ in range(3):
        _run(run_queue.process_one())
    assert len(_rows(user, "run_attention")) == 1
    assert _rows(user, "run_attention")[0].link == f"/runs/{run_id}?tab=research_professor&status=error"


def test_first_candidate_opens_that_candidate():
    user = _new_user()
    run_id = _new_run(user)

    async def fire():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            await events.first_candidate(session, run, "cand-1")
            await session.commit()

    _run(fire())
    assert _rows(user, "first_candidate")[0].link == f"/runs/{run_id}?preview=cand-1"


def test_allowance_pause_notifies_once_for_concurrent_refusals():
    user = _new_user()
    run_id = _new_run(user)

    async def setup():
        async with SessionLocal() as session:
            ids = []
            for _ in range(3):
                task = ResearchTask(
                    user_id=user,
                    run_id=run_id,
                    task_type="research_one_professor",
                    status=TaskStatus.running,
                    attempt=1,
                )
                session.add(task)
                await session.flush()
                ids.append(task.id)
            await session.commit()
            return ids

    task_ids = _run(setup())

    async def park(task_id):
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            await run_queue._park_for_allowance(session, task, run_id, "out of allowance")

    async def all_at_once():
        await asyncio.gather(*(park(t) for t in task_ids))

    _run(all_at_once())
    paused = _rows(user, "run_paused")
    assert len(paused) == 1
    assert paused[0].link == f"/runs/{run_id}"


def test_first_candidate_notification_is_created_once():
    user = _new_user()
    run_id = _new_run(user)

    async def fire_twice():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            first = await events.first_candidate(session, run)
            second = await events.first_candidate(session, run)
            await session.commit()
            return first, second

    assert _run(fire_twice()) == (True, False)


def test_parse_deadline_only_accepts_unambiguous_dates():
    assert parse_deadline("2026-12-15") == date(2026, 12, 15)
    assert parse_deadline("15 December 2026") == date(2026, 12, 15)
    assert parse_deadline("Dec 15, 2026") == date(2026, 12, 15)
    assert parse_deadline("December 1st 2026") == date(2026, 12, 1)
    assert parse_deadline("25/12/2026") == date(2026, 12, 25)
    assert parse_deadline("12/25/2026") == date(2026, 12, 25)
    assert parse_deadline("03/04/2026") is None
    assert parse_deadline("rolling admissions") is None
    assert parse_deadline("mid-December") is None
    assert parse_deadline("2026-02-30") is None
    assert parse_deadline("") is None


def test_tracker_form_sets_deadline_date():
    client = TestClient(app)
    created = client.post(
        "/api/applications",
        json={"school": f"Deadline U {uuid.uuid4().hex[:6]}", "deadline": "2026-12-01"},
    ).json()
    assert created["deadline_date"] == "2026-12-01"
    patched = client.patch(
        f"/api/applications/{created['id']}", json={"deadline": "sometime in winter"}
    ).json()
    assert patched["deadline_date"] is None
    explicit = client.patch(
        f"/api/applications/{created['id']}", json={"deadline_date": "2027-01-10"}
    ).json()
    assert explicit["deadline_date"] == "2027-01-10"
    client.delete(f"/api/applications/{created['id']}")


def _application(user_id: str, deadline: date, status: str = "applying") -> str:
    async def setup():
        async with SessionLocal() as session:
            row = Application(
                user_id=user_id,
                school="Reminder University",
                program="PhD in Tests",
                deadline=deadline.isoformat(),
                deadline_date=deadline,
                status=status,
            )
            session.add(row)
            await session.commit()
            return row.id

    return _run(setup())


def _check(now: datetime) -> int:
    async def go():
        async with SessionLocal() as session:
            return await deadlines.check_deadlines(session, now=now)

    return _run(go())


def test_deadline_reminders_fire_once_per_threshold():
    user = _new_user(timezone="UTC")
    now = _at(2026, 11, 1, 9, 0)
    app_id = _application(user, date(2026, 11, 8))  # 7 days out
    _check(now)
    _check(now + timedelta(hours=1))
    rows = [r for r in _rows(user, "deadline") if r.entity_id == app_id]
    assert len(rows) == 1
    assert rows[0].title == "Application deadline in 7 days"
    assert rows[0].link == f"/applications/{app_id}"
    # Six days out belongs to the 7-day reminder already sent.
    _check(now + timedelta(days=1))
    assert len([r for r in _rows(user, "deadline") if r.entity_id == app_id]) == 1
    _check(now + timedelta(days=6))
    titles = [r.title for r in _rows(user, "deadline") if r.entity_id == app_id]
    assert titles == ["Application deadline in 7 days", "Application deadline tomorrow"]


def test_deadline_days_count_in_the_users_timezone():
    tokyo = _new_user(timezone="Asia/Tokyo")
    app_id = _application(tokyo, date(2026, 11, 3))
    # 23:30 UTC on Nov 1 is 08:30 on Nov 2 in Tokyo: due tomorrow there.
    _check(_at(2026, 11, 1, 23, 30))
    rows = [r for r in _rows(tokyo, "deadline") if r.entity_id == app_id]
    assert [r.title for r in rows] == ["Application deadline tomorrow"]

    # Nothing before 08:00 local.
    early = _new_user(timezone="UTC")
    early_app = _application(early, date(2026, 11, 2))
    _check(_at(2026, 11, 1, 6, 0))
    assert [r for r in _rows(early, "deadline") if r.entity_id == early_app] == []


def test_deadline_reminders_stop_once_submitted():
    user = _new_user(timezone="UTC")
    submitted = _application(user, date(2026, 11, 8), status="submitted")
    _check(_at(2026, 11, 1, 9, 0))
    assert [r for r in _rows(user, "deadline") if r.entity_id == submitted] == []


def test_deadline_email_to_verified_address_with_unsubscribe(monkeypatch):
    monkeypatch.setattr(settings, "vapid_public_key", "")
    mailer.outbox.clear()
    user = _new_user(timezone="UTC")
    unverified = _new_user(verified=False, timezone="UTC")
    _application(user, date(2026, 11, 2))
    _application(unverified, date(2026, 11, 2))
    _check(_at(2026, 11, 1, 9, 0))
    _deliver(now=_at(2026, 11, 1, 9, 1))
    to_user = [m for m in mailer.outbox if m.to == f"{user}@example.com"]
    assert len(to_user) == 1
    assert "/applications/" in to_user[0].text
    assert not [m for m in mailer.outbox if m.to == f"{unverified}@example.com"]

    link = next(line for line in to_user[0].text.splitlines() if "unsubscribe?token=" in line)
    token = link.split("token=", 1)[1].strip()
    client = TestClient(app)
    resp = client.post("/api/notifications/unsubscribe", json={"token": token})
    assert resp.status_code == 200, resp.text
    assert resp.json()["kind"] == "deadline"

    async def prefs():
        async with SessionLocal() as session:
            return service.channels_for(await service.get_prefs(session, user), "deadline")

    assert _run(prefs())["email"] is False
    assert client.post("/api/notifications/unsubscribe", json={"token": "forged"}).status_code == 400


def test_daily_digest_lists_unread_once_a_day():
    mailer.outbox.clear()
    user = _new_user(timezone="UTC", email_digest=True)
    _notify(user, "digest-1", kind="first_candidate", title="First candidate saved")
    now = utcnow_naive().replace(hour=9)

    async def go(at):
        async with SessionLocal() as session:
            return await deadlines.send_digests(session, now=at)

    _run(go(now))
    _run(go(now + timedelta(minutes=5)))
    mails = [m for m in mailer.outbox if m.to == f"{user}@example.com"]
    assert len(mails) == 1
    assert "First candidate saved" in mails[0].text
    assert "notifications/unsubscribe?token=" in mails[0].text


def test_inbox_counts_for_the_shared_test_user():
    client = TestClient(app)
    _notify(TEST_USER_ID, f"shared-{uuid.uuid4().hex}", kind="first_candidate")
    inbox = client.get("/api/notifications")
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["unread"] >= 1

    async def count():
        async with SessionLocal() as session:
            return (
                await session.execute(
                    select(func.count()).select_from(Notification).where(
                        Notification.user_id == TEST_USER_ID,
                        Notification.in_inbox.is_(True),
                        Notification.read_at.is_(None),
                    )
                )
            ).scalar()

    assert inbox.json()["unread"] == _run(count())


@pytest.mark.real_auth
def test_logout_removes_this_devices_subscription():
    client = TestClient(app)
    email = f"logout-{uuid.uuid4().hex[:8]}@example.edu"
    session_body = client.post(
        "/api/auth/register",
        json={"accept_terms": True, "email": email, "password": "correct-horse-99"},
    ).json()
    headers = {"Authorization": f"Bearer {session_body['tokens']['access_token']}"}
    endpoint = f"https://push.example.com/{uuid.uuid4().hex}"
    other = f"https://push.example.com/{uuid.uuid4().hex}"
    for e in (endpoint, other):
        resp = client.post(
            "/api/notifications/push/subscriptions",
            json={"endpoint": e, "keys": {"p256dh": "k", "auth": "a"}},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
    out = client.post(
        "/api/auth/logout",
        json={"refresh_token": session_body["tokens"]["refresh_token"], "push_endpoint": endpoint},
    )
    assert out.status_code == 200, out.text

    async def endpoints():
        async with SessionLocal() as session:
            return set(
                (
                    await session.execute(
                        select(PushSubscription.endpoint).where(
                            PushSubscription.user_id == session_body["user"]["id"]
                        )
                    )
                ).scalars()
            )

    assert _run(endpoints()) == {other}


def test_migration_parses_unambiguous_existing_deadlines():
    from alembic import command
    from tests.test_migrations import _cfg, _fetch, _scratch_db

    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "040_cv_markdown")
        _run(
            _fetch(
                url,
                "INSERT INTO users (id, email, password_hash, plan, prefer_own_model) "
                "VALUES ('u1', 'u1@example.com', 'x', 'free', false)",
            )
        )
        _run(
            _fetch(
                url,
                "INSERT INTO applications (id, school, program, degree_type, location, link, "
                "requirements, offer, deadline, status, professors, notes, fee_waiver, "
                "fee_waiver_notes, source, user_id) VALUES "
                "('a1', 'S', '', 'phd', '', '', '[]', '', '15 December 2026', 'wishlist', "
                "'[]', '', false, '', 'manual', 'u1'), "
                "('a2', 'S', 'P', 'phd', '', '', '[]', '', 'rolling', 'wishlist', "
                "'[]', '', false, '', 'manual', 'u1'), "
                "('a3', 'S', 'Q', 'phd', '', '', '[]', '', '03/04/2026', 'wishlist', "
                "'[]', '', false, '', 'manual', 'u1')",
            )
        )
        command.upgrade(cfg, "041_notifications")
        rows = _run(_fetch(url, "SELECT id, deadline_date FROM applications ORDER BY id"))
        assert {r["id"]: r["deadline_date"] for r in rows} == {
            "a1": date(2026, 12, 15),
            "a2": None,
            "a3": None,
        }


def test_delete_notification_is_scoped_idempotent_and_preserves_delivery(monkeypatch):
    from api.auth import schemas as auth_schemas
    from api.auth.routes import get_current_user

    alice, bob = _new_user(), _new_user()
    _notify(alice, "dismiss-once")
    _notify(bob, "other-account")
    own = _rows(alice)[0]
    other = _rows(bob)[0]
    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        lambda: auth_schemas.UserOut(
            id=alice, email=f"{alice}@example.com", created_at=_at(2026, 1, 1)
        ),
    )
    client = TestClient(app)
    assert client.delete(f"/api/notifications/{other.id}").json() == {"removed": 0}
    assert client.delete(f"/api/notifications/{own.id}").json() == {"removed": 1}
    assert client.delete(f"/api/notifications/{own.id}").json() == {"removed": 0}
    assert client.delete("/api/notifications/does-not-exist").json() == {"removed": 0}
    inbox = client.get("/api/notifications").json()
    assert inbox["items"] == []
    assert inbox["unread"] == 0
    assert _notify(alice, "dismiss-once") is False
    stored = _rows(alice)[0]
    assert stored.in_inbox is False
    assert stored.delivered_at is None
    assert stored.delivery is None
    assert _rows(bob)[0].in_inbox is True


def test_clear_notifications_includes_older_read_and_unread_entries(monkeypatch):
    from api.auth import schemas as auth_schemas
    from api.auth.routes import get_current_user

    alice, bob = _new_user(), _new_user()
    for index in range(32):
        _notify(alice, f"bulk:{index}", kind="first_candidate")
    _notify(bob, "keep")
    first = _rows(alice)[0]
    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        lambda: auth_schemas.UserOut(
            id=alice, email=f"{alice}@example.com", created_at=_at(2026, 1, 1)
        ),
    )
    client = TestClient(app)
    assert client.post(f"/api/notifications/{first.id}/read").json() == {"marked": 1}
    before = client.get("/api/notifications").json()
    assert len(before["items"]) == 30
    assert before["unread"] == 31
    response = client.delete("/api/notifications")
    assert response.status_code == 200
    assert response.json() == {"removed": 32}
    assert client.delete("/api/notifications").json() == {"removed": 0}
    after = client.get("/api/notifications").json()
    assert after["items"] == []
    assert after["unread"] == 0
    assert len(_rows(alice)) == 32
    assert all(not row.in_inbox for row in _rows(alice))
    assert _rows(bob)[0].in_inbox is True
    assert _notify(alice, "bulk:0", kind="first_candidate") is False

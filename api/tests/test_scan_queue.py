"""Queue guarantees: leases, fencing, the reaper, retries, cancellation and conclusion."""

import asyncio
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.main import app
from api.scans import queue
from api.scans.models import Scan, ScanTask, TaskStatus, WorkerHeartbeat
from tests.conftest import TEST_USER_ID


def _scan(tasks: int = 0, **task_fields) -> tuple[str, list[str]]:
    async def go():
        async with SessionLocal() as session:
            scan = Scan(user_id=TEST_USER_ID, region="Ghana", categories=["startup"], status="running")
            session.add(scan)
            await session.flush()
            ids = []
            for _ in range(tasks):
                task = ScanTask(
                    scan_id=scan.id, user_id=TEST_USER_ID, task_type="discover_opportunities", **task_fields
                )
                session.add(task)
                await session.flush()
                ids.append(task.id)
            await session.commit()
            return scan.id, ids

    return asyncio.run(go())


def _get(model, row_id):
    async def go():
        async with SessionLocal() as session:
            return await session.get(model, row_id)

    return asyncio.run(go())


def _beat(worker_id: str, age: timedelta = timedelta(0)) -> None:
    async def go():
        async with SessionLocal() as session:
            seen = utcnow_naive() - age
            row = await session.get(WorkerHeartbeat, worker_id)
            if row is None:
                session.add(WorkerHeartbeat(worker_id=worker_id, started_at=seen, last_seen_at=seen))
            else:
                row.last_seen_at = seen
            await session.commit()

    asyncio.run(go())


def _process(scan_id: str) -> bool:
    async def go():
        async with SessionLocal() as session:
            task = await queue.claim_next_task(session, scan_id)
            if task is None:
                return False
            token = queue.current_lease.set((task.id, task.attempt))
            try:
                await queue.process_claimed(session, task)
            finally:
                queue.current_lease.reset(token)
            await queue._release_lease(task.id, task.attempt)
            return True

    return asyncio.run(go())


async def _ok(session, task, scan, on_event=None, resume_messages=None, on_checkpoint=None):
    await on_event({"turn": 1, "kind": "turn", "note": "looking"})
    return {"final_text": "Saved: None", "turns": 1}


def test_live_attempt_is_not_reaped_dead_one_is():
    old = utcnow_naive() - timedelta(hours=2)
    _, (live,) = _scan(1, status=TaskStatus.running, claimed_by="live-w", updated_at=old)
    _, (dead,) = _scan(1, status=TaskStatus.running, claimed_by="dead-w", updated_at=old)
    _beat("live-w")
    _beat("dead-w", age=timedelta(hours=1))

    async def reap():
        async with SessionLocal() as session:
            return await queue.reap_stale_tasks(session)

    asyncio.run(reap())
    assert _get(ScanTask, live).status == TaskStatus.running
    assert _get(ScanTask, dead).status == TaskStatus.pending
    assert _get(ScanTask, dead).claimed_by is None


def test_pending_task_held_by_a_live_worker_is_not_claimed():
    _beat("other-w")
    scan_id, _ = _scan(1, status=TaskStatus.pending, claimed_by="other-w")

    async def claim():
        async with SessionLocal() as session:
            return await queue.claim_next_task(session, scan_id)

    assert asyncio.run(claim()) is None


def test_superseded_attempt_cannot_write():
    scan_id, (task_id,) = _scan(1)

    async def go():
        async with SessionLocal() as stale, SessionLocal() as fresh:
            mine = await queue.claim_next_task(stale, scan_id)
            assert mine is not None
            theirs = await fresh.get(ScanTask, task_id)
            theirs.attempt += 1  # a newer attempt took over
            await fresh.commit()
            mine.final_text = "late write"
            try:
                await stale.commit()
            except StaleDataError:
                return True
            return False

    assert asyncio.run(go()) is True


def test_done_tasks_conclude_the_scan_with_a_trace(monkeypatch):
    monkeypatch.setitem(queue.TASK_HANDLERS, "discover_opportunities", _ok)
    scan_id, _ = _scan(2)
    assert _process(scan_id) and _get(Scan, scan_id).status == "running"
    assert _process(scan_id) and _get(Scan, scan_id).status == "done"
    detail = TestClient(app).get(f"/api/scans/{scan_id}").json()
    assert [t["status"] for t in detail["tasks"]] == ["done", "done"]
    assert detail["tasks"][0]["log"][0]["note"] == "looking"


def test_transient_failure_requeues_then_errors(monkeypatch):
    monkeypatch.setattr(queue.settings, "max_task_attempts", 2)

    async def flaky(session, task, scan, **_):
        raise TimeoutError("slow model")

    monkeypatch.setitem(queue.TASK_HANDLERS, "discover_opportunities", flaky)
    scan_id, (task_id,) = _scan(1)
    _process(scan_id)
    assert _get(ScanTask, task_id).status == TaskStatus.pending
    _process(scan_id)
    assert _get(ScanTask, task_id).status == TaskStatus.error
    assert _get(Scan, scan_id).status == "done"


def test_cancel_stops_pending_work_and_halts_running_agents():
    from api.agent.tools import ToolContext
    from api.agent.tools.dispatch import run_halted

    scan_id, _ = _scan(2)
    cancelled = TestClient(app).post(f"/api/scans/{scan_id}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert {t["status"] for t in cancelled["tasks"]} == {"cancelled"}

    async def halted():
        async with SessionLocal() as session:
            scan = await session.get(Scan, scan_id)
            return await run_halted(ToolContext(session=session, run=scan))

    assert asyncio.run(halted()) == "cancelled"
    assert _process(scan_id) is False


def test_start_list_and_delete_scans():
    client = TestClient(app)
    started = client.post("/api/scans", json={"categories": ["student", "startup"], "focus": "agritech"})
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["region"] == "Ghana" and body["categories"] == ["startup", "student"]
    assert sorted(t["target"] for t in body["tasks"]) == ["category:startup", "category:student"]
    assert body["id"] in [s["id"] for s in client.get("/api/scans").json()]
    assert client.delete(f"/api/scans/{body['id']}").status_code == 200
    assert client.get(f"/api/scans/{body['id']}").status_code == 404

    async def leftovers():
        async with SessionLocal() as session:
            return (await session.execute(select(ScanTask).where(ScanTask.scan_id == body["id"]))).all()

    assert asyncio.run(leftovers()) == []

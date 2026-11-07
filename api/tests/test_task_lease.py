import asyncio
import functools
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm.exc import StaleDataError

from api.core.db import SessionLocal
from api.main import app
from api.runs import queue
from api.runs.models import ResearchTask, Run, TaskStatus, WorkerHeartbeat
from tests.conftest import TEST_USER_ID


def _run_id() -> str:
    with TestClient(app) as client:
        resp = client.post(
            "/api/runs/from-list",
            json={
                "degree_level": "phd",
                "interest_statement": "lease robots",
                "programs": [{"school_name": "Lease U", "program_name": "PhD Leases"}],
            },
        )
        assert resp.status_code == 200, resp.text
        run_id = resp.json()["id"]

    async def isolate():
        # Only our own task in this run: drop whatever from-list queued.
        async with SessionLocal() as session:
            await session.execute(
                text("DELETE FROM research_tasks WHERE run_id = :r"), {"r": run_id}
            )
            run = await session.get(Run, run_id)
            assert run is not None
            run.status = "running"
            await session.commit()

    asyncio.run(isolate())
    return run_id


def _add_task(run_id, **kwargs) -> str:
    async def go():
        async with SessionLocal() as session:
            task = ResearchTask(
                user_id=TEST_USER_ID,
                run_id=run_id,
                task_type="discover_programs",
                **kwargs,
            )
            session.add(task)
            await session.commit()
            return task.id

    return asyncio.run(go())


def _beat(worker_id: str, age: timedelta = timedelta(0)):
    async def go():
        async with SessionLocal() as session:
            row = await session.get(WorkerHeartbeat, worker_id)
            seen = queue.utcnow_naive() - age
            if row is None:
                session.add(
                    WorkerHeartbeat(
                        worker_id=worker_id,
                        concurrency=1,
                        started_at=seen,
                        last_seen_at=seen,
                    )
                )
            else:
                row.last_seen_at = seen
            await session.commit()

    asyncio.run(go())


def _get(task_id) -> ResearchTask:
    async def go():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            assert task is not None
            return task

    return asyncio.run(go())


def test_live_attempt_is_not_reaped_dead_one_is():
    run_id = _run_id()
    old = queue.utcnow_naive() - timedelta(hours=2)
    live = _add_task(
        run_id, status=TaskStatus.running, claimed_by="live-w", updated_at=old
    )
    dead = _add_task(
        run_id, status=TaskStatus.running, claimed_by="dead-w", updated_at=old
    )
    _beat("live-w")
    _beat("dead-w", age=timedelta(hours=1))

    async def reap():
        async with SessionLocal() as session:
            return await queue.reap_stale_tasks(session)

    asyncio.run(reap())
    assert _get(live).status == TaskStatus.running
    assert _get(dead).status == TaskStatus.pending
    assert _get(dead).claimed_by is None


def test_fresh_task_is_not_reaped_off_utc():
    """updated_at uses the same UTC clock as the cutoff, whatever the session TimeZone."""
    run_id = _run_id()

    async def go():
        async with SessionLocal() as session:
            await session.execute(text("SET TIME ZONE 'America/New_York'"))
            task = ResearchTask(
                user_id=TEST_USER_ID,
                run_id=run_id,
                task_type="discover_programs",
                status=TaskStatus.running,
            )
            session.add(task)
            await session.commit()
            await queue.reap_stale_tasks(session, stale_after_minutes=15)
            await session.refresh(task)
            return task.status

    assert asyncio.run(go()) == TaskStatus.running


def test_resume_during_live_attempt_does_not_start_second_handler():
    run_id = _run_id()
    task_id = _add_task(run_id)
    _beat(queue.WORKER_ID)

    async def claim():
        async with SessionLocal() as session:
            return await queue._claim_next_task(session, run_id)

    first = asyncio.run(claim())
    assert first is not None and first.attempt == 1
    assert first.claimed_by == queue.WORKER_ID
    with TestClient(app) as client:
        assert client.post(f"/api/tasks/{task_id}/pause").status_code == 200
        assert client.post(f"/api/tasks/{task_id}/resume").status_code == 200
    # Pending again, but the first attempt still holds the lease.
    assert asyncio.run(claim()) is None
    asyncio.run(queue._release_lease(task_id, 1))
    second = asyncio.run(claim())
    assert second is not None and second.attempt == 2


def test_superseded_attempt_cannot_write_or_run_tools():
    run_id = _run_id()
    task_id = _add_task(run_id, status=TaskStatus.running, attempt=1, claimed_by="w1")

    async def go():
        async with SessionLocal() as old_session, SessionLocal() as new_session:
            stale = await old_session.get(ResearchTask, task_id)
            assert stale is not None
            fresh = await new_session.get(ResearchTask, task_id)
            assert fresh is not None
            fresh.attempt = 2  # a newer claim
            await new_session.commit()

            token = queue.current_lease.set((task_id, 1))
            try:
                halt = await queue.current_lease_halt(old_session)
            finally:
                queue.current_lease.reset(token)
            stale.log = "[]"
            with pytest.raises(StaleDataError):
                await old_session.commit()
            return halt

    assert asyncio.run(go()) == "superseded"


def test_paused_task_tools_are_refused():
    from api.agent.tools import ToolContext, dispatch_batch

    run_id = _run_id()
    task_id = _add_task(run_id, status=TaskStatus.paused, attempt=1)

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            token = queue.current_lease.set((task_id, 1))
            try:
                return await dispatch_batch(
                    [("search_web", {"query": "x"})],
                    ToolContext(session=session, run=run),
                    "discover_programs",
                )
            finally:
                queue.current_lease.reset(token)

    [result] = asyncio.run(go())
    assert "This task was paused" in result["error"]


def test_reaper_during_slow_turn_gives_one_invocation(monkeypatch):
    """A slow attempt, the reaper firing past the stale window, and a second loop looking for work."""
    run_id = _run_id()
    _add_task(run_id)
    _beat(queue.WORKER_ID)
    monkeypatch.setattr(
        queue,
        "_claim_next_task",
        functools.partial(queue._claim_next_task, run_id=run_id),
    )
    calls = {"n": 0, "max": 0, "live": 0}

    async def slow_handler(session, task, run, **kwargs):
        calls["n"] += 1
        calls["live"] += 1
        calls["max"] = max(calls["max"], calls["live"])
        await asyncio.sleep(0.5)
        calls["live"] -= 1
        return {"turns": 1, "final_text": "ok", "usage": {}}

    monkeypatch.setitem(queue.TASK_HANDLERS, "discover_programs", slow_handler)

    async def scenario():
        first = asyncio.create_task(queue.process_one())
        await asyncio.sleep(0.1)
        async with SessionLocal() as session:
            await queue.reap_stale_tasks(session, stale_after_minutes=0)
        second = await queue.process_one()
        await first
        return second

    assert asyncio.run(scenario()) is False
    assert calls == {"n": 1, "max": 1, "live": 0}

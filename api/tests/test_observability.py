import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from api.core.db import SessionLocal
from api.main import app
from api.runs import queue
from api.runs.models import ResearchTask, Run, TaskStatus, ToolCallLog, WorkerHeartbeat
from tests.conftest import TEST_USER_ID


def _client():
    return TestClient(app)


def _seed_run():
    async def setup():
        async with SessionLocal() as session:
            run = Run(user_id=TEST_USER_ID, 
                region="U",
                field="f",
                degree_level="phd",
                interest_statement="x",
                status="running",
            )
            session.add(run)
            await session.commit()
            return run.id

    return asyncio.run(setup())


def _beat(worker_id="w-alive", age_seconds=0, concurrency=5):
    async def setup():
        async with SessionLocal() as session:
            await queue.heartbeat(session, worker_id, concurrency)
            if age_seconds:
                row = await session.get(WorkerHeartbeat, worker_id)
                assert row is not None
                row.last_seen_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(
                    seconds=age_seconds
                )
                await session.commit()

    asyncio.run(setup())


def test_heartbeat_insert_update_and_prune():
    async def roundtrip():
        async with SessionLocal() as session:
            await queue.heartbeat(session, "w-1", 3)
            row = await session.get(WorkerHeartbeat, "w-1")
            assert row is not None
            assert row.concurrency == 3
            first_seen = row.last_seen_at
            await queue.heartbeat(session, "w-1", 7)
            row = await session.get(WorkerHeartbeat, "w-1")
            assert row is not None
            assert row.concurrency == 7
            assert row.last_seen_at >= first_seen
            assert row.started_at is not None
            pruned = await queue.prune_heartbeats(
                session, older_than=timedelta(days=-1)
            )
            assert pruned >= 1
            assert await session.get(WorkerHeartbeat, "w-1") is None

    asyncio.run(roundtrip())


def test_workers_endpoint_marks_stale():
    _beat("w-alive")
    _beat("w-stale", age_seconds=3600)
    workers = {w["worker_id"]: w for w in _client().get("/api/workers").json()}
    assert workers["w-alive"]["alive"] is True
    assert workers["w-alive"]["concurrency"] == 5
    assert workers["w-alive"]["lag_seconds"] >= 0
    assert workers["w-stale"]["alive"] is False

    body = _client().get("/health").json()
    assert body["workers"]["alive"] >= 1
    assert body["workers"]["stale"] >= 1


def test_run_usage_accounting():
    run_id = _seed_run()

    async def setup():
        async with SessionLocal() as session:
            task = ResearchTask(user_id=TEST_USER_ID, 
                run_id=run_id,
                task_type="discover_programs",
                status=TaskStatus.done,
                turns=3,
                input_tokens=100,
                output_tokens=50,
            )
            session.add(task)
            await session.flush()
            session.add(
                ToolCallLog(user_id=TEST_USER_ID, 
                    task_id=task.id,
                    turn=1,
                    tool_name="search_web",
                    input_json="{}",
                    result_json="{}",
                    ok=True,
                )
            )
            session.add(
                ToolCallLog(user_id=TEST_USER_ID, 
                    task_id=task.id,
                    turn=2,
                    tool_name="fetch_page",
                    input_json="{}",
                    result_json="{}",
                    ok=False,
                )
            )
            await session.commit()

    asyncio.run(setup())

    client = _client()
    body = client.get(f"/api/runs/{run_id}/usage").json()
    assert body["input_tokens"] == 100
    assert body["output_tokens"] == 50
    assert body["turns"] == 3
    assert body["tasks"]["done"] == 1
    assert body["tools"]["search_web"] == {"calls": 1, "errors": 0}
    assert body["tools"]["fetch_page"] == {"calls": 1, "errors": 1}
    assert client.get("/api/runs/does-not-exist/usage").status_code == 404

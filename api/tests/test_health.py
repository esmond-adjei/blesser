import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from api.core.db import SessionLocal
from api.main import app
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID


def _client():
    return TestClient(app)


def test_health_reports_database_and_queue():
    import tomllib
    from pathlib import Path

    import api

    client = _client()
    body = client.get("/health").json()
    assert body["version"] == api.__version__
    assert tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"] == api.__version__
    assert {"llm_provider", "embedding_provider"} <= set(body)
    assert {"pending", "running", "done", "error", "stale_running", "last_activity_at"} <= set(body["queue"])
    database = body["database"]
    assert database["reachable"] is True
    assert database["dialect"] == "postgresql"
    assert database["latency_ms"] >= 0
    for key in ("runs", "tasks", "candidates", "drafts"):
        assert isinstance(database[key], int)
    assert isinstance(body["search_configured"], bool)
    assert isinstance(body["typesafe_enabled"], bool)
    assert client.get("/ready").json() == {"ready": True}


def _seed_error_and_stale(run_id):
    async def setup():
        async with SessionLocal() as session:
            session.add(
                ResearchTask(user_id=TEST_USER_ID, 
                    run_id=run_id,
                    task_type="discover_programs",
                    status=TaskStatus.error,
                    error="boom",
                )
            )
            session.add(
                ResearchTask(user_id=TEST_USER_ID, 
                    run_id=run_id,
                    task_type="research_professor",
                    status=TaskStatus.running,
                    updated_at=datetime.now(UTC).replace(tzinfo=None)
                    - timedelta(hours=1),
                )
            )
            await session.commit()

    return asyncio.run(setup())


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


def test_health_degraded_on_failure_and_stale():
    _seed_error_and_stale(_seed_run())
    body = _client().get("/health").json()
    assert body["status"] == "degraded"
    assert body["queue"]["error"] >= 1
    assert body["queue"]["stale_running"] >= 1
    assert body["queue"]["last_activity_at"] is not None


def test_queue_reports_a_windowed_error_count():
    """`error` is a lifetime count; asserted as a relationship since the shared DB holds other modules' failures."""
    _seed_error_and_stale(_seed_run())
    queue = _client().get("/health").json()["queue"]
    assert isinstance(queue["recent_error"], int)
    assert queue["error_window_minutes"] > 0
    assert queue["recent_error"] <= queue["error"]


def test_no_live_worker_with_queued_work_is_degraded():
    from sqlalchemy import delete

    from api.runs import queue
    from api.runs.models import WorkerHeartbeat

    run_id = _seed_run()

    async def setup():
        async with SessionLocal() as session:
            await session.execute(delete(WorkerHeartbeat))
            session.add(
                ResearchTask(
                    user_id=TEST_USER_ID,
                    run_id=run_id,
                    task_type="discover_programs",
                    status=TaskStatus.pending,
                )
            )
            await session.commit()

    asyncio.run(setup())
    body = _client().get("/health").json()
    assert body["no_workers"] is True
    assert body["status"] == "degraded"

    async def beat():
        async with SessionLocal() as session:
            await queue.heartbeat(session, "health-test-worker", 1)

    asyncio.run(beat())
    assert _client().get("/health").json()["no_workers"] is False

    asyncio.run(queue.retire_heartbeat("health-test-worker"))
    assert _client().get("/health").json()["no_workers"] is True


def test_queue_eta_follows_the_recent_finishing_pace():
    import uuid

    from api.auth.models import User
    from api.runs.health import _queue_eta

    user_id = f"eta-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).replace(tzinfo=None)

    async def run():
        async with SessionLocal() as session:
            session.add(User(id=user_id, email=f"{user_id}@example.com", password_hash="x"))
            await session.flush()
            assert await _queue_eta(session, user_id, 4, 2) is None
            run = Run(user_id=user_id, region="U", field="f", degree_level="phd", interest_statement="x", status="running")
            session.add(run)
            await session.flush()
            for i in range(6):
                session.add(
                    ResearchTask(
                        user_id=user_id,
                        run_id=run.id,
                        task_type="research_professor",
                        status=TaskStatus.done,
                        started_at=now - timedelta(minutes=10),
                        finished_at=now - timedelta(minutes=i),
                    )
                )
            await session.flush()
            assert 390 <= await _queue_eta(session, user_id, 4, 2) <= 410
            assert await _queue_eta(session, user_id, 0, 0) is None
            await session.rollback()

    asyncio.run(run())

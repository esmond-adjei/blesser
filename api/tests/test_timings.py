import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update

from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.main import app
from api.runs.models import ResearchTask, Run
from tests.conftest import TEST_USER_ID


def _client():
    return TestClient(app)


def _seed_run(client):
    resp = client.post(
        "/api/runs",
        json={
            "region": "United States",
            "field": "robotics",
            "degree_level": "phd",
            "interest_statement": "robots",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_task_duration_computed_from_timestamps():
    client = _client()
    run_id = _seed_run(client)
    base = utcnow_naive().replace(microsecond=0) - timedelta(hours=1)

    async def setup():
        async with SessionLocal() as session:
            task = ResearchTask(user_id=TEST_USER_ID, 
                run_id=run_id,
                task_type="discover_programs",
                created_at=base,
                updated_at=base + timedelta(seconds=90),
            )
            session.add(task)
            await session.commit()
            return task.id

    task_id = asyncio.run(setup())

    body = client.get(f"/api/tasks/{task_id}").json()
    assert abs(body["duration_seconds"] - 90) < 2

    items = {t["id"]: t for t in client.get(f"/api/runs/{run_id}/tasks").json()}
    assert abs(items[task_id]["duration_seconds"] - 90) < 2


def test_fresh_task_duration_near_zero():
    client = _client()
    run_id = _seed_run(client)
    item = client.get(f"/api/runs/{run_id}/tasks").json()[0]
    assert 0 <= item["duration_seconds"] < 30
    body = client.get(f"/api/tasks/{item['id']}").json()
    assert 0 <= body["duration_seconds"] < 30


def test_run_elapsed_computed_from_created_at():
    client = _client()
    run_id = _seed_run(client)
    backdated = utcnow_naive().replace(microsecond=0) - timedelta(seconds=300)

    async def setup():
        async with SessionLocal() as session:
            await session.execute(
                update(Run).where(Run.id == run_id).values(created_at=backdated)
            )
            await session.commit()

    asyncio.run(setup())

    detail = client.get(f"/api/runs/{run_id}").json()
    assert 270 <= detail["elapsed_seconds"] <= 330
    index = {r["id"]: r for r in client.get("/api/runs").json()}
    assert 270 <= index[run_id]["elapsed_seconds"] <= 330


def test_finished_run_elapsed_stops_at_its_last_task():
    client = _client()
    run_id = _seed_run(client)
    created = utcnow_naive().replace(microsecond=0) - timedelta(days=3)

    async def setup(status: str):
        async with SessionLocal() as session:
            await session.execute(
                update(Run).where(Run.id == run_id).values(created_at=created, status=status)
            )
            await session.execute(
                update(ResearchTask)
                .where(ResearchTask.run_id == run_id)
                .values(status="done", started_at=created, finished_at=created + timedelta(minutes=90))
            )
            await session.commit()

    asyncio.run(setup("done"))
    done = client.get(f"/api/runs/{run_id}").json()
    assert done["finished_at"] is not None
    assert done["elapsed_seconds"] == 90 * 60

    asyncio.run(setup("running"))
    live = client.get(f"/api/runs/{run_id}").json()
    assert live["finished_at"] is None
    assert live["elapsed_seconds"] >= 3 * 86400


def test_run_detail_reports_its_latest_task_activity():
    client = _client()
    run_id = _seed_run(client)
    created = utcnow_naive().replace(microsecond=0) - timedelta(days=3)
    touched = created + timedelta(hours=5)

    async def setup():
        async with SessionLocal() as session:
            await session.execute(update(Run).where(Run.id == run_id).values(created_at=created))
            await session.execute(
                update(ResearchTask).where(ResearchTask.run_id == run_id).values(updated_at=touched)
            )
            await session.commit()

    asyncio.run(setup())
    detail = client.get(f"/api/runs/{run_id}").json()
    assert datetime.fromisoformat(detail["updated_at"]) == touched


def test_run_time_counts_working_spans_not_idle_gaps():
    from types import SimpleNamespace

    from api.runs.service import active_seconds

    t0 = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)

    def task(start_min, end_min, status="done"):
        return SimpleNamespace(
            status=status,
            started_at=t0 + timedelta(minutes=start_min),
            finished_at=t0 + timedelta(minutes=end_min) if end_min is not None else None,
            updated_at=None,
        )

    week = 7 * 24 * 60
    never_started = SimpleNamespace(status="pending", started_at=None, finished_at=None, updated_at=None)
    tasks = [task(0, 30), task(10, 60), task(week, week + 5), never_started]
    assert active_seconds(tasks, t0) == (60 + 5) * 60
    live = [task(0, 10), task(20, None, status="running")]
    assert active_seconds(live, t0 + timedelta(minutes=50)) == (10 + 30) * 60

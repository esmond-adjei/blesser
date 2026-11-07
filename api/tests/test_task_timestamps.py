import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.main import app
from api.runs import models as run_models
from api.runs import queue as run_queue
from api.runs.models import ResearchTask, Run, TaskStatus

_STUBBED_TYPES = (
    "discover_programs",
    "research_professor",
    "research_one_professor",
    "draft_email",
)


def _client():
    return TestClient(app)


def _seed_run(client):
    resp = client.post(
        "/api/runs/from-list",
        json={
            "degree_level": "phd",
            "interest_statement": "timing robots",
            "programs": [
                {
                    "school_name": "Timing University",
                    "program_name": "PhD in Timing Robotics",
                },
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _tasks(client, run_id):
    return client.get(f"/api/runs/{run_id}/tasks").json()


def _task(client, task_id):
    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


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
        task.started_at = utcnow_naive()
        await session.commit()
        return task

    return fake_claim


async def _ok_handler(
    session, task, run, on_event=None, resume_messages=None, on_checkpoint=None
):
    return {"turns": 1, "final_text": "stubbed finish", "usage": {}}


def _process(monkeypatch, run_id, handler=_ok_handler):
    for task_type in _STUBBED_TYPES:
        monkeypatch.setitem(run_queue.TASK_HANDLERS, task_type, handler)
    monkeypatch.setattr(run_queue, "_claim_next_task", _fake_claim_for(run_id))
    return asyncio.run(run_queue.process_one())


def test_real_claim_stamps_start():
    """Seeds a run so the claim always finds a row, and restores whatever was claimed."""

    _seed_run(_client())

    async def claim_and_restore():
        async with SessionLocal() as session:
            task = await run_queue._claim_next_task(session)
            if task is None:
                return None
            seen = (run_models.status_str(task.status), task.started_at)
            task.status = TaskStatus.pending
            task.started_at = None
            await session.commit()
            return seen

    seen = asyncio.run(claim_and_restore())
    if seen is None:
        pytest.skip("no claimable tasks globally")
    status, started_at = seen
    assert status == TaskStatus.running.value
    assert started_at is not None


def test_claim_and_conclude_stamp_window(monkeypatch):
    client = _client()
    run_id = _seed_run(client)
    (seeded,) = _tasks(client, run_id)

    assert seeded["started_at"] is None
    assert seeded["finished_at"] is None

    assert _process(monkeypatch, run_id) is True
    task = _task(client, seeded["id"])
    assert task["status"] == "done"
    assert task["started_at"] is not None
    assert task["finished_at"] is not None
    assert datetime.fromisoformat(task["started_at"]) <= datetime.fromisoformat(
        task["finished_at"]
    )


def test_duration_ignores_queue_time(monkeypatch):
    client = _client()
    run_id = _seed_run(client)
    (seeded,) = _tasks(client, run_id)

    async def age_queue_time():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, seeded["id"])
            assert task is not None
            task.created_at = datetime.now() - timedelta(days=2)  # noqa: DTZ005 - repo convention is naive UTC
            await session.commit()

    asyncio.run(age_queue_time())

    assert _process(monkeypatch, run_id) is True
    task = _task(client, seeded["id"])
    execution = (
        datetime.fromisoformat(task["finished_at"])
        - datetime.fromisoformat(task["started_at"])
    ).total_seconds()
    assert execution < 3600
    assert (task["duration_seconds"] or 0) > 2 * 24 * 3600


def test_rerun_clears_window_and_cancel_finishes_it(monkeypatch):
    client = _client()
    run_id = _seed_run(client)
    (seeded,) = _tasks(client, run_id)
    assert _process(monkeypatch, run_id) is True

    assert client.post(f"/api/tasks/{seeded['id']}/rerun").status_code == 200
    task = _task(client, seeded["id"])
    assert task["started_at"] is None
    assert task["finished_at"] is None

    assert client.post(f"/api/tasks/{seeded['id']}/cancel").status_code == 200
    task = _task(client, seeded["id"])
    assert task["status"] == "cancelled"
    assert task["finished_at"] is not None

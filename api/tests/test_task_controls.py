import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from api.core.db import SessionLocal
from api.main import app
from api.runs import queue as run_queue
from api.runs.models import ResearchTask, Run, TaskStatus, ToolCallLog
from tests.conftest import TEST_USER_ID

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
            "interest_statement": "control robots",
            "programs": [
                {
                    "school_name": "Control University",
                    "program_name": "PhD in Control Robotics",
                },
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _add_task(run_id, **kwargs):
    async def setup():
        async with SessionLocal() as session:
            task = ResearchTask(user_id=TEST_USER_ID, run_id=run_id, **kwargs)
            session.add(task)
            await session.commit()
            return task.id

    return asyncio.run(setup())


def _task(client, task_id):
    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _tasks(client, run_id):
    return client.get(f"/api/runs/{run_id}/tasks").json()


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
        await session.commit()
        return task

    return fake_claim


def _process(monkeypatch, run_id, handler):
    for task_type in _STUBBED_TYPES:
        monkeypatch.setitem(run_queue.TASK_HANDLERS, task_type, handler)
    monkeypatch.setattr(run_queue, "_claim_next_task", _fake_claim_for(run_id))
    return asyncio.run(run_queue.process_one())


async def _ok_handler(
    session, task, run, on_event=None, resume_messages=None, on_checkpoint=None
):
    return {"turns": 1, "final_text": "stubbed finish", "usage": {}}


def test_pause_resume_cycle():
    client = _client()
    run_id = _seed_run(client)
    (seeded,) = _tasks(client, run_id)
    task_id = seeded["id"]

    assert client.post(f"/api/tasks/{task_id}/pause").json() == {"status": "paused"}
    assert _task(client, task_id)["status"] == "paused"

    paused = client.get(f"/api/runs/{run_id}/tasks", params={"status": "paused"}).json()
    assert [t["id"] for t in paused] == [task_id]
    board = client.get(f"/api/runs/{run_id}/board").json()
    assert [c["id"] for c in board["paused"]] == [task_id]
    assert client.get(f"/api/runs/{run_id}").json()["tasks"]["paused"] == 1

    assert client.post(f"/api/tasks/{task_id}/pause").status_code == 400
    assert client.post(f"/api/tasks/{task_id}/rerun").status_code == 400

    assert client.post(f"/api/tasks/{task_id}/resume").json() == {"status": "pending"}
    assert _task(client, task_id)["status"] == "pending"
    assert client.post(f"/api/tasks/{task_id}/resume").status_code == 400


def test_cancel_concludes_run_and_is_terminal():
    client = _client()
    run_id = _seed_run(client)
    (seeded,) = _tasks(client, run_id)

    assert client.post(f"/api/tasks/{seeded['id']}/cancel").json() == {
        "status": "cancelled"
    }
    assert _task(client, seeded["id"])["status"] == "cancelled"
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "done"

    assert client.post(f"/api/tasks/{seeded['id']}/cancel").status_code == 400
    assert client.post(f"/api/tasks/{seeded['id']}/pause").status_code == 400

    assert client.post(f"/api/tasks/{seeded['id']}/rerun").json() == {
        "status": "pending"
    }
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "running"


def test_rerun_restarts_finished_tasks_fresh():
    client = _client()
    run_id = _seed_run(client)
    task_id = _add_task(
        run_id,
        task_type="research_professor",
        status=TaskStatus.done,
        turns=4,
        final_text="old summary",
        log='[{"turn": 1, "tool": "search_web"}]',
        messages_json='[{"role": "user", "content": "go"}]',
        input_tokens=100,
        output_tokens=50,
    )

    async def add_log():
        async with SessionLocal() as session:
            session.add(
                ToolCallLog(user_id=TEST_USER_ID, 
                    task_id=task_id,
                    turn=1,
                    tool_name="search_web",
                    input_json="{}",
                    result_json="{}",
                    ok=True,
                )
            )
            await session.commit()

    asyncio.run(add_log())

    assert client.post(f"/api/tasks/{task_id}/rerun").json() == {"status": "pending"}
    task = _task(client, task_id)
    assert task["status"] == "pending"
    assert task["error"] is None
    assert task["log"] is None
    assert task["final_text"] is None
    assert task["turns"] is None
    assert task["input_tokens"] is None
    assert task["output_tokens"] is None

    async def check_cleared():
        async with SessionLocal() as session:
            row = await session.get(ResearchTask, task_id)
            assert row is not None
            checkpoint = row.messages_json
            logs = (
                await session.execute(
                    select(ToolCallLog).where(ToolCallLog.task_id == task_id)
                )
            ).scalars().all()
            return checkpoint, logs

    checkpoint, logs = asyncio.run(check_cleared())
    assert checkpoint is None
    assert logs == []


def test_rerun_rejects_open_tasks():
    client = _client()
    run_id = _seed_run(client)
    (seeded,) = _tasks(client, run_id)
    assert client.post(f"/api/tasks/{seeded['id']}/rerun").status_code == 400
    assert client.post(f"/api/tasks/{seeded['id']}/cancel").status_code == 200
    paused_id = _add_task(run_id, task_type="discover_programs")
    assert client.post(f"/api/tasks/{paused_id}/pause").status_code == 200
    assert client.post(f"/api/tasks/{paused_id}/rerun").status_code == 400


def test_delete_refuses_running_tasks():
    client = _client()
    run_id = _seed_run(client)
    (seeded,) = _tasks(client, run_id)

    async def mark_running():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, seeded["id"])
            assert task is not None
            task.status = TaskStatus.running
            await session.commit()

    asyncio.run(mark_running())
    resp = client.delete(f"/api/tasks/{seeded['id']}")
    assert resp.status_code == 400

    assert client.post(f"/api/tasks/{seeded['id']}/cancel").status_code == 200
    assert client.delete(f"/api/tasks/{seeded['id']}").json() == {"status": "deleted"}
    assert client.get(f"/api/tasks/{seeded['id']}").status_code == 404


def test_conclude_honors_mid_run_cancel(monkeypatch):
    async def self_cancel(session, task, run, on_event=None, **kwargs):
        async with SessionLocal() as other:
            other_task = await other.get(ResearchTask, task.id)
            assert other_task is not None
            other_task.status = TaskStatus.cancelled
            await other.commit()
        return {"turns": 1, "final_text": "must be discarded", "usage": {}}

    client = _client()
    run_id = _seed_run(client)
    assert _process(monkeypatch, run_id, self_cancel) is True

    (task,) = _tasks(client, run_id)
    assert task["status"] == "cancelled"
    assert task["final_text"] is None
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "done"


def test_pause_mid_run_keeps_checkpoint_for_resume(monkeypatch):
    async def self_pause(session, task, run, on_event=None, on_checkpoint=None, **kwargs):
        await on_checkpoint([{"role": "user", "content": "halfway"}])
        async with SessionLocal() as other:
            other_task = await other.get(ResearchTask, task.id)
            assert other_task is not None
            other_task.status = TaskStatus.paused
            await other.commit()
        return {"turns": 9, "final_text": "must be discarded", "usage": {}}

    client = _client()
    run_id = _seed_run(client)
    (seeded,) = _tasks(client, run_id)
    assert _process(monkeypatch, run_id, self_pause) is True

    task = _task(client, seeded["id"])
    assert task["status"] == "paused"
    assert task["turns"] is None

    assert client.post(f"/api/tasks/{seeded['id']}/resume").status_code == 200
    assert _process(monkeypatch, run_id, _ok_handler) is True
    task = _task(client, seeded["id"])
    assert task["status"] == "done"
    assert task["final_text"] == "stubbed finish"

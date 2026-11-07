import asyncio

import pytest
from fastapi.testclient import TestClient

from api.agent.orchestrator import TaskHalted, _halt_reason
from api.agent.tools import ToolContext
from api.core.db import SessionLocal
from api.main import app
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.test_agent_controls import NARROW, SUPERVISOR, _control, _run, _statuses
from tests.test_task_controls import _ok_handler, _process, _seed_run, _task, _tasks


def _turn_boundary(before=None):
    """Stands in for the orchestrator: checkpoint one turn, let `before` act from another session, then run the halt check."""

    async def handler(session, task, run, on_event=None, on_checkpoint=None, **kwargs):
        await on_checkpoint([{"role": "user", "content": "halfway"}])
        if before is not None:
            await before(task)
        halted = await _halt_reason(ToolContext(session=session, run=run), task.task_type)
        if halted:
            raise TaskHalted(halted)
        return {"turns": 9, "final_text": "must be discarded", "usage": {}}

    return handler


def test_pausing_the_run_stops_its_running_task_and_resume_carries_it_on(monkeypatch):
    client = TestClient(app)
    run_id = _seed_run(client)
    (seeded,) = _tasks(client, run_id)

    async def pause_run(task):
        assert client.post(f"/api/runs/{run_id}/pause").status_code == 200

    assert _process(monkeypatch, run_id, _turn_boundary(pause_run)) is True
    task = _task(client, seeded["id"])
    assert task["status"] == "pending"
    assert task["final_text"] is None

    assert client.post(f"/api/runs/{run_id}/resume").status_code == 200
    assert _process(monkeypatch, run_id, _ok_handler) is True
    assert _task(client, seeded["id"])["status"] == "done"


def test_a_run_paused_without_touching_rows_still_requeues_its_task(monkeypatch):
    """The allowance gate flips only the run: the halt alone requeues."""
    client = TestClient(app)
    run_id = _seed_run(client)
    (seeded,) = _tasks(client, run_id)

    async def flip_run(task):
        async with SessionLocal() as other:
            run = await other.get(Run, run_id)
            assert run is not None
            run.status = "paused"
            await other.commit()

    assert _process(monkeypatch, run_id, _turn_boundary(flip_run)) is True
    task = _task(client, seeded["id"])
    assert task["status"] == "pending" and task["final_text"] is None


@pytest.mark.parametrize(
    ("action", "expected"),
    [("pause", TaskStatus.paused), ("cancel", TaskStatus.cancelled)],
)
def test_controlling_an_agent_marks_its_running_tasks(action, expected):
    run_id, (running, other) = _run([(NARROW, TaskStatus.running), (SUPERVISOR, TaskStatus.running)])
    resp = _control(run_id, NARROW, action)
    assert resp.status_code == 200, resp.text
    assert resp.json()["affected"] == 1
    statuses, _ = _statuses(run_id)
    assert statuses[running][0] == expected
    assert statuses[other][0] == TaskStatus.running


def test_the_halt_check_reads_the_agents_state():
    run_id, _ = _run([(NARROW, TaskStatus.running)])
    _control(run_id, NARROW, "pause")

    async def check():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            ctx = ToolContext(session=session, run=run)
            return await _halt_reason(ctx, NARROW), await _halt_reason(ctx, SUPERVISOR)

    assert asyncio.run(check()) == ("agent paused", None)


def test_an_agent_cancelled_mid_turn_ends_its_task(monkeypatch):
    client = TestClient(app)
    run_id = _seed_run(client)
    (seeded,) = _tasks(client, run_id)

    async def cancel_agent(task):
        # State only, as if the row update raced the claim.
        async with SessionLocal() as other:
            run = await other.get(Run, run_id)
            assert run is not None
            run.agent_states = f'{{"{task.task_type}": "cancelled"}}'
            await other.commit()

    assert _process(monkeypatch, run_id, _turn_boundary(cancel_agent)) is True

    async def read():
        async with SessionLocal() as session:
            row = await session.get(ResearchTask, seeded["id"])
            assert row is not None
            return row.status, row.final_text

    assert asyncio.run(read()) == (TaskStatus.cancelled, None)

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from api.core.db import SessionLocal
from api.main import app
from api.prospects import leads
from api.runs import agents, queue
from api.runs.lifecycle import note_tasks_drained, note_work_enqueued
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID

NARROW = "research_one_professor"
SUPERVISOR = "research_professor"


def _run(tasks):
    """A running run with tasks [(task_type, status)]; returns (run_id, ids)."""

    async def setup():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID, region="U", field="f", degree_level="phd",
                interest_statement="robots", status="running",
            )  # fmt: skip
            session.add(run)
            await session.flush()
            ids = []
            for task_type, status in tasks:
                t = ResearchTask(user_id=TEST_USER_ID, run_id=run.id, task_type=task_type, status=status, target_name="x")
                session.add(t)
                await session.flush()
                ids.append(t.id)
            await session.commit()
            return run.id, ids

    return asyncio.run(setup())


def _control(run_id, task_type, action):
    return TestClient(app).post(f"/api/runs/{run_id}/agents/{task_type}/{action}")


def _statuses(run_id):
    async def read():
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ResearchTask.id, ResearchTask.status, ResearchTask.error).where(ResearchTask.run_id == run_id)
                )
            ).all()
            run = await session.get(Run, run_id)
            return {r.id: (r.status, r.error) for r in rows}, run.status

    return asyncio.run(read())


def _claim(run_id):
    async def go():
        async with SessionLocal() as session:
            task = await queue._claim_next_task(session, run_id)
            return task.task_type if task else None

    return asyncio.run(go())


def _enqueue(run_id, task_type):
    async def go():
        async with SessionLocal() as session:
            t = ResearchTask(user_id=TEST_USER_ID, run_id=run_id, task_type=task_type, target_name="new")
            session.add(t)
            await note_work_enqueued(session, run_id)
            await session.commit()
            return t.id

    return asyncio.run(go())


def test_pausing_one_agent_leaves_the_others_working():
    run_id, (narrow, supervisor) = _run([(NARROW, TaskStatus.pending), (SUPERVISOR, TaskStatus.pending)])
    resp = _control(run_id, NARROW, "pause")
    assert resp.status_code == 200, resp.text
    assert resp.json()["affected"] == 1 and resp.json()["agent_states"] == {NARROW: "paused"}
    statuses, _ = _statuses(run_id)
    assert statuses[narrow][0] == TaskStatus.paused and statuses[supervisor][0] == TaskStatus.pending
    # A Faculty Agent's new names don't refill the paused queue.
    new = _enqueue(run_id, NARROW)
    statuses, _ = _statuses(run_id)
    assert statuses[new][0] == TaskStatus.paused
    assert _claim(run_id) == SUPERVISOR
    assert _claim(run_id) is None
    body = TestClient(app).get(f"/api/runs/{run_id}").json()
    assert body["agent_states"] == {NARROW: "paused"}


def test_a_paused_agent_keeps_the_run_open_and_resumes():
    run_id, (narrow, _) = _run([(NARROW, TaskStatus.pending), (SUPERVISOR, TaskStatus.done)])
    _control(run_id, NARROW, "pause")

    async def drain():
        async with SessionLocal() as session:
            await note_tasks_drained(session, run_id)
            await session.commit()

    asyncio.run(drain())
    _, run_status = _statuses(run_id)
    assert run_status == "running"  # its work isn't finished, only waiting
    resp = _control(run_id, NARROW, "resume")
    assert resp.json()["affected"] == 1 and resp.json()["agent_states"] == {}
    statuses, _ = _statuses(run_id)
    assert statuses[narrow][0] == TaskStatus.pending
    assert _claim(run_id) == NARROW


def test_the_claim_never_picks_a_held_agents_task():
    run_id, _ = _run([(NARROW, TaskStatus.pending)])

    async def hold_directly():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            run.agent_states = '{"research_one_professor": "paused"}'
            await session.commit()

    asyncio.run(hold_directly())
    assert _claim(run_id) is None


def test_leads_wait_while_the_professor_agents_are_paused():
    run_id, (lead,) = _run([(NARROW, TaskStatus.deferred)])
    _control(run_id, NARROW, "pause")

    async def release():
        async with SessionLocal() as session:
            n = await leads.release_deferred_leads(session, run_id)
            await session.commit()
            return n

    assert asyncio.run(release()) == 0
    statuses, _ = _statuses(run_id)
    assert statuses[lead][0] == TaskStatus.deferred


def test_cancelling_an_agent_stops_it_for_the_rest_of_the_run():
    run_id, (pending, paused, deferred, done, _) = _run(
        [
            (NARROW, TaskStatus.pending),
            (NARROW, TaskStatus.paused),
            (NARROW, TaskStatus.deferred),
            (NARROW, TaskStatus.done),
            (SUPERVISOR, TaskStatus.done),
        ]
    )
    resp = _control(run_id, NARROW, "cancel")
    assert resp.json()["affected"] == 3
    statuses, run_status = _statuses(run_id)
    for tid in (pending, paused, deferred):
        assert statuses[tid] == (TaskStatus.cancelled, agents.CANCELLED_NOTE)
    assert statuses[done][0] == TaskStatus.done
    assert run_status == "done"
    # New work for it is cancelled as it lands; it can't be paused.
    new = _enqueue(run_id, NARROW)
    statuses, _ = _statuses(run_id)
    assert statuses[new][0] == TaskStatus.cancelled
    assert _control(run_id, NARROW, "pause").status_code == 400


def test_resuming_a_cancelled_agent_brings_its_work_back():
    run_id, (pending, deferred, done) = _run(
        [(NARROW, TaskStatus.pending), (NARROW, TaskStatus.deferred), (NARROW, TaskStatus.done)]
    )
    _control(run_id, NARROW, "cancel")
    resp = _control(run_id, NARROW, "resume")
    assert resp.json()["affected"] == 2
    statuses, run_status = _statuses(run_id)
    assert run_status == "running"
    assert statuses[pending] == statuses[deferred] == (TaskStatus.pending, None)
    assert statuses[done][0] == TaskStatus.done


def test_a_supervisor_is_told_when_the_professor_agents_were_cancelled():
    from api.agent.tools import ToolContext, dispatch
    from api.prospects.models import Program
    from tests.test_budgets import _make_program, _make_run

    run_id = _make_run()
    _, program_id = _make_program(run_id)
    _control(run_id, NARROW, "cancel")

    async def spawn():
        async with SessionLocal() as session:
            ctx = ToolContext(
                session=session, run=await session.get(Run, run_id), program=await session.get(Program, program_id)
            )
            return await dispatch("spawn_professor_research", {"names": ["Ada Walker"]}, ctx)

    out = asyncio.run(spawn())
    assert "Professor Agents were cancelled" in out["error"]


def test_unknown_agents_and_actions_are_refused():
    run_id, _ = _run([])
    assert _control(run_id, "make_coffee", "pause").status_code == 400
    assert _control(run_id, NARROW, "explode").status_code == 400
    assert TestClient(app).post(f"/api/runs/nope/agents/{NARROW}/pause").status_code == 404

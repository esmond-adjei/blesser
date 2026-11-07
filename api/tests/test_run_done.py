"""Worker tests fake `_claim_next_task` per run: the suite shares one database, so real claims would pick up other files' tasks."""

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from api.candidates.models import CandidateScore, CandidateStatus
from api.core.db import SessionLocal
from api.main import app
from api.prospects.models import Professor, Program, RunSchool, School
from api.runs import queue as run_queue
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID

_STUBBED_TYPES = (
    "discover_programs",
    "research_professor",
    "research_one_professor",
    "draft_email",
)


def _client():
    return TestClient(app)


def _seed_run(client, **kwargs):
    body = {
        "degree_level": "phd",
        "interest_statement": "robots",
        "programs": [{"school_name": "Done University", "program_name": "PhD in Done"}],
    }
    body.update(kwargs)
    resp = client.post("/api/runs/from-list", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _ok_handler(
    session, task, run, on_event=None, resume_messages=None, on_checkpoint=None
):
    return {"turns": 1, "final_text": "stubbed finish", "usage": {}}


async def _boom_handler(
    session, task, run, on_event=None, resume_messages=None, on_checkpoint=None
):
    raise RuntimeError("stubbed failure")


def _fake_claim_for(run_id):
    """Claim this run's oldest pending task; like the real claim, only `running` runs qualify."""

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


def _process(monkeypatch, run_id, handler=_ok_handler):
    for task_type in _STUBBED_TYPES:
        monkeypatch.setitem(run_queue.TASK_HANDLERS, task_type, handler)
    monkeypatch.setattr(run_queue, "_claim_next_task", _fake_claim_for(run_id))
    return asyncio.run(run_queue.process_one())


def _mark_done(run_id):
    async def setup():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            run.status = "done"
            await session.commit()

    asyncio.run(setup())


def _add_task(run_id, status=TaskStatus.pending):
    async def setup():
        async with SessionLocal() as session:
            session.add(
                ResearchTask(user_id=TEST_USER_ID, 
                    run_id=run_id, task_type="research_professor", status=status
                )
            )
            await session.commit()

    asyncio.run(setup())


def _add_candidate(run_id, name, score, status=CandidateStatus.scored):
    async def setup():
        async with SessionLocal() as session:
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run_id)], name=f"{name} University")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name=f"PhD in {name}")
            session.add(program)
            await session.flush()
            professor = Professor(user_id=TEST_USER_ID, program_id=program.id, name=f"Prof {name}")
            session.add(professor)
            await session.flush()
            candidate = CandidateScore(user_id=TEST_USER_ID, 
                run_id=run_id,
                professor_id=professor.id,
                similarity_score=score,
                rationale=f"{name} aligns.",
                status=status,
            )
            session.add(candidate)
            await session.flush()
            await session.commit()
            return candidate.id

    return asyncio.run(setup())


def _run_status(client, run_id):
    return client.get(f"/api/runs/{run_id}").json()["status"]


def test_last_task_concludes_run(monkeypatch):
    client = _client()
    run_id = _seed_run(client)
    assert _run_status(client, run_id) == "running"

    assert _process(monkeypatch, run_id) is True
    assert _run_status(client, run_id) == "done"

    assert _process(monkeypatch, run_id) is False

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["status"] == "done"
    assert detail["tasks"]["done"] == 1


def test_open_tasks_keep_run_running(monkeypatch):
    client = _client()
    run_id = _seed_run(client)
    _add_task(run_id)

    assert _process(monkeypatch, run_id) is True
    assert _run_status(client, run_id) == "running"

    assert _process(monkeypatch, run_id) is True
    assert _run_status(client, run_id) == "done"


def test_failed_last_task_also_concludes(monkeypatch):
    client = _client()
    run_id = _seed_run(client)

    assert _process(monkeypatch, run_id, handler=_boom_handler) is True
    assert _run_status(client, run_id) == "done"
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["status"] == "done"
    assert detail["tasks"]["error"] == 1


def test_cancelled_run_never_auto_concludes(monkeypatch):
    client = _client()
    run_id = _seed_run(client)
    assert client.post(f"/api/runs/{run_id}/cancel").json() == {"status": "cancelled"}

    async def claimable():
        async with SessionLocal() as session:
            return (
                (
                    await session.execute(
                        select(ResearchTask)
                        .join(Run, ResearchTask.run_id == Run.id)
                        .where(
                            ResearchTask.run_id == run_id,
                            ResearchTask.status == TaskStatus.pending,
                            Run.status == "running",
                        )
                    )
                )
                .scalars()
                .all()
            )

    assert asyncio.run(claimable()) == []
    assert _process(monkeypatch, run_id) is False
    assert _run_status(client, run_id) == "cancelled"


def test_retry_failed_reopens_done_run():
    client = _client()
    run_id = _seed_run(client)
    _add_task(run_id, TaskStatus.error)
    _mark_done(run_id)

    resp = client.post(f"/api/runs/{run_id}/retry-failed")
    assert resp.json() == {"retried": 1}
    assert _run_status(client, run_id) == "running"


def test_single_retry_reopens_done_run():
    client = _client()
    run_id = _seed_run(client)

    async def failing_id():
        async with SessionLocal() as session:
            task = (
                (
                    await session.execute(
                        select(ResearchTask).where(ResearchTask.run_id == run_id)
                    )
                )
                .scalars()
                .first()
            )
            assert task is not None
            task.status = TaskStatus.error
            await session.commit()
            return task.id

    task_id = asyncio.run(failing_id())
    _mark_done(run_id)

    assert client.post(f"/api/tasks/{task_id}/retry").json() == {"status": "pending"}
    assert _run_status(client, run_id) == "running"


def test_request_draft_reopens_done_run():
    client = _client()
    run_id = _seed_run(client)
    candidate_id = _add_candidate(run_id, "Draft", 0.8)
    _mark_done(run_id)

    assert client.post(f"/api/candidates/{candidate_id}/request-draft").json() == {
        "status": "queued"
    }
    assert _run_status(client, run_id) == "running"


def test_bulk_request_drafts_reopens_done_run():
    client = _client()
    run_id = _seed_run(client)
    first = _add_candidate(run_id, "BulkA", 0.8)
    second = _add_candidate(run_id, "BulkB", 0.7)
    _mark_done(run_id)

    body = client.post(
        f"/api/runs/{run_id}/request-drafts",
        json={"candidate_ids": [first, second]},
    ).json()
    assert sorted(body["queued"]) == sorted([first, second])
    assert _run_status(client, run_id) == "running"


def test_bulk_request_drafts_all_skipped_stays_done():
    client = _client()
    run_id = _seed_run(client)
    _mark_done(run_id)

    body = client.post(
        f"/api/runs/{run_id}/request-drafts",
        json={"candidate_ids": ["does-not-exist"]},
    ).json()
    assert body["queued"] == []
    assert _run_status(client, run_id) == "done"


def test_manual_program_and_professor_reopen_done_run():
    client = _client()
    run_id = _seed_run(client)
    tree = client.get(f"/api/runs/{run_id}/programs").json()
    school_id = tree[0]["id"]
    program_id = tree[0]["programs"][0]["id"]
    _mark_done(run_id)

    created = client.post(
        f"/api/schools/{school_id}/programs", json={"name": "PhD in Reopen"}
    )
    assert created.status_code == 200, created.text
    assert _run_status(client, run_id) == "running"

    _mark_done(run_id)
    created = client.post(
        f"/api/programs/{program_id}/professors", json={"name": "Prof Reopen"}
    )
    assert created.status_code == 200, created.text
    assert _run_status(client, run_id) == "running"


def test_manual_school_with_programs_reopens_done_run():
    client = _client()
    run_id = _seed_run(client)
    _mark_done(run_id)

    created = client.post(
        f"/api/runs/{run_id}/schools",
        json={"name": "Reopen University", "programs": [{"name": "PhD in Reopen"}]},
    )
    assert created.status_code == 200, created.text
    assert len(created.json()["programs"]) == 1
    assert _run_status(client, run_id) == "running"


def test_manual_bare_school_keeps_done_run():
    client = _client()
    run_id = _seed_run(client)
    _mark_done(run_id)

    created = client.post(
        f"/api/runs/{run_id}/schools", json={"name": "Bare University"}
    )
    assert created.status_code == 200, created.text
    assert _run_status(client, run_id) == "done"


def test_agent_chained_tasks_reopen_done_run(monkeypatch):
    from api.agent.tools import ToolContext
    from api.agent.tools import dispatch as agent_dispatch

    client = _client()
    run_id = _seed_run(client)

    async def run_tool(tool_name, tool_input):
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = (
                (
                    await session.execute(
                        select(Program).where(
                            Program.school_id.in_(
                                select(RunSchool.school_id).where(RunSchool.run_id == run_id)
                            )
                        )
                    )
                )
                .scalars()
                .first()
            )
            ctx = ToolContext(session=session, run=run, program=program)
            result = await agent_dispatch(tool_name, tool_input, ctx)
            await session.commit()
            return result

    async def count_open():
        async with SessionLocal() as session:
            return (
                (
                    await session.execute(
                        select(ResearchTask).where(
                            ResearchTask.run_id == run_id,
                            ResearchTask.status.in_(
                                [TaskStatus.pending, TaskStatus.running]
                            ),
                        )
                    )
                )
                .scalars()
                .all()
            )

    _mark_done(run_id)
    saved = asyncio.run(
        run_tool("save_program", {"school_name": "Chain U", "program_name": "PhD"})
    )
    assert "error" not in saved, saved
    assert _run_status(client, run_id) == "running"

    _mark_done(run_id)
    spawned = asyncio.run(run_tool("spawn_professor_research", {"names": ["Prof Z"]}))
    assert spawned.get("queued") == 1, spawned
    assert _run_status(client, run_id) == "running"
    assert len(asyncio.run(count_open())) >= 2

import asyncio
import contextlib
import os
from urllib.parse import urlsplit, urlunsplit

import asyncpg
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.core.db import SessionLocal
from api.main import app
from api.runs import queue as run_queue
from api.runs.models import ResearchTask, Run, TaskStatus
from api.runs.notify import CHANNEL, parse_payload
from tests.conftest import TEST_USER_ID

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://graduator:graduator@localhost:5432/graduator_test",
)

_STUBBED_TYPES = (
    "discover_programs",
    "research_professor",
    "research_one_professor",
    "draft_email",
)


def _client():
    return TestClient(app)


def _dsn():
    parts = urlsplit(TEST_DATABASE_URL)
    return urlunsplit(("postgresql", parts.netloc, parts.path, "", ""))


@contextlib.asynccontextmanager
async def _listen():
    conn = await asyncpg.connect(_dsn())
    received: asyncio.Queue = asyncio.Queue()

    def _cb(*_a):
        received.put_nowait(_a[3])

    await conn.add_listener(CHANNEL, _cb)
    try:
        yield received
    finally:
        try:
            await conn.remove_listener(CHANNEL, _cb)
        except Exception:  # noqa: BLE001, S110 - teardown only
            pass
        await conn.close()


async def _next_for(received, run_id, timeout=5.0):
    """Next payload for this run (skips other runs' traffic)."""
    while True:
        payload = await asyncio.wait_for(received.get(), timeout=timeout)
        parsed = parse_payload(payload)
        if parsed is not None and parsed[0] == run_id:
            return parsed[1]


def _seed_run(client):
    resp = client.post(
        "/api/runs/from-list",
        json={
            "degree_level": "phd",
            "interest_statement": "notify robots",
            "programs": [
                {
                    "school_name": "Notify University",
                    "program_name": "PhD in Notify Robotics",
                },
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


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


def test_parse_payload():
    assert parse_payload("run-1:tasks") == ("run-1", "tasks")
    assert parse_payload("run-1:candidates") == ("run-1", "candidates")
    assert parse_payload("run-1:drafts") == ("run-1", "drafts")
    assert parse_payload("run-1:bogus") is None
    assert parse_payload("no-separator") is None
    assert parse_payload("") is None
    assert parse_payload(None) is None
    assert parse_payload(123) is None


def test_worker_turn_notifies_tasks(monkeypatch):
    async def run():
        async with _listen() as received:
            run_id = _seed_run(_client())

            async def stub(session, task, run, on_event, **kwargs):
                await on_event(
                    {
                        "turn": 1,
                        "tool": "search_web",
                        "input": {"query": "x"},
                        "result": {"results": []},
                        "result_preview": "{}",
                        "ok": True,
                        "note": "",
                    }
                )
                return {"turns": 1, "final_text": "done", "usage": {}}

            for task_type in _STUBBED_TYPES:
                monkeypatch.setitem(run_queue.TASK_HANDLERS, task_type, stub)
            monkeypatch.setattr(
                run_queue, "_claim_next_task", _fake_claim_for(run_id)
            )
            assert await run_queue.process_one() is True
            section = await _next_for(received, run_id)
            assert section == "tasks"

    asyncio.run(run())


def test_pause_notifies_tasks():
    async def run():
        async with _listen() as received:
            client = _client()
            run_id = _seed_run(client)
            task_id = client.get(f"/api/runs/{run_id}/tasks").json()[0]["id"]
            assert client.post(f"/api/tasks/{task_id}/pause").status_code == 200
            assert await _next_for(received, run_id) == "tasks"

    asyncio.run(run())


def test_review_notifies_candidates():
    async def seed_candidate(run_id):
        from api.candidates.models import CandidateScore, CandidateStatus
        from api.prospects.models import Professor, Program, RunSchool, School

        async with SessionLocal() as session:
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run_id)], name="Review University")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="PhD in Review")
            session.add(program)
            await session.flush()
            professor = Professor(user_id=TEST_USER_ID, program_id=program.id, name="Prof Review")
            session.add(professor)
            await session.flush()
            candidate = CandidateScore(user_id=TEST_USER_ID, 
                run_id=run_id,
                professor_id=professor.id,
                similarity_score=0.9,
                rationale="Review aligns.",
                status=CandidateStatus.scored,
            )
            session.add(candidate)
            await session.flush()
            await session.commit()
            return candidate.id

    async def run():
        async with _listen() as received:
            client = _client()
            run_id = _seed_run(client)
            candidate_id = await seed_candidate(run_id)
            resp = client.post(
                f"/api/candidates/{candidate_id}/review", json={"approved": True}
            )
            assert resp.status_code == 200, resp.text
            kind = await _next_for(received, run_id)
            while kind in ("tasks", "work"):  # the seed's own wake-ups
                kind = await _next_for(received, run_id)
            assert kind == "candidates"

    asyncio.run(run())

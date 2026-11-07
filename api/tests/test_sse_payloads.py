import asyncio
import json

from fastapi.testclient import TestClient

from api.candidates.models import CandidateScore, CandidateStatus
from api.core.db import SessionLocal
from api.main import app
from api.prospects.models import Paper, Professor, Program, RunSchool, School
from api.runs import service as run_service
from tests.conftest import TEST_USER_ID


def _client():
    return TestClient(app)


def _seed_run(client):
    resp = client.post(
        "/api/runs/from-list",
        json={
            "degree_level": "phd",
            "interest_statement": "robots",
            "programs": [
                {"school_name": "SSE University", "program_name": "PhD in SSE"}
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _seed_candidate(run_id, status=CandidateStatus.scored):
    async def setup():
        async with SessionLocal() as session:
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run_id)], name="SSE School")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="PhD in SSE")
            session.add(program)
            await session.flush()
            professor = Professor(user_id=TEST_USER_ID, program_id=program.id, name="Prof SSE")
            session.add(professor)
            await session.flush()
            session.add(Paper(user_id=TEST_USER_ID, professor_id=professor.id, title="SSE paper"))
            session.add(
                CandidateScore(user_id=TEST_USER_ID, 
                    run_id=run_id,
                    professor_id=professor.id,
                    similarity_score=0.9,
                    rationale="SSE aligns.",
                    status=status,
                )
            )
            await session.commit()

    asyncio.run(setup())


def _collect_until_ping(run_id):
    async def drive():
        gen = run_service.run_events(run_id, TEST_USER_ID, poll_interval=0.01)
        try:
            frames = []
            for _ in range(20):
                frame = await gen.__anext__()
                frames.append(frame)
                if frame.startswith(": ping"):
                    break
            return frames
        finally:
            await gen.aclose()

    return asyncio.run(drive())


def test_open_task_emits_value_status_and_no_done():
    run_id = _seed_run(_client())
    frames = _collect_until_ping(run_id)

    assert frames, "expected at least one SSE frame"
    assert not any(f.startswith("event: done") for f in frames), frames
    assert frames[-1].startswith(": ping"), frames

    task_frames = [f for f in frames if f.startswith("event: task")]
    assert task_frames, frames
    statuses = set()
    for frame in task_frames:
        assert "TaskStatus." not in frame, frame
        _, _, data = frame.partition("data: ")
        statuses.add(json.loads(data)["status"])
    assert "pending" in statuses, task_frames


def test_candidate_emits_value_status():
    run_id = _seed_run(_client())
    _seed_candidate(run_id)
    frames = _collect_until_ping(run_id)

    candidate_frames = [f for f in frames if f.startswith("event: candidate")]
    assert candidate_frames, frames
    for frame in candidate_frames:
        assert "CandidateStatus." not in frame, frame
        _, _, data = frame.partition("data: ")
        assert json.loads(data)["status"] == CandidateStatus.scored.value

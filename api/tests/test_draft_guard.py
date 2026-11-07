import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api.candidates.models import CandidateScore, CandidateStatus
from api.core.db import SessionLocal
from api.main import app
from api.prospects.models import Paper, Professor, Program, RunSchool, School
from api.runs.models import ResearchTask, TaskStatus
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
                {"school_name": "Draft University", "program_name": "PhD in Drafts"}
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _graph(run_id, candidate_status=CandidateStatus.scored):
    async def setup():
        async with SessionLocal() as session:
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run_id)], name="G University")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="PhD in G")
            session.add(program)
            await session.flush()
            professor = Professor(user_id=TEST_USER_ID, program_id=program.id, name="Prof G")
            session.add(professor)
            await session.flush()
            session.add(Paper(user_id=TEST_USER_ID, professor_id=professor.id, title="G paper"))
            candidate = CandidateScore(user_id=TEST_USER_ID, 
                run_id=run_id,
                professor_id=professor.id,
                similarity_score=0.8,
                rationale="G aligns.",
                status=candidate_status,
            )
            session.add(candidate)
            await session.flush()
            await session.commit()
            return {"candidate_id": candidate.id}

    return asyncio.run(setup())


def _draft_tasks(candidate_id):
    async def fetch():
        async with SessionLocal() as session:
            return (
                (
                    await session.execute(
                        select(ResearchTask).where(
                            ResearchTask.task_type == "draft_email",
                            ResearchTask.target_id == candidate_id,
                        )
                    )
                )
                .scalars()
                .all()
            )

    return asyncio.run(fetch())


def _set_task_status(task_id, status):
    async def update():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            assert task is not None
            task.status = status
            await session.commit()

    asyncio.run(update())


def _count_draft_tasks():
    async def count():
        async with SessionLocal() as session:
            return (
                await session.execute(
                    select(func.count())
                    .select_from(ResearchTask)
                    .where(ResearchTask.task_type == "draft_email")
                )
            ).scalar() or 0

    return asyncio.run(count())


def test_single_request_draft_double_fire_returns_409():
    client = _client()
    run_id = _seed_run(client)
    candidate_id = _graph(run_id)["candidate_id"]
    assert run_id is not None

    first = client.post(f"/api/candidates/{candidate_id}/request-draft")
    assert first.status_code == 200, first.text
    assert first.json() == {"status": "queued"}

    tasks = _draft_tasks(candidate_id)
    assert len(tasks) == 1
    inflight_id = tasks[0].id

    second = client.post(f"/api/candidates/{candidate_id}/request-draft")
    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert detail["task_id"] == inflight_id
    assert detail["message"]

    assert len(_draft_tasks(candidate_id)) == 1


def test_single_request_draft_running_also_conflicts_done_and_error_allow_retry():
    client = _client()
    run_id = _seed_run(client)
    candidate_id = _graph(run_id)["candidate_id"]
    assert run_id is not None

    assert (
        client.post(f"/api/candidates/{candidate_id}/request-draft").status_code == 200
    )
    (task,) = _draft_tasks(candidate_id)

    _set_task_status(task.id, TaskStatus.running)
    conflict = client.post(f"/api/candidates/{candidate_id}/request-draft")
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["task_id"] == task.id

    _set_task_status(task.id, TaskStatus.error)
    retry = client.post(f"/api/candidates/{candidate_id}/request-draft")
    assert retry.status_code == 200, retry.text
    assert len(_draft_tasks(candidate_id)) == 2

    for row in _draft_tasks(candidate_id):
        _set_task_status(row.id, TaskStatus.done)
    again = client.post(f"/api/candidates/{candidate_id}/request-draft")
    assert again.status_code == 200, again.text
    assert len(_draft_tasks(candidate_id)) == 3


def test_single_request_draft_is_candidate_scoped():
    client = _client()
    run_id = _seed_run(client)
    first = _graph(run_id)["candidate_id"]
    second = _graph(run_id)["candidate_id"]

    assert client.post(f"/api/candidates/{first}/request-draft").status_code == 200
    other = client.post(f"/api/candidates/{second}/request-draft")
    assert other.status_code == 200, other.text


def test_bulk_request_drafts_skips_inflight():
    client = _client()
    run_id = _seed_run(client)
    busy = _graph(run_id)["candidate_id"]
    fresh = _graph(run_id)["candidate_id"]

    assert client.post(f"/api/candidates/{busy}/request-draft").status_code == 200
    (busy_task,) = _draft_tasks(busy)
    before = _count_draft_tasks()

    resp = client.post(
        f"/api/runs/{run_id}/request-drafts",
        json={"candidate_ids": [busy, fresh, "does-not-exist"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["queued"] == [fresh]
    by_id = {s["id"]: s for s in body["skipped"]}
    assert by_id["does-not-exist"]["reason"] == "not found in run"
    assert by_id[busy]["reason"] == "draft already in progress"
    assert by_id[busy]["task_id"] == busy_task.id

    assert len(_draft_tasks(busy)) == 1
    assert len(_draft_tasks(fresh)) == 1
    assert _count_draft_tasks() == before + 1

    repeat = client.post(
        f"/api/runs/{run_id}/request-drafts", json={"candidate_ids": [fresh]}
    )
    assert repeat.json() == {
        "queued": [],
        "skipped": [
            {
                "id": fresh,
                "reason": "draft already in progress",
                "task_id": _draft_tasks(fresh)[0].id,
            }
        ],
    }


def test_bulk_request_drafts_reports_duplicates_honestly():
    client = _client()
    run_id = _seed_run(client)
    fresh = _graph(run_id)["candidate_id"]

    resp = client.post(
        f"/api/runs/{run_id}/request-drafts",
        json={"candidate_ids": [fresh, fresh]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["queued"] == [fresh]
    assert body["skipped"] == [
        {"id": fresh, "reason": "duplicate in request", "task_id": None}
    ]
    assert len(_draft_tasks(fresh)) == 1


def test_candidate_detail_exposes_draft_task_status():
    client = _client()
    run_id = _seed_run(client)
    candidate_id = _graph(run_id)["candidate_id"]
    assert run_id is not None

    detail = client.get(f"/api/candidates/{candidate_id}").json()
    assert detail["draft_task_id"] is None
    assert detail["draft_task_status"] is None

    assert (
        client.post(f"/api/candidates/{candidate_id}/request-draft").status_code == 200
    )
    (task,) = _draft_tasks(candidate_id)
    detail = client.get(f"/api/candidates/{candidate_id}").json()
    assert detail["draft_task_id"] == task.id
    assert detail["draft_task_status"] == "pending"

    _set_task_status(task.id, TaskStatus.running)
    detail = client.get(f"/api/candidates/{candidate_id}").json()
    assert detail["draft_task_status"] == "running"

    # Detail exposes in-flight tasks only, so finished drafts report nulls and the button re-enables.
    _set_task_status(task.id, TaskStatus.done)
    detail = client.get(f"/api/candidates/{candidate_id}").json()
    assert detail["draft_task_id"] is None
    assert detail["draft_task_status"] is None

    _set_task_status(task.id, TaskStatus.error)
    detail = client.get(f"/api/candidates/{candidate_id}").json()
    assert detail["draft_task_id"] is None
    assert detail["draft_task_status"] is None

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from api.agent.tools import ToolContext, dispatch
from api.candidates.models import CandidateScore, CandidateStatus
from api.core.db import SessionLocal
from api.main import app
from api.outreach.models import EmailDraft
from api.prospects.models import Paper, Professor, Program, RunSchool, School
from api.runs.models import ResearchTask, Run, TaskStatus, ToolCallLog
from tests.conftest import TEST_USER_ID


def _client():
    return TestClient(app)


def _seed_run(client, **kwargs):
    body = {
        "degree_level": "phd",
        "interest_statement": "robots",
        "programs": [
            {"school_name": "Review University", "program_name": "PhD in Review"}
        ],
    }
    body.update(kwargs)
    resp = client.post("/api/runs/from-list", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _graph(run_id, candidate_status=CandidateStatus.scored, score=0.8):
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
                similarity_score=score,
                rationale="G aligns.",
                status=candidate_status,
            )
            session.add(candidate)
            await session.flush()
            await session.commit()
            return {
                "school_id": school.id,
                "program_id": program.id,
                "professor_id": professor.id,
                "candidate_id": candidate.id,
            }

    return asyncio.run(setup())


def test_run_payloads_carry_detail_and_counts():
    client = _client()
    run_id = _seed_run(client)
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["interest_statement"] == "robots"
    assert detail["created_at"] is not None
    assert detail["tasks"]["pending"] == 1
    assert detail["candidates"] == 0
    index = {r["id"]: r for r in client.get("/api/runs").json()}
    assert index[run_id]["interest_statement"] == "robots"
    assert index[run_id]["created_at"] is not None


def test_cancel_pause_resume_gate_claims_and_saves():
    client = _client()
    run_id = _seed_run(client)

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

    assert client.post(f"/api/runs/{run_id}/cancel").json() == {"status": "cancelled"}
    assert asyncio.run(claimable()) == []

    async def refused():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            ctx = ToolContext(session=session, run=run)
            return await dispatch(
                "save_program", {"school_name": "X", "program_name": "Y"}, ctx
            )

    assert "halted" in asyncio.run(refused())["error"]

    assert client.post(f"/api/runs/{run_id}/pause").json() == {"status": "paused"}
    assert client.post(f"/api/runs/{run_id}/resume").json() == {"status": "running"}
    assert client.post(f"/api/runs/{run_id}/resume").status_code == 400
    assert len(asyncio.run(claimable())) == 1
    assert client.post("/api/runs/does-not-exist/cancel").status_code == 404


def test_patch_run_retunes_budgets_and_interest():
    client = _client()
    run_id = _seed_run(client)
    body = client.patch(
        f"/api/runs/{run_id}",
        json={"max_programs": 4, "interest_statement": "boats"},
    ).json()
    assert body["max_programs"] == 4
    assert body["interest_statement"] == "boats"
    assert (
        client.patch(f"/api/runs/{run_id}", json={"max_programs": 0}).status_code == 422
    )
    assert (
        client.patch("/api/runs/does-not-exist", json={"max_programs": 2}).status_code
        == 404
    )


def test_candidate_payloads_carry_graph_ids():
    client = _client()
    run_id = _seed_run(client)
    ids = _graph(run_id)
    row = client.get(f"/api/runs/{run_id}/candidates").json()[0]
    assert row["professor_id"] == ids["professor_id"]
    assert row["program_id"] == ids["program_id"]
    assert row["school_id"] == ids["school_id"]
    assert row["draft_id"] is None
    detail = client.get(f"/api/candidates/{ids['candidate_id']}").json()
    assert detail["professor_id"] == ids["professor_id"]
    assert detail["draft_id"] is None


def test_candidates_pagination_filter_sort():
    client = _client()
    run_id = _seed_run(client)
    _graph(run_id, CandidateStatus.scored, 0.5)
    _graph(run_id, CandidateStatus.approved, 0.9)
    _graph(run_id, CandidateStatus.rejected, 0.7)

    resp = client.get(f"/api/runs/{run_id}/candidates", params={"limit": 2})
    assert resp.headers["X-Total-Count"] == "3"
    assert [c["similarity_score"] for c in resp.json()] == [0.9, 0.7]

    resp = client.get(
        f"/api/runs/{run_id}/candidates", params={"limit": 2, "offset": 2}
    )
    assert [c["similarity_score"] for c in resp.json()] == [0.5]

    resp = client.get(f"/api/runs/{run_id}/candidates", params={"status": "approved"})
    assert resp.headers["X-Total-Count"] == "1"
    assert resp.json()[0]["status"] == "approved"

    assert (
        client.get(
            f"/api/runs/{run_id}/candidates", params={"status": "bogus"}
        ).status_code
        == 400
    )
    assert (
        client.get(
            f"/api/runs/{run_id}/candidates", params={"sort": "bogus"}
        ).status_code
        == 400
    )


def _seed_tasks(run_id):
    async def setup():
        async with SessionLocal() as session:
            base = datetime.now(UTC).replace(tzinfo=None)
            for i, (offset, status) in enumerate(
                [
                    (120, TaskStatus.done),
                    (60, TaskStatus.error),
                    (30, TaskStatus.pending),
                ]
            ):
                session.add(
                    ResearchTask(user_id=TEST_USER_ID, 
                        run_id=run_id,
                        task_type="discover_programs",
                        status=status,
                        created_at=base - timedelta(minutes=offset),
                    )
                )
            await session.commit()

    asyncio.run(setup())


def test_tasks_pagination_filter_sort():
    client = _client()
    run_id = _seed_run(client)
    _seed_tasks(run_id)

    resp = client.get(f"/api/runs/{run_id}/tasks", params={"limit": 2})
    assert resp.headers["X-Total-Count"] == "4"
    assert len(resp.json()) == 2

    resp = client.get(f"/api/runs/{run_id}/tasks", params={"status": "error"})
    assert resp.headers["X-Total-Count"] == "1"

    recent = client.get(f"/api/runs/{run_id}/tasks", params={"sort": "recent"}).json()
    created = client.get(f"/api/runs/{run_id}/tasks").json()
    assert [t["status"] for t in recent] == ["pending", "pending", "error", "done"]
    assert [t["status"] for t in created] == ["done", "error", "pending", "pending"]

    assert (
        client.get(f"/api/runs/{run_id}/tasks", params={"status": "bogus"}).status_code
        == 400
    )
    assert (
        client.get(f"/api/runs/{run_id}/tasks", params={"sort": "bogus"}).status_code
        == 400
    )


def test_events_feed_streams_to_done():
    client = _client()
    run_id = _seed_run(client)
    ids = _graph(run_id)

    async def finish():
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
            task.status = TaskStatus.done
            task.turns = 2
            session.add(
                EmailDraft(user_id=TEST_USER_ID, candidate_id=ids["candidate_id"], subject="Hi", body="Body")
            )
            await session.commit()

    asyncio.run(finish())
    # `done` doesn't end the feed, so collect frames until the first `done`.
    from api.runs import service as run_service

    async def collect():
        gen = run_service.run_events(run_id, TEST_USER_ID, poll_interval=0.01)
        text = ""
        try:
            async for frame in gen:
                text += frame
                if "event: done" in text:
                    break
        finally:
            await gen.aclose()
        return text

    text = asyncio.run(collect())
    assert "event: task" in text
    assert "event: candidate" in text
    assert "event: draft" in text
    assert "event: done" in text
    token = client.post(
        "/api/auth/register",
        json={"accept_terms": True, "email": "events-probe@example.com", "password": "correct-horse-99"},
    ).json()["tokens"]["access_token"]
    assert (
        client.get(
            "/api/runs/does-not-exist/events",
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 404
    )
    assert client.get("/api/runs/does-not-exist/events").status_code == 401


def test_retry_failed_updates_run_detail():
    client = _client()
    run_id = _seed_run(client)
    _seed_tasks(run_id)
    ids = _graph(run_id)

    # The seeded from-list task is pending; the helper added done/error/pending.
    resp = client.post(f"/api/runs/{run_id}/retry-failed")
    assert resp.json() == {"retried": 1}
    assert client.post("/api/runs/does-not-exist/retry-failed").status_code == 404

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["tasks"]["pending"] == 3
    assert detail["tasks"]["done"] == 1
    assert detail["tasks"]["error"] == 0
    scored = client.get(f"/api/runs/{run_id}/candidates", params={"status": "scored"})
    assert scored.headers["X-Total-Count"] == "1"
    assert client.get(f"/api/runs/{run_id}/drafts").json() == []
    assert ids["candidate_id"] is not None
    assert client.get("/api/runs/does-not-exist").status_code == 404


def test_manual_professor_create_queues_research():
    client = _client()
    run_id = _seed_run(client)
    program_id = client.get(f"/api/runs/{run_id}/programs").json()[0]["programs"][0][
        "id"
    ]

    created = client.post(
        f"/api/programs/{program_id}/professors",
        json={"name": "Prof Manual", "email": "m@example.edu"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["name"] == "Prof Manual"
    assert body["papers"] == []
    assert body["candidate_id"] is None
    assert (
        client.post(
            "/api/programs/does-not-exist/professors", json={"name": "X"}
        ).status_code
        == 404
    )

    tasks = client.get(f"/api/runs/{run_id}/tasks").json()
    assert any(
        t["task_type"] == "research_one_professor" and t["target_name"] == "Prof Manual"
        for t in tasks
    )


def test_draft_outbox_carries_review_context():
    client = _client()
    run_id = _seed_run(client)
    ids = _graph(run_id, CandidateStatus.approved, 0.77)

    async def add_draft():
        async with SessionLocal() as session:
            session.add(
                EmailDraft(user_id=TEST_USER_ID, candidate_id=ids["candidate_id"], subject="S", body="B")
            )
            await session.commit()

    asyncio.run(add_draft())
    (draft,) = client.get(f"/api/runs/{run_id}/drafts").json()
    assert draft["candidate_status"] == "approved"
    assert draft["similarity_score"] == 0.77
    assert draft["rationale"] == "G aligns."
    assert draft["created_at"]


def test_bulk_drafts_and_review():
    client = _client()
    run_id = _seed_run(client)
    first = _graph(run_id)["candidate_id"]
    second = _graph(run_id)["candidate_id"]

    queued = client.post(
        f"/api/runs/{run_id}/request-drafts",
        json={"candidate_ids": [first, second, "does-not-exist"]},
    ).json()
    assert sorted(queued["queued"]) == sorted([first, second])
    assert queued["skipped"] == [{"id": "does-not-exist", "reason": "not found in run"}]
    assert (
        client.post(
            "/api/runs/does-not-exist/request-drafts", json={"candidate_ids": []}
        ).status_code
        == 404
    )

    reviewed = client.post(
        f"/api/runs/{run_id}/review-bulk",
        json={
            "reviews": [
                {"candidate_id": first, "approved": True},
                {"candidate_id": second, "approved": False},
                {"candidate_id": "does-not-exist", "approved": True},
            ]
        },
    ).json()
    assert sorted(reviewed["updated"]) == sorted([first, second])
    assert reviewed["skipped"] == [
        {"id": "does-not-exist", "reason": "not found in run"}
    ]

    async def statuses():
        async with SessionLocal() as session:
            first_row = await session.get(CandidateScore, first)
            second_row = await session.get(CandidateScore, second)
            assert first_row is not None
            assert second_row is not None
            return first_row.status, second_row.status

    first_status, second_status = asyncio.run(statuses())
    assert first_status == CandidateStatus.approved
    assert second_status == CandidateStatus.rejected


def test_delete_preview_and_structured_conflict():
    client = _client()
    # A school of its own: one other runs share isn't deleted with this run.
    run_id = _seed_run(
        client, programs=[{"school_name": "Preview University", "program_name": "PhD in Review"}]
    )
    ids = _graph(run_id)

    async def add_log(task_id):
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

    task_id = client.get(f"/api/runs/{run_id}/tasks").json()[0]["id"]
    asyncio.run(add_log(task_id))

    preview = client.get(f"/api/runs/{run_id}/delete-preview").json()
    assert preview == {
        "schools": 2,
        "programs": 2,
        "professors": 1,
        "papers": 1,
        "candidates": 1,
        "drafts": 0,
        "tasks": 1,
        "tool_calls": 1,
    }
    assert client.get("/api/runs/does-not-exist/delete-preview").status_code == 404

    conflict = client.delete(f"/api/schools/{ids['school_id']}")
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["candidates"] == 1


def _search_graph(run_id, school_name, prof_name, score=0.8):
    """Unique names, so leftover rows from other modules never match the search."""

    async def setup():
        async with SessionLocal() as session:
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run_id)], name=school_name)
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name=f"PhD in {school_name}")
            session.add(program)
            await session.flush()
            professor = Professor(user_id=TEST_USER_ID, program_id=program.id, name=prof_name)
            session.add(professor)
            await session.flush()
            candidate = CandidateScore(user_id=TEST_USER_ID, 
                run_id=run_id,
                professor_id=professor.id,
                similarity_score=score,
                rationale="Aligns.",
                status=CandidateStatus.scored,
            )
            session.add(candidate)
            await session.flush()
            await session.commit()
            return candidate.id

    return asyncio.run(setup())


def test_candidate_search_across_runs():
    client = _client()
    first = _seed_run(client)
    second = _seed_run(client)
    _search_graph(first, "Zeta Alpha University", "Prof Zeta One", 0.9)
    _search_graph(second, "Zeta Beta University", "Prof Zeta Two", 0.7)

    found = client.get("/api/candidates/search", params={"q": "zeta"}).json()
    assert [c["professor_name"] for c in found] == ["Prof Zeta One", "Prof Zeta Two"]

    scoped = client.get("/api/candidates/search", params={"run_ids": second}).json()
    assert [c["professor_name"] for c in scoped] == ["Prof Zeta Two"]

    page = client.get("/api/candidates/search", params={"q": "zeta", "limit": 1})
    assert len(page.json()) == 1
    assert page.headers["X-Total-Count"] == "2"

    assert (
        client.get(
            "/api/candidates/search", params={"run_ids": "does-not-exist"}
        ).json()
        == []
    )
    assert (
        client.get("/api/candidates/search", params={"q": "no-such-professor"}).json()
        == []
    )

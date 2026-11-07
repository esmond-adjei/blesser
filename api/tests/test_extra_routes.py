import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from api.candidates.models import CandidateScore, CandidateStatus
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.outreach.models import EmailDraft
from api.prospects.models import Paper, Professor, Program, RunSchool, School
from api.runs.models import ResearchTask, Run, TaskStatus, ToolCallLog
from tests.conftest import TEST_USER_ID


def _client():
    return TestClient(app)


def test_api_routes_are_tagged_by_feature():
    paths = app.openapi()["paths"]
    groups = {}
    for path, operations in paths.items():
        if not path.startswith("/api/"):
            continue
        for operation in operations.values():
            assert operation.get("tags", []) and len(operation["tags"]) == 1, path
            groups.setdefault(operation["tags"][0], []).append(path)
    assert set(groups) == {
        "opportunities",
        "todos",
        "account",
        "usage",
        "agents",
        "auth",
        "billing",
        "models",
        "runs",
        "tasks",
        "workers",
        "schools",
        "programs",
        "professors",
        "candidates",
        "outreach",
        "applications",
        "assistant",
        "cv",
        "flows",
        "notifications",
    }


def _seed_run(client, programs=None):
    programs = (
        programs
        if programs is not None
        else [
            {
                "school_name": "Tree University",
                "program_name": "PhD in Robotics",
                "department_url": "https://example.edu/dept",
            },
        ]
    )
    resp = client.post(
        "/api/runs/from-list",
        json={
            "degree_level": "phd",
            "interest_statement": "robots",
            "programs": programs,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _make_graph(run_id):
    """One school/program/professor + papers + scored candidate + draft."""

    async def setup():
        async with SessionLocal() as session:
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run_id)], name="Graph University", country="Utopia")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, 
                school_id=school.id,
                name="PhD in Graph Robotics",
                department_url="https://example.edu/graph",
            )
            session.add(program)
            await session.flush()
            professor = Professor(user_id=TEST_USER_ID, 
                program_id=program.id,
                name="Prof Graph",
                openalex_id="https://openalex.org/A1",
            )
            session.add(professor)
            await session.flush()
            session.add(
                Paper(user_id=TEST_USER_ID, 
                    professor_id=professor.id,
                    title="Graph navigation with RL",
                    abstract="robots navigating graphs",
                    year=2024,
                    url="https://example.edu/p1",
                )
            )
            session.add(
                Paper(user_id=TEST_USER_ID, 
                    professor_id=professor.id,
                    title="Unrelated medieval poetry",
                    abstract="roses",
                    year=2020,
                    url=None,
                )
            )
            candidate = CandidateScore(user_id=TEST_USER_ID, 
                run_id=run_id,
                professor_id=professor.id,
                similarity_score=0.91,
                rationale="Graph navigation with RL aligns.",
                status=CandidateStatus.scored,
            )
            session.add(candidate)
            await session.flush()
            draft = EmailDraft(user_id=TEST_USER_ID, 
                candidate_id=candidate.id,
                subject="Prospective PhD student",
                body="Hello Prof Graph",
            )
            session.add(draft)
            await session.commit()
            return {
                "school_id": school.id,
                "program_id": program.id,
                "professor_id": professor.id,
                "candidate_id": candidate.id,
                "draft_id": draft.id,
            }

    return asyncio.run(setup())


def test_list_runs_reports_progress_counts():
    client = _client()
    before = {r["id"] for r in client.get("/api/runs").json()}
    run_id = _seed_run(
        client,
        programs=[
            {"school_name": "S1", "program_name": "P1"},
            {"school_name": "S2", "program_name": "P2"},
        ],
    )
    runs = client.get("/api/runs").json()
    assert len(runs) == len(before) + 1
    entry = next(r for r in runs if r["id"] == run_id)
    assert entry["region"] == "(preselected list)"
    assert entry["tasks"] == {"pending": 2, "running": 0, "done": 0, "error": 0}
    assert entry["candidates"] == 0


def test_programs_tree_and_missing_run():
    client = _client()
    run_id = _seed_run(client)
    ids = _make_graph(run_id)

    tree = client.get(f"/api/runs/{run_id}/programs").json()
    by_name = {s["name"]: s for s in tree}
    assert by_name["Tree University"]["programs"][0]["professors"] == 0
    graph = by_name["Graph University"]
    assert graph["country"] == "Utopia"
    assert len(graph["programs"]) == 1
    assert graph["programs"][0]["name"] == "PhD in Graph Robotics"
    assert graph["programs"][0]["department_url"] == "https://example.edu/graph"
    assert graph["programs"][0]["professors"] == 1
    assert graph["programs"][0]["id"] == ids["program_id"]

    resp = client.get("/api/runs/does-not-exist/programs")
    assert resp.status_code == 404


def test_candidate_detail():
    client = _client()
    run_id = _seed_run(client)
    ids = _make_graph(run_id)

    resp = client.get(f"/api/candidates/{ids['candidate_id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["professor_name"] == "Prof Graph"
    assert body["school_name"] == "Graph University"
    assert body["program_name"] == "PhD in Graph Robotics"
    assert body["similarity_score"] == 0.91
    assert body["interest"] == client.get(f"/api/runs/{run_id}").json()["interest_statement"]
    assert body["status"] == "scored"
    assert {p["title"] for p in body["papers"]} == {
        "Graph navigation with RL",
        "Unrelated medieval poetry",
    }
    assert body["draft_subject"] == "Prospective PhD student"
    assert body["draft_body"] == "Hello Prof Graph"

    shortlist = client.get(f"/api/runs/{run_id}/candidates").json()
    row = next(r for r in shortlist if r["id"] == ids["candidate_id"])
    assert row["draft_subject"] == "Prospective PhD student"

    assert client.get("/api/candidates/does-not-exist").status_code == 404


def test_candidate_detail_lists_the_professors_other_matches():
    client = _client()
    run_id = _seed_run(client)
    ids = _make_graph(run_id)
    other_run = _seed_run(client)

    async def rematch():
        async with SessionLocal() as session:
            other = CandidateScore(
                user_id=TEST_USER_ID, run_id=other_run, professor_id=ids["professor_id"],
                similarity_score=0.95, rationale="r",
            )
            session.add(other)
            await session.commit()
            return other.id

    other_id = asyncio.run(rematch())
    matches = client.get(f"/api/candidates/{ids['candidate_id']}").json()["matches"]
    assert [(m["id"], m["run_id"]) for m in matches] == [(other_id, other_run), (ids["candidate_id"], run_id)]
    assert matches[0]["interest"] == client.get(f"/api/runs/{other_run}").json()["interest_statement"]


def _make_task_with_logs(run_id):
    async def setup():
        async with SessionLocal() as session:
            task = ResearchTask(user_id=TEST_USER_ID, 
                run_id=run_id, task_type="discover_programs", status=TaskStatus.done
            )
            session.add(task)
            await session.flush()
            session.add(
                ToolCallLog(user_id=TEST_USER_ID, 
                    task_id=task.id,
                    turn=1,
                    tool_name="search_web",
                    input_json='{"query": "robotics phd"}',
                    result_json='{"results": []}',
                    ok=True,
                )
            )
            session.add(
                ToolCallLog(user_id=TEST_USER_ID, 
                    task_id=task.id,
                    turn=2,
                    tool_name="fetch_page",
                    input_json='{"url": "https://example.edu"}',
                    result_json='{"error": "boom"}',
                    ok=False,
                )
            )
            await session.commit()
            return task.id

    return asyncio.run(setup())


def test_tool_calls():
    client = _client()
    run_id = _seed_run(client)
    task_id = _make_task_with_logs(run_id)

    logs = client.get(f"/api/tasks/{task_id}/tool-calls").json()
    assert [l["turn"] for l in logs] == [1, 2]
    assert logs[0]["tool_name"] == "search_web"
    assert logs[0]["input"] == {"query": "robotics phd"}
    assert logs[0]["result"] == {"results": []}
    assert logs[0]["ok"] is True
    assert logs[1]["ok"] is False

    assert client.get("/api/tasks/does-not-exist/tool-calls").status_code == 404


def test_retry_task():
    client = _client()
    run_id = _seed_run(client)

    async def setup():
        async with SessionLocal() as session:
            task = ResearchTask(user_id=TEST_USER_ID, 
                run_id=run_id,
                task_type="discover_programs",
                status=TaskStatus.error,
                error="boom",
                messages_json='[{"role": "user", "content": "go"}]',
            )
            session.add(task)
            await session.commit()
            return task.id

    task_id = asyncio.run(setup())

    resp = client.post(f"/api/tasks/{task_id}/retry")
    assert resp.status_code == 200
    assert resp.json() == {"status": "pending"}

    async def fetch():
        async with SessionLocal() as session:
            return await session.get(ResearchTask, task_id)

    task = asyncio.run(fetch())
    assert task is not None
    assert task.status == TaskStatus.pending
    assert task.error is None
    assert task.messages_json == '[{"role": "user", "content": "go"}]'

    assert client.post(f"/api/tasks/{task_id}/retry").status_code == 400
    assert client.post("/api/tasks/does-not-exist/retry").status_code == 404


def test_run_and_task_rows_roundtrip():
    client = _client()
    run_id = _seed_run(client)
    assert client.get(f"/api/runs/{run_id}").status_code == 200
    tasks = client.get(f"/api/runs/{run_id}/tasks").json()
    assert len(tasks) == 1
    assert tasks[0]["task_type"] == "research_professor"

    async def count_runs():
        async with SessionLocal() as session:
            result = await session.execute(select(Run))
            return len(result.scalars().all())

    assert asyncio.run(count_runs()) >= 1


def test_list_tasks_filters_by_task_type():
    client = _client()
    run_id = _seed_run(client)

    async def setup():
        async with SessionLocal() as session:
            session.add(
                ResearchTask(user_id=TEST_USER_ID, 
                    run_id=run_id,
                    task_type="draft_email",
                    status=TaskStatus.done,
                )
            )
            await session.commit()

    asyncio.run(setup())

    all_tasks = client.get(f"/api/runs/{run_id}/tasks").json()
    assert {t["task_type"] for t in all_tasks} == {"research_professor", "draft_email"}

    resp = client.get(f"/api/runs/{run_id}/tasks", params={"task_type": "draft_email"})
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "1"
    assert [t["task_type"] for t in resp.json()] == ["draft_email"]

    resp = client.get(
        f"/api/runs/{run_id}/tasks",
        params={"task_type": "research_professor", "status": "done"},
    )
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "0"
    assert resp.json() == []


def test_task_pages_never_repeat_a_task():
    """Tasks queued in one batch share a created_at; offset pages must still partition them."""
    client = _client()
    run_id = _seed_run(client)
    stamp = datetime.now(UTC).replace(tzinfo=None)

    async def setup():
        async with SessionLocal() as session:
            for _ in range(130):
                session.add(
                    ResearchTask(user_id=TEST_USER_ID,
                        run_id=run_id,
                        task_type="draft_email",
                        status=TaskStatus.done,
                        created_at=stamp,
                    )
                )
            await session.commit()

    asyncio.run(setup())

    for sort in ("recent", "created"):
        seen: list[str] = []
        for offset in range(0, 140, 20):
            resp = client.get(
                f"/api/runs/{run_id}/tasks",
                params={"task_type": "draft_email", "sort": sort, "limit": 20, "offset": offset},
            )
            seen += [t["id"] for t in resp.json()]
        assert len(seen) == 130
        assert len(set(seen)) == 130


def test_research_professor_tasks_carry_school_target_name():
    """research_professor rows target a program id, so the school name is the label."""
    client = _client()
    run_id = _seed_run(client)
    tasks = client.get(f"/api/runs/{run_id}/tasks").json()
    research = [t for t in tasks if t["task_type"] == "research_professor"]
    assert len(research) == 1
    assert research[0]["target_name"] == "Tree University"


def test_draft_email_tasks_carry_professor_school_target_name():
    client = _client()
    run_id = _seed_run(client)
    ids = _make_graph(run_id)

    resp = client.post(f"/api/candidates/{ids['candidate_id']}/request-draft")
    assert resp.status_code == 200, resp.text
    tasks = client.get(f"/api/runs/{run_id}/tasks").json()
    singles = [t for t in tasks if t["task_type"] == "draft_email"]
    assert len(singles) == 1
    assert singles[0]["target_name"] == "Prof Graph, Graph University"

    # Bulk labels the same way (fresh candidate, so no in-flight draft to skip).
    ids2 = _make_graph(run_id)
    resp = client.post(
        f"/api/runs/{run_id}/request-drafts",
        json={"candidate_ids": [ids2["candidate_id"]]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["queued"] == [ids2["candidate_id"]]
    tasks = client.get(
        f"/api/runs/{run_id}/tasks", params={"task_type": "draft_email"}
    ).json()
    assert len(tasks) == 2
    assert {t["target_name"] for t in tasks} == {"Prof Graph, Graph University"}


def test_run_creation_persists_default_budgets():
    client = _client()

    run_id = _seed_run(client)
    body = client.get(f"/api/runs/{run_id}").json()
    assert body["max_programs"] == settings.max_programs_per_run
    assert body["max_professors"] == settings.max_candidates_per_run
    assert body["max_professors_per_program"] == settings.max_professors_per_program

    resp = client.post(
        "/api/runs",
        json={
            "region": "EU",
            "field": "Physics",
            "degree_level": "phd",
            "interest_statement": "quantum",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["max_programs"] == settings.max_programs_per_run
    assert body["max_professors"] == settings.max_candidates_per_run
    assert body["max_professors_per_program"] == settings.max_professors_per_program

    resp = client.post(
        "/api/runs/from-list",
        json={
            "degree_level": "phd",
            "interest_statement": "robots",
            "programs": [{"school_name": "S9", "program_name": "P9"}],
            "max_programs": 3,
            "max_professors": 4,
            "max_professors_per_program": 2,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["max_programs"] == 3
    assert body["max_professors"] == 4
    assert body["max_professors_per_program"] == 2

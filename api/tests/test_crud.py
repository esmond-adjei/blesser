import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api.candidates.models import CandidateScore, CandidateStatus
from api.core.db import SessionLocal
from api.main import app
from api.outreach.models import EmailDraft
from api.prospects.models import Paper, Professor, Program, RunSchool, School
from api.runs.models import ResearchTask, Run, ToolCallLog
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
                {"school_name": "Crud University", "program_name": "PhD in Crud"}
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_school_crud():
    client = _client()
    run_id = _seed_run(client)

    created = client.post(
        f"/api/runs/{run_id}/schools",
        json={"name": "Manual University", "country": "Nowhere"},
    )
    assert created.status_code == 200
    school_id = created.json()["id"]
    assert created.json()["programs"] == []

    assert (
        client.post("/api/runs/does-not-exist/schools", json={"name": "X"}).status_code
        == 404
    )

    fetched = client.get(f"/api/schools/{school_id}").json()
    assert fetched["name"] == "Manual University"
    assert fetched["programs"] == []
    assert client.get("/api/schools/does-not-exist").status_code == 404

    patched = client.patch(
        f"/api/schools/{school_id}", json={"country": "Somewhere"}
    ).json()
    assert patched["country"] == "Somewhere"
    assert patched["name"] == "Manual University"
    assert (
        client.patch("/api/schools/does-not-exist", json={"name": "Y"}).status_code
        == 404
    )

    assert client.delete(f"/api/schools/{school_id}").json() == {"status": "deleted"}
    assert client.get(f"/api/schools/{school_id}").status_code == 404
    assert client.delete(f"/api/schools/{school_id}").status_code == 404


def _make_professor_chain(run_id, school_name="Guard University"):
    """School/program/professor + scored candidate. Returns ids."""

    async def setup():
        async with SessionLocal() as session:
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run_id)], name=school_name)
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="PhD in Guarding")
            session.add(program)
            await session.flush()
            professor = Professor(user_id=TEST_USER_ID, program_id=program.id, name="Prof Guard")
            session.add(professor)
            await session.flush()
            session.add(Paper(user_id=TEST_USER_ID, professor_id=professor.id, title="On guarding"))
            candidate = CandidateScore(user_id=TEST_USER_ID, 
                run_id=run_id,
                professor_id=professor.id,
                similarity_score=0.8,
                rationale="On guarding aligns.",
                status=CandidateStatus.scored,
            )
            session.add(candidate)
            await session.commit()
            return {
                "school_id": school.id,
                "program_id": program.id,
                "professor_id": professor.id,
                "candidate_id": candidate.id,
            }

    return asyncio.run(setup())


def test_delete_guards_reviewed_work():
    client = _client()
    run_id = _seed_run(client)
    ids = _make_professor_chain(run_id)

    assert client.delete(f"/api/schools/{ids['school_id']}").status_code == 409
    assert client.delete(f"/api/programs/{ids['program_id']}").status_code == 409
    assert client.delete(f"/api/professors/{ids['professor_id']}").status_code == 409

    assert client.delete(f"/api/candidates/{ids['candidate_id']}").json() == {
        "status": "deleted"
    }
    assert client.get(f"/api/candidates/{ids['candidate_id']}").status_code == 404
    assert client.delete(f"/api/candidates/{ids['candidate_id']}").status_code == 404

    assert client.delete(f"/api/professors/{ids['professor_id']}").json() == {
        "status": "deleted"
    }
    assert client.delete(f"/api/programs/{ids['program_id']}").json() == {
        "status": "deleted"
    }
    assert client.delete(f"/api/schools/{ids['school_id']}").json() == {
        "status": "deleted"
    }


def test_run_faculty_roll():
    client = _client()
    run_id = _seed_run(client)
    ids = _make_professor_chain(run_id, school_name="Faculty University")

    rows = client.get(f"/api/runs/{run_id}/faculty").json()
    mine = [r for r in rows if r["id"] == ids["professor_id"]]
    assert len(mine) == 1
    (row,) = mine
    assert row["name"] == "Prof Guard"
    assert row["program"] == "PhD in Guarding"
    assert row["program_id"] == ids["program_id"]
    assert row["school"] == "Faculty University"
    assert row["school_id"] == ids["school_id"]
    assert row["papers"] == 1
    assert row["candidate_id"] == ids["candidate_id"]
    assert {r["school"] for r in rows} <= {"Crud University", "Faculty University"}

    assert client.get("/api/runs/does-not-exist/faculty").status_code == 404


def test_program_create_queues_research_and_crud():
    client = _client()
    run_id = _seed_run(client)
    school_id = client.get(f"/api/runs/{run_id}/programs").json()[0]["id"]

    created = client.post(
        f"/api/schools/{school_id}/programs",
        json={"name": "MS in Manual", "department_url": "https://example.edu/ms"},
    )
    assert created.status_code == 200
    program_id = created.json()["id"]
    assert created.json()["professors"] == []
    assert (
        client.post(
            "/api/schools/does-not-exist/programs", json={"name": "X"}
        ).status_code
        == 404
    )

    tasks = client.get(f"/api/runs/{run_id}/tasks").json()
    assert any(
        t["task_type"] == "research_professor" and t["target_id"] == program_id
        for t in tasks
    )

    fetched = client.get(f"/api/programs/{program_id}").json()
    assert fetched["school_name"] == "Crud University"
    assert fetched["professors"] == []
    assert client.get("/api/programs/does-not-exist").status_code == 404

    patched = client.patch(
        f"/api/programs/{program_id}", json={"name": "MS in Renamed"}
    ).json()
    assert patched["name"] == "MS in Renamed"

    assert client.delete(f"/api/programs/{program_id}").json() == {"status": "deleted"}
    assert client.get(f"/api/programs/{program_id}").status_code == 404


def test_professor_read_and_update():
    client = _client()
    run_id = _seed_run(client)
    ids = _make_professor_chain(run_id, school_name="Detail University")

    body = client.get(f"/api/professors/{ids['professor_id']}").json()
    assert body["name"] == "Prof Guard"
    assert body["school_name"] == "Detail University"
    assert body["program_name"] == "PhD in Guarding"
    assert body["candidate_id"] == ids["candidate_id"]
    assert [p["title"] for p in body["papers"]] == ["On guarding"]
    assert client.get("/api/professors/does-not-exist").status_code == 404

    patched = client.patch(
        f"/api/professors/{ids['professor_id']}",
        json={"email": "guard@example.edu"},
    ).json()
    assert patched["email"] == "guard@example.edu"
    assert patched["name"] == "Prof Guard"

    assert body["lab_name"] is None
    lab_patched = client.patch(
        f"/api/professors/{ids['professor_id']}",
        json={
            "lab_name": "Guard Lab",
            "bio": "Guards things.",
            "bio_source": "generated",
        },
    ).json()
    assert lab_patched["lab_name"] == "Guard Lab"
    assert lab_patched["bio"] == "Guards things."
    assert lab_patched["bio_source"] == "generated"
    assert body["photo_url"] is None
    photo_patched = client.patch(
        f"/api/professors/{ids['professor_id']}",
        json={"photo_url": "https://faculty.example.edu/guard.jpg"},
    ).json()
    assert photo_patched["photo_url"] == "https://faculty.example.edu/guard.jpg"
    socials_patched = client.patch(
        f"/api/professors/{ids['professor_id']}",
        json={
            "socials": [
                {"label": "Scholar", "url": "https://scholar.example.edu/guard"}
            ]
        },
    ).json()
    assert socials_patched["socials"] == [
        {"label": "Scholar", "url": "https://scholar.example.edu/guard"}
    ]


def _make_draft(run_id):
    ids = _make_professor_chain(run_id, school_name="Draft University")

    async def setup():
        async with SessionLocal() as session:
            draft = EmailDraft(user_id=TEST_USER_ID, 
                candidate_id=ids["candidate_id"],
                subject="Hello",
                body="Body here",
            )
            session.add(draft)
            candidate = await session.get(CandidateScore, ids["candidate_id"])
            assert candidate is not None
            candidate.status = CandidateStatus.drafted
            await session.commit()
            return draft.id

    ids["draft_id"] = asyncio.run(setup())
    return ids


def test_draft_outbox_edit_and_discard():
    client = _client()
    run_id = _seed_run(client)
    ids = _make_draft(run_id)

    drafts = client.get(f"/api/runs/{run_id}/drafts").json()
    assert len(drafts) == 1
    assert drafts[0]["professor_name"] == "Prof Guard"
    assert drafts[0]["subject"] == "Hello"
    assert client.get("/api/runs/does-not-exist/drafts").status_code == 404

    detail = client.get(f"/api/candidates/{ids['candidate_id']}").json()
    assert detail["draft_subject"] == "Hello"
    assert detail["draft_created_at"]

    edited = client.patch(
        f"/api/drafts/{ids['draft_id']}", json={"subject": "Personalized hello"}
    ).json()
    assert edited["subject"] == "Personalized hello"
    assert edited["body"] == "Body here"
    assert (
        client.patch("/api/drafts/does-not-exist", json={"subject": "x"}).status_code
        == 404
    )

    assert client.delete(f"/api/drafts/{ids['draft_id']}").json() == {
        "status": "deleted"
    }
    assert client.delete(f"/api/drafts/{ids['draft_id']}").status_code == 404

    detail = client.get(f"/api/candidates/{ids['candidate_id']}").json()
    assert detail["status"] == "scored"
    assert detail["draft_subject"] is None


def test_candidate_drafts_lists_all():
    client = _client()
    run_id = _seed_run(client)
    ids = _make_draft(run_id)

    async def add_second():
        async with SessionLocal() as session:
            draft = EmailDraft(user_id=TEST_USER_ID, 
                candidate_id=ids["candidate_id"],
                subject="Second angle",
                body="Another body",
            )
            session.add(draft)
            await session.commit()
            return draft.id

    second_id = asyncio.run(add_second())

    drafts = client.get(f"/api/candidates/{ids['candidate_id']}/drafts").json()
    assert [d["id"] for d in drafts] == [second_id, ids["draft_id"]]
    assert all(d["subject"] for d in drafts)
    assert client.get("/api/candidates/does-not-exist/drafts").status_code == 404

    items = client.get(f"/api/runs/{run_id}/candidates").json()
    assert items[0]["draft_count"] == 2
    assert items[0]["draft_id"] in {second_id, ids["draft_id"]}


def test_task_read_and_prune():
    client = _client()
    run_id = _seed_run(client)
    task_id = client.get(f"/api/runs/{run_id}/tasks").json()[0]["id"]

    fetched = client.get(f"/api/tasks/{task_id}").json()
    assert fetched["task_type"] == "research_professor"
    assert client.get("/api/tasks/does-not-exist").status_code == 404

    assert client.delete(f"/api/tasks/{task_id}").json() == {"status": "deleted"}
    assert client.get(f"/api/tasks/{task_id}").status_code == 404
    assert client.delete(f"/api/tasks/{task_id}").status_code == 404


def test_run_delete_removes_subtree():
    client = _client()
    run_id = _seed_run(client)
    ids = _make_draft(run_id)
    task_id = client.get(f"/api/runs/{run_id}/tasks").json()[0]["id"]

    async def seed_log():
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

    asyncio.run(seed_log())

    assert client.delete(f"/api/runs/{run_id}").json() == {"status": "deleted"}
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.delete(f"/api/runs/{run_id}").status_code == 404

    async def fetch_leftovers():
        async with SessionLocal() as session:
            counts = {}
            counts["schools"] = (
                await session.execute(
                    select(func.count())
                    .select_from(RunSchool)
                    .where(RunSchool.run_id == run_id)
                )
            ).scalar()
            counts["tasks"] = (
                await session.execute(
                    select(func.count())
                    .select_from(ResearchTask)
                    .where(ResearchTask.run_id == run_id)
                )
            ).scalar()
            counts["candidates"] = (
                await session.execute(
                    select(func.count())
                    .select_from(CandidateScore)
                    .where(CandidateScore.run_id == run_id)
                )
            ).scalar()
            counts["runs"] = (
                await session.execute(
                    select(func.count()).select_from(Run).where(Run.id == run_id)
                )
            ).scalar()
            # Tables without a run_id are checked by the exact ids of this run.
            counts["professor"] = await session.get(Professor, ids["professor_id"])
            counts["draft"] = await session.get(EmailDraft, ids["draft_id"])
            counts["logs"] = (
                await session.execute(
                    select(func.count())
                    .select_from(ToolCallLog)
                    .where(ToolCallLog.task_id == task_id)
                )
            ).scalar()
            return counts

    counts = asyncio.run(fetch_leftovers())
    assert counts["schools"] == 0
    assert counts["tasks"] == 0
    assert counts["candidates"] == 0
    assert counts["runs"] == 0
    assert counts["professor"] is None
    assert counts["draft"] is None
    assert counts["logs"] == 0


def test_cards_carry_pictures_and_recipient():
    client = _client()
    run_id = _seed_run(client)
    ids = _make_draft(run_id)

    async def decorate():
        async with SessionLocal() as session:
            professor = await session.get(Professor, ids["professor_id"])
            professor.photo_url = "https://img.example.edu/guard.jpg"
            professor.email = "guard@example.edu"
            school = await session.get(School, ids["school_id"])
            school.image_url = "https://img.example.edu/campus.jpg"
            await session.commit()

    asyncio.run(decorate())

    rows = client.get(f"/api/runs/{run_id}/candidates").json()
    row = next(c for c in rows if c["id"] == ids["candidate_id"])
    assert row["professor_photo_url"] == "https://img.example.edu/guard.jpg"
    assert row["school_image_url"] == "https://img.example.edu/campus.jpg"

    detail = client.get(f"/api/candidates/{ids['candidate_id']}").json()
    assert detail["professor_photo_url"] == "https://img.example.edu/guard.jpg"
    assert detail["school_image_url"] == "https://img.example.edu/campus.jpg"

    draft = client.get(f"/api/runs/{run_id}/drafts").json()[0]
    assert draft["professor_email"] == "guard@example.edu"
    assert draft["professor_photo_url"] == "https://img.example.edu/guard.jpg"
    assert draft["school_name"] == "Draft University"
    assert draft["program_name"] == "PhD in Guarding"
    edited = client.patch(f"/api/drafts/{ids['draft_id']}", json={"subject": "Hi"}).json()
    assert edited["school_name"] == "Draft University"

    made = client.post("/api/applications", json={"school": "draft  university!", "program": "PhD"})
    assert made.status_code in (200, 201), made.text
    apps = client.get("/api/applications").json()
    match = next(a for a in apps if a["id"] == made.json()["id"])
    assert match["school_image_url"] == "https://img.example.edu/campus.jpg"
    client.delete(f"/api/applications/{match['id']}")

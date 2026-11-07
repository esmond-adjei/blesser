import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.agent.tools import ToolContext
from api.applications import notes as application_notes
from api.applications import tools as application_tools
from api.applications.models import Application
from api.candidates.models import CandidateScore, CandidateStatus
from api.core.db import SessionLocal
from api.main import app
from api.prospects.models import Professor, Program, RunSchool, School
from api.runs.models import Run
from tests.conftest import TEST_USER_ID


@pytest.fixture(autouse=True)
def _clean_applications():
    """The scratch database lives for the session: empty the tracker between tests."""

    async def _wipe():
        async with SessionLocal() as session:
            await session.execute(delete(Application))
            await session.commit()

    asyncio.run(_wipe())


def _client():
    return TestClient(app)


def _seed_run(client):
    resp = client.post(
        "/api/runs/from-list",
        json={
            "degree_level": "phd",
            "interest_statement": "robots",
            "programs": [
                {"school_name": "Review University", "program_name": "PhD in Review"}
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


NOTES = """\
## Summary
McGill's CS graduate admissions page describes the process.

## Key dates
Dec 15

## Costs & waivers
Fee waivers for eligible applicants.

## Watch-outs
None found.
"""


def test_crud_round_trip():
    client = _client()
    created = client.post(
        "/api/applications",
        json={
            "school": "McGill",
            "program": "MSc Computer Science",
            "deadline": "2026-12-15",
            "requirements": [{"label": "Statement", "done": False}],
            "fee_waiver": True,
            "fee_waiver_notes": "Ask the department.",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["source"] == "manual"
    assert body["status"] == "wishlist"
    assert body["fee_waiver"] is True
    app_id = body["id"]

    listed = client.get("/api/applications").json()
    assert [a["id"] for a in listed] == [app_id]

    patched = client.patch(
        f"/api/applications/{app_id}",
        json={
            "status": "applying",
            "requirements": [
                {"label": "Statement", "done": True},
                {"label": "Transcripts", "done": False},
            ],
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "applying"
    assert patched.json()["requirements"] == [
        {"label": "Statement", "done": True},
        {"label": "Transcripts", "done": False},
    ]

    assert client.delete(f"/api/applications/{app_id}").status_code == 200
    assert client.get(f"/api/applications/{app_id}").status_code == 404


def test_create_validates():
    client = _client()
    assert client.post("/api/applications", json={}).status_code == 422
    assert (
        client.post(
            "/api/applications", json={"school": "X", "status": "bogus"}
        ).status_code
        == 422
    )


def _agent_save(run_id, tool_input):
    async def setup():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            ctx = ToolContext(session=session, run=run)
            return await application_tools.handle_save_application(tool_input, ctx)

    return asyncio.run(setup())


def _agent_input(**overrides):
    base = {
        "school": "McGill University",
        "program": "MSc Computer Science",
        "degree_type": "masters",
        "link": "https://mcgill.ca/apply",
        "deadline": "2026-12-15",
        "requirements": ["Statement", "Transcripts"],
        "fee_waiver": True,
        "fee_waiver_notes": "Ask the department.",
        "professors": ["Prof A"],
        "notes": NOTES,
    }
    base.update(overrides)
    return base


def test_agent_upsert_creates_then_fills_empty_only():
    client = _client()
    run_id = _seed_run(client)

    first = _agent_save(run_id, _agent_input())
    assert first["created"] is True
    assert first["application_id"]
    row = client.get(f"/api/applications/{first['application_id']}").json()
    assert row["source"] == "agent"
    assert row["run_id"] == run_id
    assert row["status"] == "wishlist"
    assert row["requirements"] == [
        {"label": "Statement", "done": False},
        {"label": "Transcripts", "done": False},
    ]

    client.patch(
        f"/api/applications/{first['application_id']}",
        json={
            "offer": "TAship confirmed",
            "status": "applying",
            "degree_type": "phd",
            "requirements": [{"label": "Statement", "done": True}],
        },
    )

    # Same school + program in different case merges, never clobbers.
    second = _agent_save(
        run_id,
        _agent_input(
            school="mcgill university",
            program="msc computer science",
            offer="RAship rumored",
            degree_type="masters",
            requirements=["References"],
            professors=["Prof B"],
            link="",
            notes=NOTES.replace("McGill's CS", "McGill's CS (updated)"),
        ),
    )
    assert second["created"] is False
    assert second["application_id"] == first["application_id"]
    assert "offer" not in second["updated_fields"]
    assert "degree_type" not in second["updated_fields"]
    assert "notes" not in second["updated_fields"]

    row = client.get(f"/api/applications/{first['application_id']}").json()
    assert row["offer"] == "TAship confirmed"
    assert row["status"] == "applying"
    assert row["degree_type"] == "phd"
    assert row["notes"] == NOTES
    assert row["requirements"] == [
        {"label": "Statement", "done": True},
        {"label": "References", "done": False},
    ]
    assert [p["name"] for p in row["professors"]] == ["Prof A", "Prof B"]
    assert "link" in second["updated_fields"] or row["link"] == "https://mcgill.ca/apply"


def test_agent_save_rejects_malformed_notes():
    client = _client()
    run_id = _seed_run(client)
    result = _agent_save(run_id, _agent_input(notes="Some freeform text."))
    assert "error" in result
    assert "## Summary" in result["error"]
    assert client.get("/api/applications").json() == []


def test_note_template_verifier():
    assert application_notes.verify_application_notes({"notes": NOTES}) is None
    assert "## Summary" in (
        application_notes.verify_application_notes({"notes": ""}) or ""
    )
    missing = application_notes.verify_application_notes(
        {"notes": "## Summary\nHi.\n\n## Key dates\nNone."}
    )
    assert missing is not None and "## Costs & waivers" in missing


def _resolve_graph(run_id):
    """Unique names so leftover rows from other modules can't collide with the attach rule."""

    async def setup():
        async with SessionLocal() as session:
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run_id)], name="Resolve University")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="PhD in Resolve")
            session.add(program)
            await session.flush()
            professor = Professor(user_id=TEST_USER_ID, program_id=program.id, name="Prof Resolve")
            session.add(professor)
            await session.flush()
            candidate = CandidateScore(user_id=TEST_USER_ID, 
                run_id=run_id,
                professor_id=professor.id,
                similarity_score=0.9,
                rationale="R aligns.",
                status=CandidateStatus.scored,
            )
            session.add(candidate)
            await session.flush()
            await session.commit()
            return {
                "professor_id": professor.id,
                "candidate_id": candidate.id,
            }

    return asyncio.run(setup())


def test_resolve_professors_backfills_ids():
    client = _client()
    run_id = _seed_run(client)
    ids = _resolve_graph(run_id)
    saved = _agent_save(
        run_id,
        _agent_input(
            school="Resolve University",
            program="PhD in Resolve",
            professors=["Prof Resolve", "Prof Unknown"],
        ),
    )
    app_id = saved["application_id"]

    resolved = client.post(f"/api/applications/{app_id}/resolve-professors")
    assert resolved.status_code == 200, resolved.text
    links = {p["name"]: p for p in resolved.json()["professors"]}
    assert links["Prof Resolve"]["professor_id"] == ids["professor_id"]
    assert links["Prof Resolve"]["candidate_id"] == ids["candidate_id"]
    assert links["Prof Unknown"]["professor_id"] is None
    assert links["Prof Unknown"]["candidate_id"] is None

    # Researcher-set professor ids are never overwritten; a missing
    # candidate id alongside one still gets filled.
    patched = client.patch(
        f"/api/applications/{app_id}",
        json={
            "professors": [
                {
                    "name": "Prof Resolve",
                    "professor_id": ids["professor_id"],
                    "candidate_id": None,
                }
            ]
        },
    )
    assert patched.status_code == 200, patched.text
    again = client.post(f"/api/applications/{app_id}/resolve-professors")
    assert again.status_code == 200, again.text
    (link,) = again.json()["professors"]
    assert link["professor_id"] == ids["professor_id"]
    assert link["candidate_id"] == ids["candidate_id"]

    assert (
        client.post("/api/applications/does-not-exist/resolve-professors").status_code
        == 404
    )


def test_resolve_professor_candidate_from_another_run():
    client = _client()
    research_run = _seed_run(client)
    application_run = _seed_run(client)
    ids = _resolve_graph(research_run)
    saved = _agent_save(
        application_run,
        _agent_input(school="Resolve University", program="PhD in Resolve", professors=["Prof Resolve"]),
    )
    updated = client.patch(
        f"/api/applications/{saved['application_id']}",
        json={"professors": [{"name": "Prof Resolve", "professor_id": ids["professor_id"]}]},
    )
    assert updated.status_code == 200
    resolved = client.post(f"/api/applications/{saved['application_id']}/resolve-professors")
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["professors"][0]["candidate_id"] == ids["candidate_id"]

    async def add_same_run_candidate():
        async with SessionLocal() as session:
            candidate = CandidateScore(
                user_id=TEST_USER_ID, run_id=application_run, professor_id=ids["professor_id"],
                similarity_score=0.2, status=CandidateStatus.scored,
            )
            session.add(candidate)
            await session.flush()
            candidate_id = candidate.id
            await session.commit()
            return candidate_id

    preferred = asyncio.run(add_same_run_candidate())
    updated = client.patch(
        f"/api/applications/{saved['application_id']}",
        json={"professors": [{"name": "Prof Resolve", "professor_id": ids["professor_id"]}]},
    )
    assert updated.status_code == 200
    resolved = client.post(f"/api/applications/{saved['application_id']}/resolve-professors")
    assert resolved.json()["professors"][0]["candidate_id"] == preferred

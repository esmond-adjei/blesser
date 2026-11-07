import asyncio
import uuid

from fastapi.testclient import TestClient

from api.assistant import tools as assistant_tools
from api.core.db import SessionLocal
from api.main import app
from tests.conftest import TEST_USER_ID
from tests.test_crud import _make_draft, _seed_run


def _run(name: str, tool_input: dict, approved: bool = True) -> dict:
    async def go():
        async with SessionLocal() as session:
            return await assistant_tools.invoke(name, tool_input, session, TEST_USER_ID, approved=approved)

    return asyncio.run(go())


def test_search_finds_every_kind_by_name():
    client = TestClient(app)
    run_id = _seed_run(client)
    ids = _make_draft(run_id)  # Draft University / PhD in Guarding / Prof Guard / candidate / draft "Hello"
    tag = uuid.uuid4().hex[:6]
    app_id = _run("create_application", {"school": f"Draft University {tag}", "program": "PhD in Guarding"})["id"]

    found = _run("search", {"query": "guard"}, approved=False)
    assert any(p["id"] == ids["professor_id"] for p in found["professors"])
    assert any(c["id"] == ids["candidate_id"] for c in found["candidates"])
    assert any(p["id"] == ids["program_id"] for p in found["programs"])
    assert any(d["id"] == ids["draft_id"] for d in found["drafts"])
    assert any(a["id"] == app_id for a in _run("search", {"query": tag}, approved=False)["applications"])
    only = _run("search", {"query": "Draft University", "kinds": ["schools"]}, approved=False)
    assert set(only) >= {"schools"} and "professors" not in only
    assert "error" in _run("search", {"query": "a"}, approved=False)


def test_professor_and_candidate_can_be_updated():
    client = TestClient(app)
    run_id = _seed_run(client)
    ids = _make_draft(run_id)

    prof = _run("update_professor", {"professor_id": ids["professor_id"], "email": "guard@example.edu", "lab_name": "Guard Lab"})
    assert prof["email"] == "guard@example.edu" and prof["lab_name"] == "Guard Lab"
    assert _run("get_professor", {"professor_id": ids["professor_id"]}, approved=False)["lab_name"] == "Guard Lab"

    cand = _run("update_candidate", {"candidate_id": ids["candidate_id"], "status": "approved", "rationale": "Strong overlap."})
    assert cand["status"] == "approved" and cand["rationale"] == "Strong overlap."
    assert "error" in _run("update_candidate", {"candidate_id": ids["candidate_id"], "status": "drafted"})
    # The fit score is not a field: it can't be edited.
    assert "error" in _run("update_candidate", {"candidate_id": ids["candidate_id"], "similarity_score": 0.99})


def test_writes_need_approval_and_guards_still_apply():
    client = TestClient(app)
    run_id = _seed_run(client)
    ids = _make_draft(run_id)

    refused = _run("delete_professor", {"professor_id": ids["professor_id"]}, approved=False)
    assert "confirmation" in refused["error"]
    # A professor with a candidate can't be deleted: discard the candidate first.
    blocked = _run("delete_professor", {"professor_id": ids["professor_id"]})
    assert "error" in blocked and "candidate" in blocked["error"]

    assert _run("delete_draft", {"draft_id": ids["draft_id"]}) == {"status": "deleted"}
    assert _run("delete_candidate", {"candidate_id": ids["candidate_id"]}) == {"status": "deleted"}
    assert _run("delete_professor", {"professor_id": ids["professor_id"]}) == {"status": "deleted"}


def test_school_programme_application_and_run_lifecycle():
    client = TestClient(app)
    run_id = _seed_run(client)
    name = f"Gradis University {uuid.uuid4().hex[:6]}"

    school = _run("create_school", {"run_id": run_id, "name": name, "programs": ["PhD in Robots"]})
    assert school["name"] == name and [p["name"] for p in school["programs"]] == ["PhD in Robots"]
    assert _run("update_school", {"school_id": school["id"], "country": "Ghana"})["country"] == "Ghana"
    program = _run("create_program", {"school_id": school["id"], "name": "MSc in Robots"})
    assert _run("update_program", {"program_id": program["id"], "department_url": "https://x.edu/robots"})["department_url"] == "https://x.edu/robots"
    assert _run("delete_program", {"program_id": program["id"]}) == {"status": "deleted"}
    assert _run("delete_school", {"school_id": school["id"]}) == {"status": "deleted"}

    app_row = _run("create_application", {"school": name, "program": "PhD", "status": "applying", "requirements": ["CV", "Transcripts"]})
    assert app_row["status"] == "applying"
    assert _run("delete_application", {"application_id": app_row["id"]}) == {"status": "deleted"}

    assert _run("set_run_status", {"run_id": run_id, "action": "pause"})["status"] == "paused"
    assert _run("set_run_status", {"run_id": run_id, "action": "resume"})["status"] == "running"
    assert _run("update_run", {"run_id": run_id, "max_programs": 4})["updated"] == ["max_programs"]
    assert _run("delete_run", {"run_id": run_id}) == {"status": "deleted"}


def test_confirmation_cards_name_what_changes():
    assert assistant_tools.describe_call("delete_school", {"school_id": "s"}) == "Delete this school and its programmes"
    assert assistant_tools.describe_call("update_professor", {"professor_id": "p", "email": "e"}) == "Update professor (email)"


def test_show_record_shows_records_as_cards():
    from api.assistant import modes
    from api.assistant.sources import extract_sources

    client = TestClient(app)
    run_id = _seed_run(client)
    ids = _make_draft(run_id)
    cases = [
        ("candidate", ids["candidate_id"], f"/dossier/{ids['candidate_id']}"),
        ("professor", ids["professor_id"], None),
        ("draft", ids["draft_id"], f"/outbox/{ids['draft_id']}"),
        ("run", run_id, f"/runs/{run_id}"),
    ]
    for kind, id_, href in cases:
        shown = _run("show_record", {"kind": kind, "ids": [id_]}, approved=False)
        assert shown["kind"] == kind and shown["shown"] == 1, shown
        (source,) = extract_sources("show_record", shown)
        assert source["kind"] == kind and source["id"] == id_
        if href:
            assert source["href"] == href

    professor = _run("get_professor", {"professor_id": ids["professor_id"]}, approved=False)
    paper_id = professor["papers"][0]["id"]
    shown = _run("show_record", {"kind": "paper", "ids": [paper_id, "missing"]}, approved=False)
    assert shown["not_found"] == ["missing"]
    (source,) = extract_sources("show_record", shown)
    assert source["href"] == f"/professors/{ids['professor_id']}?paper={paper_id}"

    assert "error" in _run("show_record", {"kind": "nope", "ids": ["x"]}, approved=False)
    assert "error" in _run("show_record", {"kind": "draft", "ids": ["missing"]}, approved=False)
    # A read: offered in Chat mode, never behind a confirmation card.
    assert "show_record" in modes.READ_TOOLS
    assert "show_record" not in assistant_tools.CONFIRM_TOOLS

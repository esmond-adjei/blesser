import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from alembic import command
from api.assistant import tools as assistant_tools
from api.core.config import settings
from api.core.db import SessionLocal
from api.cv import models as cv_models
from api.main import app
from tests.conftest import TEST_USER_ID
from tests.test_cv_api import _execute
from tests.test_migrations import _cfg, _fetch, _run, _scratch_db

CV = "# Jane Doe\n\n## Experience\n\n- Lab tech at the Soft Robotics Lab, 2023-2025.\n- Built a gripper in Python.\n"
SOP = (
    "# Statement of purpose\n\n"
    "I want to study soft robotics.\n\n"
    "At the Soft Robotics Lab I built a gripper.\n"
)


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    target = tmp_path / "cv_storage"
    monkeypatch.setattr(settings, "cv_storage_dir", str(target))
    return target


@pytest.fixture(autouse=True)
def _clean():
    async def _wipe():
        async with SessionLocal() as session:
            await session.execute(delete(cv_models.CvSuggestion))
            await session.execute(delete(cv_models.CvTailoredVersion))
            await session.execute(delete(cv_models.CvDocument))
            await session.execute(delete(cv_models.DocumentFolder))
            await session.commit()

    asyncio.run(_wipe())


def _client():
    return TestClient(app)


def _create(client, kind="cv", markdown=CV, title=None, **extra):
    resp = client.post(
        "/api/cv/documents/text",
        json={"title": title or kind.upper(), "markdown": markdown, "kind": kind, **extra},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _tool(name, args):
    async def go():
        async with SessionLocal() as session:
            return await assistant_tools.HANDLERS[name](dict(args), session, TEST_USER_ID)

    return asyncio.run(go())


def test_documents_have_a_kind_and_list_by_kind():
    with _client() as client:
        cv = _create(client)
        sop = _create(client, "sop", SOP, "Statement of purpose")
        assert cv["kind"] == "cv" and sop["kind"] == "sop"
        assert {d["id"] for d in client.get("/api/cv/documents").json()} == {cv["id"], sop["id"]}
        only = client.get("/api/cv/documents", params={"kind": "sop"}).json()
        assert [d["id"] for d in only] == [sop["id"]]
        assert client.get("/api/cv/documents", params={"kind": "email"}).status_code == 422
        # There is no email kind: emails are Outbox drafts.
        bad = client.post("/api/cv/documents/text", json={"title": "x", "kind": "email"})
        assert bad.status_code == 422


def test_interest_statement_is_a_kind():
    with _client() as client:
        doc = _create(client, "interest", "# Research interests\n\nSoft grippers for fruit.\n", "Interest statement")
        assert doc["kind"] == "interest"
        only = client.get("/api/cv/documents", params={"kind": "interest"}).json()
        assert [d["id"] for d in only] == [doc["id"]]
    listed = _tool("list_documents", {"kind": "interest"})
    assert [d["id"] for d in listed["documents"]] == [doc["id"]]


def test_an_uploaded_statement_keeps_its_kind():
    with _client() as client:
        resp = client.post(
            "/api/cv/documents",
            files={"file": ("sop.md", SOP.encode(), "text/markdown")},
            data={"kind": "sop"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["kind"] == "sop" and resp.json()["markdown"] == SOP


def test_a_variant_of_a_statement_is_named_for_its_kind():
    with _client() as client:
        sop = _create(client, "sop", SOP)
        v = client.post(f"/api/cv/documents/{sop['id']}/versions", json={}).json()
        assert v["name"] == "Tailored statement of purpose"


def test_interest_suggestions_read_only_cvs():
    from api.runs import interests

    with _client() as client:
        cv = _create(client)
        _create(client, "note", "## Research interests\n\n- Knitting machines for long scarves\n")

    async def go():
        async with SessionLocal() as session:
            return await interests._collect_units(session, TEST_USER_ID)

    _, sources = asyncio.run(go())
    assert [s["document_id"] for s in sources] == [cv["id"]]


def test_folders_create_rename_reorder_and_delete():
    with _client() as client:
        a = client.post("/api/cv/folders", json={"name": "MIT"}).json()
        b = client.post("/api/cv/folders", json={"name": "Masters"}).json()
        assert [f["name"] for f in client.get("/api/cv/folders").json()] == ["MIT", "Masters"]
        renamed = client.patch(f"/api/cv/folders/{a['id']}", json={"name": "MIT 2027"}).json()
        assert renamed["name"] == "MIT 2027"
        order = client.put("/api/cv/folders/order", json={"ids": [b["id"], a["id"]]})
        assert [f["id"] for f in order.json()] == [b["id"], a["id"]]
        # A list missing a folder (another tab added one) is refused.
        assert client.put("/api/cv/folders/order", json={"ids": [a["id"]]}).status_code == 409

        doc = _create(client, folder_id=a["id"])
        assert doc["folder_id"] == a["id"]
        assert client.get("/api/cv/folders").json()[1]["document_count"] == 1
        assert client.delete(f"/api/cv/folders/{a['id']}").status_code == 200
        after = client.get(f"/api/cv/documents/{doc['id']}").json()
        assert after["folder_id"] is None and after["markdown"] == CV


def test_moving_a_document_keeps_its_text_variants_and_suggestions():
    with _client() as client:
        folder = client.post("/api/cv/folders", json={"name": "Applications"}).json()
        doc = _create(client, "sop", SOP)
        v = client.post(
            f"/api/cv/documents/{doc['id']}/versions", json={"name": "For MIT"}
        ).json()
        client.post(
            f"/api/cv/documents/{doc['id']}/suggestions",
            json={
                "version_id": v["id"],
                "suggestions": [{"find": "I want to study", "replace": "I hope to study"}],
            },
        )
        moved = client.patch(f"/api/cv/documents/{doc['id']}", json={"folder_id": folder["id"]})
        assert moved.status_code == 200, moved.text
        body = moved.json()
        assert body["folder_id"] == folder["id"]
        assert body["revision"] == doc["revision"] and body["markdown"] == SOP
        assert body["updated_at"] == doc["updated_at"]
        assert [x["id"] for x in body["versions"]] == [v["id"]]
        pending = client.get("/api/cv/suggestions", params={"version_id": v["id"]}).json()
        assert len(pending) == 1 and pending[0]["applicable"]
        listed = client.get("/api/cv/documents", params={"folder_id": folder["id"]}).json()
        assert [d["id"] for d in listed] == [doc["id"]]
        out = client.patch(f"/api/cv/documents/{doc['id']}", json={"folder_id": None}).json()
        assert out["folder_id"] is None
        missing = client.patch(f"/api/cv/documents/{doc['id']}", json={"folder_id": "nope"})
        assert missing.status_code == 404


def test_document_tools_take_a_kind():
    with _client() as client:
        cv = _create(client)
        sop = _create(client, "sop", SOP, "SOP")
    listed = _tool("list_documents", {"kind": "sop"})
    assert [d["id"] for d in listed["documents"]] == [sop["id"]]
    assert listed["documents"][0]["kind"] == "sop"
    assert "Outbox" in listed["note"]
    assert {d["id"] for d in _tool("list_documents", {})["documents"]} == {cv["id"], sop["id"]}
    read = _tool("read_document", {"document_id": sop["id"]})
    assert read["kind"] == "sop" and read["markdown"] == SOP
    wrong = _tool("read_document", {"document_id": sop["id"], "kind": "cv"})
    assert "statement of purpose" in wrong["error"]


def test_suggestions_on_a_statement_are_checked_against_the_cv_too():
    with _client() as client:
        _create(client)
        sop = _create(client, "sop", SOP)
    out = _tool(
        "suggest_changes",
        {
            "document_id": sop["id"],
            "kind": "sop",
            "suggestions": [
                # The CV says Python: not a new claim.
                {"find": "I built a gripper.", "replace": "I built a gripper in Python."},
                # Nowhere in the student's documents: flagged.
                {"find": "I want to study", "replace": "As a Nature author, I want to study"},
            ],
        },
    )
    flags = [s["new_terms"] for s in out["suggestions"]]
    assert flags[0] == [] and "nature" in flags[1] and "author" in flags[1]
    with _client() as client:
        assert client.get(f"/api/cv/documents/{sop['id']}").json()["markdown"] == SOP


def test_cv_tools_are_shims_for_cvs_only():
    with _client() as client:
        cv = _create(client, title="My CV")
        sop = _create(client, "sop", SOP)
    listed = _tool("cv_list_documents", {})
    assert [d["id"] for d in listed["documents"]] == [cv["id"]]
    assert set(listed["documents"][0]) == {"id", "title", "updated_at", "versions"}
    read = _tool("cv_read", {"document_id": cv["id"]})
    assert read == {
        "document_id": cv["id"],
        "name": "My CV",
        "truncated": False,
        "markdown": CV,
    }
    assert "error" in _tool("cv_read", {"document_id": sop["id"]})
    refused = _tool(
        "cv_suggest_changes",
        {"document_id": sop["id"], "suggestions": [{"find": "I want", "replace": "I hope"}]},
    )
    assert "error" in refused
    ok = _tool(
        "cv_suggest_changes",
        {"document_id": cv["id"], "suggestions": [{"find": "Lab tech", "replace": "Lab technician"}]},
    )
    assert ok["suggestions"][0]["applicable"]


def test_new_chats_get_the_document_tools_and_old_chats_keep_the_cv_ones():
    defs = assistant_tools.ASSISTANT_DEFINITIONS
    fresh = {d["name"] for d in assistant_tools.without_unused_legacy(defs, [])}
    assert {"list_documents", "read_document", "suggest_changes"} <= fresh
    assert not fresh & assistant_tools.LEGACY_TOOLS
    history = [{"role": "assistant", "tool_calls": [{"name": "cv_read", "arguments": {}}]}]
    old = {d["name"] for d in assistant_tools.without_unused_legacy(defs, history)}
    assert "cv_read" in old and "cv_suggest_changes" not in old


def test_the_fabrication_rule_is_in_the_generic_tool():
    spec = next(d for d in assistant_tools.ASSISTANT_DEFINITIONS if d["name"] == "suggest_changes")
    assert "never add experience" in spec["description"]
    assert "publications" in spec["description"]


def test_migration_makes_every_existing_document_a_cv():
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "043_assistant_queue")
        _run(
            _execute(
                url,
                """
                INSERT INTO users (id, email, password_hash) VALUES ('u1', 'u1@example.com', 'x');
                INSERT INTO cv_documents (id, title, format, status, size_bytes, user_id)
                VALUES ('d1', 'CV', 'md', 'ready', 0, 'u1');
                """,
            )
        )
        command.upgrade(cfg, "044_document_kinds")
        rows = _run(_fetch(url, "SELECT id, kind, folder_id FROM cv_documents"))
        assert [(r["id"], r["kind"], r["folder_id"]) for r in rows] == [("d1", "cv", None)]
        command.downgrade(cfg, "043_assistant_queue")
        rows = _run(_fetch(url, "SELECT id FROM cv_documents"))
        assert [r["id"] for r in rows] == ["d1"]
        command.upgrade(cfg, "head")

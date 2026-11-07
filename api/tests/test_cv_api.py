import asyncio
import io
import logging
import uuid

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from alembic import command
from api.assistant import tools as assistant_tools
from api.candidates.models import CandidateScore, CandidateStatus
from api.core.config import settings
from api.core.db import SessionLocal
from api.cv import claims, markdown
from api.cv import models as cv_models
from api.main import app
from api.prospects.models import Professor, Program, RunSchool, School
from api.runs.models import Run
from tests.conftest import TEST_USER_ID
from tests.cv_fixtures import corpus_rich, corpus_simple
from tests.test_migrations import _cfg, _dsn, _fetch, _run, _scratch_db

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    target = tmp_path / "cv_storage"
    monkeypatch.setattr(settings, "cv_storage_dir", str(target))
    return target


@pytest.fixture(autouse=True)
def _clean_cv():
    async def _wipe():
        async with SessionLocal() as session:
            await session.execute(delete(cv_models.CvSuggestion))
            await session.execute(delete(cv_models.CvTailoredVersion))
            await session.execute(delete(cv_models.CvDocument))
            await session.commit()

    asyncio.run(_wipe())


def _client():
    return TestClient(app)


def _upload(client, data: bytes, filename: str = "cv.docx", title: str | None = "My CV"):
    return client.post(
        "/api/cv/documents",
        files={"file": (filename, data, DOCX)},
        data={"title": title} if title else {},
    )


def _pdf(lines: list[str]) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for line in lines:
        c.drawString(72, y, line)
        y -= 16
    c.save()
    return buf.getvalue()


def _candidate() -> str:
    """A scored candidate: Prof Ada Lovelace at Analytical University."""

    async def setup():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID,
                region="Anywhere",
                field="robotics",
                degree_level="phd",
                interest_statement="robots",
                status="done",
            )
            session.add(run)
            await session.flush()
            school = School(
                user_id=TEST_USER_ID,
                name=f"Analytical University {uuid.uuid4().hex[:6]}",
                run_links=[RunSchool(run_id=run.id)],
            )
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="PhD in Engines")
            session.add(program)
            await session.flush()
            prof = Professor(user_id=TEST_USER_ID, program_id=program.id, name="Ada Lovelace")
            session.add(prof)
            await session.flush()
            cand = CandidateScore(
                user_id=TEST_USER_ID,
                run_id=run.id,
                professor_id=prof.id,
                similarity_score=0.8,
                status=CandidateStatus.scored,
            )
            session.add(cand)
            await session.commit()
            return cand.id

    return asyncio.run(setup())


def test_a_docx_becomes_a_markdown_base_cv_and_the_file_is_kept(storage_dir):
    data = corpus_simple()  # built once: zip entries carry timestamps
    with _client() as client:
        resp = _upload(client, data)
        assert resp.status_code == 200, resp.text
        doc = resp.json()
        assert doc["format"] == "docx" and doc["has_original"] and doc["revision"] == 1
        assert doc["markdown"] == (
            "## Jane Doe\n\nResearch assistant in robotics.\n\n## Experience\n\n- Lab tech, 2023-2025.\n"
        )
        original = client.get(f"/api/cv/documents/{doc['id']}/original")
        assert original.status_code == 200
        assert original.content == data
        assert "My CV.docx" in original.headers["content-disposition"]
        listed = client.get("/api/cv/documents").json()
        assert [d["id"] for d in listed] == [doc["id"]]
    assert (storage_dir / "cv" / doc["id"] / "original" / "source.docx").exists()


def test_headers_come_first_and_images_are_left_out():
    with _client() as client:
        text = _upload(client, corpus_rich()).json()["markdown"]
    assert text.startswith("Jane Doe — CV")
    assert "Mobile robotics and reinforcement learning." in text
    assert "Best paper (example.com)" in text
    assert "Open to relocation." in text
    assert "image1" not in text


def test_a_pdf_and_a_markdown_file_upload_too():
    with _client() as client:
        pdf = _upload(client, _pdf(["Jane Doe", "EDUCATION", "PhD student, 2024", "- Robot learning"]), "cv.pdf")
        assert pdf.status_code == 200, pdf.text
        text = pdf.json()["markdown"]
        assert text.startswith("# Jane Doe")
        assert "## Education" in text and "- Robot learning" in text
        md = _upload(client, b"# Jane\n\n## Skills\n\n- Python\n", "cv.md", None)
        assert md.status_code == 200
        assert md.json()["markdown"] == "# Jane\n\n## Skills\n\n- Python\n"
        assert md.json()["title"] == "cv"
        assert _upload(client, b"MZ\x90\x00", "cv.exe").status_code == 400
        assert _upload(client, b"%PDF-1.7 broken", "cv.pdf").status_code == 400


def test_a_cv_can_start_from_typed_text():
    with _client() as client:
        doc = client.post("/api/cv/documents/text", json={"title": "Typed", "markdown": "# Me\n"}).json()
        assert doc["markdown"] == "# Me\n" and not doc["has_original"]
        assert client.get(f"/api/cv/documents/{doc['id']}/original").status_code == 404


def test_saves_are_refused_when_the_text_changed_since_it_was_loaded():
    with _client() as client:
        doc = _upload(client, corpus_simple()).json()
        url = f"/api/cv/documents/{doc['id']}"
        saved = client.put(url, json={"base_revision": 1, "markdown": "# Edited\n", "title": "Renamed"})
        assert saved.status_code == 200, saved.text
        assert saved.json()["revision"] == 2 and saved.json()["title"] == "Renamed"
        stale = client.put(url, json={"base_revision": 1, "markdown": "# Lost\n"})
        assert stale.status_code == 409
        assert stale.json()["detail"]["revision"] == 2
        assert client.get(url).json()["markdown"] == "# Edited\n"


def test_a_version_tailored_for_a_professor_is_named_linked_and_reused():
    candidate_id = _candidate()
    with _client() as client:
        doc = _upload(client, corpus_simple()).json()
        url = f"/api/cv/documents/{doc['id']}/versions"
        v = client.post(url, json={"candidate_id": candidate_id}).json()
        assert v["name"] == "CV for Ada Lovelace"
        assert v["candidate_id"] == candidate_id and v["professor_name"] == "Ada Lovelace"
        assert v["target_label"].startswith("Ada Lovelace, Analytical University")
        assert v["markdown"] == doc["markdown"]
        again = client.post(url, json={"candidate_id": candidate_id}).json()
        assert again["id"] == v["id"]
        fresh = client.post(url, json={"candidate_id": candidate_id, "new": True}).json()
        assert fresh["id"] != v["id"]
        listed = client.get(f"/api/cv/documents/{doc['id']}").json()
        assert {x["id"] for x in listed["versions"]} == {v["id"], fresh["id"]}
        renamed = client.put(
            f"/api/cv/versions/{v['id']}", json={"base_revision": 1, "title": "CV for computing"}
        ).json()
        assert renamed["name"] == "CV for computing" and renamed["revision"] == 2
        assert client.delete(f"/api/cv/versions/{fresh['id']}").status_code == 200
        assert client.get(f"/api/cv/versions/{fresh['id']}").status_code == 404


def test_an_unsaved_variant_is_created_with_its_edited_text_in_one_call():
    candidate_id = _candidate()
    with _client() as client:
        doc = _upload(client, corpus_simple()).json()
        url = f"/api/cv/documents/{doc['id']}/versions"
        first = client.post(url, json={"candidate_id": candidate_id}).json()
        edited = "## Jane Doe\n\nRobotics research assistant.\n"
        saved = client.post(
            url,
            json={"candidate_id": candidate_id, "name": "CV for Ada", "markdown": edited, "new": True},
        )
        assert saved.status_code == 200, saved.text
        v = saved.json()
        assert v["id"] != first["id"] and v["name"] == "CV for Ada"
        assert v["markdown"] == edited and v["revision"] == 1
        assert v["professor_name"] == "Ada Lovelace"
        assert client.get(f"/api/cv/documents/{doc['id']}").json()["markdown"] == doc["markdown"]
        empty = client.post(url, json={"name": "Blank", "markdown": ""}).json()
        assert empty["markdown"] == ""
        too_long = client.post(url, json={"name": "Huge", "markdown": "x" * 60_001})
        assert too_long.status_code == 422


def test_the_cv_list_nests_each_cvs_versions():
    with _client() as client:
        a = _upload(client, corpus_simple(), title="CV A").json()
        b = client.post("/api/cv/documents/text", json={"title": "CV B", "markdown": "# B\n"}).json()
        va = client.post(f"/api/cv/documents/{a['id']}/versions", json={"name": "For RL"}).json()
        listed = {d["id"]: d for d in client.get("/api/cv/documents").json()}
        assert listed[a["id"]]["version_count"] == 1
        assert [v["id"] for v in listed[a["id"]]["versions"]] == [va["id"]]
        assert listed[a["id"]]["versions"][0]["name"] == "For RL"
        assert "markdown" not in listed[a["id"]]["versions"][0]
        assert listed[b["id"]]["versions"] == [] and listed[b["id"]]["version_count"] == 0


def _version(client) -> tuple[dict, dict]:
    doc = _upload(client, corpus_simple()).json()
    v = client.post(f"/api/cv/documents/{doc['id']}/versions", json={"name": "CV for RL"}).json()
    return doc, v


def _suggest(client, doc, v, find, replace, rationale="Sharper"):
    resp = client.post(
        f"/api/cv/documents/{doc['id']}/suggestions",
        json={"version_id": v["id"], "suggestions": [{"find": find, "replace": replace, "rationale": rationale}]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()[0]


def test_accepting_a_suggestion_changes_only_the_version():
    with _client() as client:
        doc, v = _version(client)
        s = _suggest(client, doc, v, "Research assistant in robotics.", "Robotics research assistant.")
        assert s["status"] == "pending" and s["applicable"] and s["claim_check"]["passed"]
        accepted = client.post(f"/api/cv/suggestions/{s['id']}/accept", json={})
        assert accepted.status_code == 200, accepted.text
        body = accepted.json()
        assert "Robotics research assistant." in body["markdown"] and body["revision"] == 2
        assert body["suggestion"]["status"] == "accepted"
        assert client.get(f"/api/cv/versions/{v['id']}").json()["markdown"] == body["markdown"]
        assert client.get(f"/api/cv/documents/{doc['id']}").json()["markdown"] == doc["markdown"]
        assert client.post(f"/api/cv/suggestions/{s['id']}/accept", json={}).status_code == 409


def test_new_terms_are_flagged_and_need_confirming():
    with _client() as client:
        doc, v = _version(client)
        s = _suggest(client, doc, v, "Lab tech, 2023-2025.", "Lab tech at NASA, 2023-2025.")
        assert s["claim_check"] == {"passed": False, "new_terms": ["nasa"]}
        refused = client.post(f"/api/cv/suggestions/{s['id']}/accept", json={})
        assert refused.status_code == 409
        assert refused.json()["detail"]["new_terms"] == ["nasa"]
        ok = client.post(f"/api/cv/suggestions/{s['id']}/accept", json={"confirm_new_terms": True})
        assert ok.status_code == 200
        assert "NASA" in ok.json()["markdown"]


def test_an_edited_suggestion_is_checked_again_and_applied_as_edited():
    with _client() as client:
        doc, v = _version(client)
        s = _suggest(client, doc, v, "Lab tech, 2023-2025.", "Lab technician, 2023-2025.")
        edited = client.post(
            f"/api/cv/suggestions/{s['id']}/accept", json={"replace": "Lab tech at Google, 2023-2025."}
        )
        assert edited.status_code == 409 and edited.json()["detail"]["new_terms"] == ["google"]
        edited = client.post(
            f"/api/cv/suggestions/{s['id']}/accept", json={"replace": "Robotics lab tech, 2023-2025."}
        )
        assert edited.status_code == 200
        assert "- Robotics lab tech, 2023-2025." in edited.json()["markdown"]
        listed = client.get("/api/cv/suggestions", params={"version_id": v["id"]}).json()
        assert listed[0]["replace"] == "Robotics lab tech, 2023-2025."


def test_a_suggestion_whose_text_was_edited_goes_stale():
    with _client() as client:
        doc, v = _version(client)
        s = _suggest(client, doc, v, "Lab tech, 2023-2025.", "Lab technician, 2023-2025.")
        client.put(f"/api/cv/versions/{v['id']}", json={"base_revision": 1, "markdown": "# Rewritten\n"})
        listed = client.get("/api/cv/suggestions", params={"version_id": v["id"]}).json()
        assert listed[0]["applicable"] is False
        stale = client.post(f"/api/cv/suggestions/{s['id']}/accept", json={})
        assert stale.status_code == 409 and stale.json()["detail"]["reason"] == "stale"
        assert client.get("/api/cv/suggestions", params={"version_id": v["id"]}).json()[0]["status"] == "stale"


def test_a_quote_with_different_line_breaks_still_applies():
    with _client() as client:
        doc, v = _version(client)
        s = _suggest(client, doc, v, "Research   assistant\nin robotics.", "Robotics research assistant.")
        assert s["applicable"]
        assert client.post(f"/api/cv/suggestions/{s['id']}/accept", json={}).status_code == 200


def test_rejecting_leaves_the_text_alone():
    with _client() as client:
        doc, v = _version(client)
        s = _suggest(client, doc, v, "Lab tech, 2023-2025.", "Lab technician.")
        rejected = client.post(f"/api/cv/suggestions/{s['id']}/reject")
        assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
        assert client.get(f"/api/cv/versions/{v['id']}").json()["markdown"] == doc["markdown"]


def test_exports_as_markdown_text_and_pdf():
    with _client() as client:
        doc, v = _version(client)
        md = client.get(f"/api/cv/versions/{v['id']}/export", params={"format": "md"})
        assert md.status_code == 200 and md.text == doc["markdown"]
        assert 'filename="CV for RL.md"' in md.headers["content-disposition"]
        txt = client.get(f"/api/cv/documents/{doc['id']}/export", params={"format": "txt"}).text
        assert txt == "Jane Doe\n\nResearch assistant in robotics.\n\nExperience\n\n• Lab tech, 2023-2025.\n"
        pdf = client.get(f"/api/cv/documents/{doc['id']}/export", params={"format": "pdf"})
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        assert pdf.headers["content-type"] == "application/pdf"
        word = client.get(f"/api/cv/versions/{v['id']}/export", params={"format": "docx"})
        assert word.status_code == 200 and word.content.startswith(b"PK")
        assert word.headers["content-type"] == DOCX
        assert 'filename="CV for RL.docx"' in word.headers["content-disposition"]
        from docx import Document

        texts = [p.text for p in Document(io.BytesIO(word.content)).paragraphs]
        assert "Jane Doe" in texts and "Lab tech, 2023-2025." in texts


def test_layout_reports_where_pdf_pages_start():
    lines = ["# Jane Doe", ""]
    for s in range(8):
        lines += [f"## Section {s}", ""] + [f"- Item {s}.{i}, a line long enough to wrap once on the page." for i in range(12)] + [""]
    with _client() as client:
        resp = client.post("/api/cv/layout", json={"markdown": "\n".join(lines)})
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert out["pages"] >= 2 and len(out["breaks"]) == out["pages"] - 1
        assert all(lines[b["line"] - 1].strip() for b in out["breaks"])
        assert client.post("/api/cv/layout", json={"markdown": "# Short"}).json() == {"pages": 1, "breaks": []}
        too_long = client.post("/api/cv/layout", json={"markdown": "x" * 60_001})
        assert too_long.status_code == 422


def test_deleting_a_cv_removes_its_versions_suggestions_and_file(storage_dir):
    with _client() as client:
        doc, v = _version(client)
        _suggest(client, doc, v, "Lab tech, 2023-2025.", "Lab technician.")
        assert client.delete(f"/api/cv/documents/{doc['id']}").status_code == 200
        assert client.get(f"/api/cv/documents/{doc['id']}").status_code == 404
        assert client.get(f"/api/cv/versions/{v['id']}").status_code == 404

    async def left():
        async with SessionLocal() as session:
            return (await session.execute(select(cv_models.CvSuggestion))).scalars().all()

    assert asyncio.run(left()) == []
    assert not (storage_dir / "cv" / doc["id"]).exists()


def test_gradis_reads_a_cv_and_suggests_changes_for_review():
    with _client() as client:
        doc, v = _version(client)

    async def go():
        async with SessionLocal() as session:
            read = await assistant_tools.HANDLERS["cv_read"](
                {"document_id": doc["id"], "version_id": v["id"]}, session, TEST_USER_ID
            )
            stored = await assistant_tools.HANDLERS["cv_suggest_changes"](
                {
                    "document_id": doc["id"],
                    "version_id": v["id"],
                    "suggestions": [
                        {"find": "Lab tech, 2023-2025.", "replace": "Robotics lab tech, 2023-2025."},
                        {"find": "Not in the CV", "replace": "x"},
                    ],
                },
                session,
                TEST_USER_ID,
            )
            listed = await assistant_tools.HANDLERS["cv_list_documents"]({}, session, TEST_USER_ID)
            return read, stored, listed

    read, stored, listed = asyncio.run(go())
    assert read["markdown"] == doc["markdown"] and read["version_id"] == v["id"]
    assert [s["applicable"] for s in stored["suggestions"]] == [True, False]
    assert listed["documents"][0]["versions"][0]["name"] == "CV for RL"
    with _client() as client:
        pending = client.get("/api/cv/suggestions", params={"version_id": v["id"], "status": "pending"}).json()
        assert len(pending) == 1 and {p["created_by"] for p in pending} == {"assistant"}
        assert client.get(f"/api/cv/versions/{v['id']}").json()["markdown"] == doc["markdown"]


def test_claim_check_is_against_the_base_cv():
    base = "Research assistant in robotics, 2023."
    assert claims.check_new_terms(base, "Robotics research assistant (2023)") == {"passed": True, "new_terms": []}
    assert claims.check_new_terms(base, "Won the 2024 Turing award")["new_terms"] == ["2024", "award", "turing", "won"]


def test_plain_text_drops_the_marks():
    text = markdown.to_plain_text("# Jane\n\n**Bold** and _it_, [site](https://x.org)\n\n- one\n  - two\n")
    assert text == "Jane\n\nBold and it, site (https://x.org)\n\n• one\n  • two\n"


def test_sections_split_on_headings():
    md = "# Jane\n\nintro\n\n## Research\n\nRobots.\n\n## Skills\n\n- Python\n"
    assert markdown.sections(md) == [("Jane", "intro"), ("Research", "Robots."), ("Skills", "- Python")]


def test_pdf_lines_become_headings_bullets_and_paragraphs():
    pages = ["Jane Doe\nEXPERIENCE\n\uf0b7 Built a robot arm\n  with force control\nPlain line\n2"]
    assert markdown.pdf_text_to_markdown(pages) == (
        "# Jane Doe\n\n## Experience\n\n- Built a robot arm with force control\nPlain line\n"
    )


def test_tabs_become_separators_and_section_words_headings():
    units = [
        {"type": "paragraph", "text": "Experience", "source": {"part": "word/document.xml"}},
        {"type": "paragraph", "text": "Engineer\tAcme\t2021", "source": {"part": "word/document.xml"}},
        {"type": "paragraph", "text": "3", "source": {"part": "word/footer1.xml"}},
    ]
    assert markdown.units_to_markdown(units) == "## Experience\n\nEngineer — Acme — 2021\n"


async def _execute(url: str, sql: str) -> None:
    conn = await asyncpg.connect(_dsn(url))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def test_migration_converts_each_documents_latest_version(caplog):
    ir = (
        '{"units": ['
        '{"id": "u1", "type": "heading", "text": "Jane Doe", "source": {"part": "word/document.xml", "path": "p0", "fingerprint": "f"}},'
        '{"id": "u2", "type": "bullet", "text": "Robot learning", "source": {"part": "word/document.xml", "path": "p1", "fingerprint": "f"}}'
        "]}"
    )
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "039_run_schools")
        _run(
            _execute(
                url,
                f"""
                INSERT INTO users (id, email, password_hash) VALUES ('u1', 'u1@example.com', 'x');
                INSERT INTO cv_documents (id, title, format, status, original_sha256, size_bytes,
                    fidelity_class, head_version_id, redo_stack, user_id)
                VALUES ('d1', 'CV', 'docx', 'ready', 'abc', 10, 'high', 'v2', '[]', 'u1'),
                       ('d2', 'Empty', 'docx', 'ready', 'def', 10, 'high', NULL, '[]', 'u1');
                INSERT INTO cv_versions (id, document_id, branch_id, kind, file_path, ir_json,
                    operations_json, quality_report_json, label, created_by, user_id)
                VALUES ('v1', 'd1', 'main', 'original', '/x', '{{"units": []}}', '[]', '{{}}', 'upload', 'user', 'u1'),
                       ('v2', 'd1', 'main', 'checkpoint', '/y', '{ir}', '[]', '{{}}', 'edit', 'user', 'u1');
                """,
            )
        )
        with caplog.at_level(logging.INFO, logger="alembic.runtime.migration"):
            command.upgrade(cfg, "head")
        rows = _run(_fetch(url, "SELECT id, markdown, source_path, revision FROM cv_documents ORDER BY id"))
        assert rows[0]["markdown"] == "## Jane Doe\n\n- Robot learning\n"
        assert rows[0]["source_path"] == "cv/d1/versions/v2/document.docx"
        assert rows[0]["revision"] == 1
        assert rows[1]["markdown"] == "" and rows[1]["source_path"] == "cv/d2/original/source.docx"
        assert "converted 2 CV document(s)" in caplog.text
        tables = {r["table_name"] for r in _run(_fetch(url, "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))}
        assert {"cv_tailored_versions", "cv_suggestions"} <= tables
        assert not {"cv_versions", "cv_branches", "cv_proposals"} & tables
        command.downgrade(cfg, "039_run_schools")
        command.upgrade(cfg, "head")

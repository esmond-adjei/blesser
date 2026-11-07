import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from alembic import command
from api.applications.models import Application
from api.assistant import tools as assistant_tools
from api.core.config import settings
from api.core.db import SessionLocal
from api.cv import checks as cv_checks
from api.cv import models as cv_models
from api.cv import suggest
from api.main import app
from tests.conftest import TEST_USER_ID
from tests.test_cv_api import _execute
from tests.test_cv_suggest import _ask, _Fake
from tests.test_migrations import _cfg, _fetch, _run, _scratch_db

CV = (
    "# Jane Doe\n\n## Experience\n\n"
    "- Lab tech at the Soft Robotics Lab, 2023-2025.\n"
    "- BSc, University of Ghana, 2019-2023.\n"
)
SOP = (
    "# Statement of purpose\n\n"
    "I want to study soft robotics.\n\n"
    "At the Soft Robotics Lab I built a gripper.\n"
)


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cv_storage_dir", str(tmp_path / "cv_storage"))


@pytest.fixture(autouse=True)
def _clean():
    async def _wipe():
        async with SessionLocal() as session:
            for m in (
                cv_models.CvSuggestion,
                cv_models.CvTailoredVersion,
                cv_models.CvDocument,
                Application,
            ):
                await session.execute(delete(m))
            await session.commit()

    asyncio.run(_wipe())


def _client():
    return TestClient(app)


def _create(client, kind="sop", markdown=SOP, title="SOP"):
    r = client.post("/api/cv/documents/text", json={"title": title, "markdown": markdown, "kind": kind})
    assert r.status_code == 200, r.text
    return r.json()


def _limit(client, doc, **limits):
    r = client.patch(f"/api/cv/documents/{doc['id']}", json=limits)
    assert r.status_code == 200, r.text
    return r.json()


def _suggest(client, doc, pairs, version=None):
    r = client.post(
        f"/api/cv/documents/{doc['id']}/suggestions",
        json={
            "version_id": version["id"] if version else None,
            "suggestions": [{"find": f, "replace": rep} for f, rep in pairs],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _tool(name, args):
    async def go():
        async with SessionLocal() as session:
            return await assistant_tools.HANDLERS[name](dict(args), session, TEST_USER_ID)

    return asyncio.run(go())


def test_word_count_matches_the_editor():
    # Marks don't count; a bullet or a lone dash isn't a word.
    assert cv_checks.word_count("# My **bold** title\n\n- one [link](http://x.y) — two\n") == 7


def test_limits_are_set_without_touching_the_text():
    with _client() as client:
        doc = _create(client)
        out = _limit(client, doc, word_limit=500, page_limit=2)
        assert (out["word_limit"], out["page_limit"]) == (500, 2)
        assert out["revision"] == doc["revision"] and out["markdown"] == SOP
        assert out["updated_at"] == doc["updated_at"]
        out = _limit(client, doc, page_limit=None)
        assert (out["word_limit"], out["page_limit"]) == (500, None)
        for bad in ({"word_limit": 0}, {"page_limit": 1000}):
            assert client.patch(f"/api/cv/documents/{doc['id']}", json=bad).status_code == 422


def test_a_version_has_its_own_limits_or_its_bases():
    with _client() as client:
        doc = _limit(client, _create(client), word_limit=900)
        v = client.post(f"/api/cv/documents/{doc['id']}/versions", json={"name": "For ETH"}).json()
        assert v["word_limit"] is None and v["base_word_limit"] == 900
        r = client.patch(f"/api/cv/versions/{v['id']}", json={"word_limit": 10})
        assert r.status_code == 200, r.text
        assert r.json()["word_limit"] == 10 and r.json()["revision"] == v["revision"]
        [s] = _suggest(
            client, doc, [("I want to study soft robotics.", "I want to study soft robotics and tactile sensing.")], v
        )
        assert s["limit_check"]["word_limit"] == 10 and s["limit_check"]["over_limit"]


def test_growth_past_the_limit_is_flagged():
    with _client() as client:
        doc = _create(client)
        words = cv_checks.word_count(SOP)
        _limit(client, doc, word_limit=words + 2)
        [s] = _suggest(
            client, doc, [("I want to study soft robotics.", "I want to study soft robotics and how hands feel things.")]
        )
        check = s["limit_check"]
        assert check["over_limit"] and not check["offset"]
        assert check["delta"] == 5 and check["words_after"] == words + 5


def test_growth_with_a_matching_cut_in_the_same_batch_is_not_flagged():
    with _client() as client:
        doc = _create(client)
        words = cv_checks.word_count(SOP)
        _limit(client, doc, word_limit=words + 2)
        grow, cut = _suggest(
            client,
            doc,
            [
                ("I want to study soft robotics.", "I want to study soft robotics and how hands feel things."),
                ("At the Soft Robotics Lab I built a gripper.", "I built a gripper."),
            ],
        )
        assert grow["limit_check"]["offset"] and not grow["limit_check"]["over_limit"]
        assert grow["limit_check"]["words_after"] <= words + 2
        assert cut["limit_check"]["delta"] < 0 and not cut["limit_check"]["over_limit"]


def test_without_a_limit_nothing_is_checked():
    with _client() as client:
        doc = _create(client)
        [s] = _suggest(client, doc, [("I want to study soft robotics.", "I want to study soft robotics a lot.")])
        assert s["limit_check"] is None


def test_a_page_limit_uses_the_pdf_layout():
    with _client() as client:
        doc = _create(client)
        _limit(client, doc, page_limit=1)
        long = "\n\n".join(["I built grippers in the lab, and tested them on fruit."] * 120)
        [s] = _suggest(client, doc, [("At the Soft Robotics Lab I built a gripper.", long)])
        assert s["limit_check"]["pages_after"] > 1 and s["limit_check"]["over_limit"]


def test_the_assistant_hears_about_the_limit():
    with _client() as client:
        doc = _create(client)
        _limit(client, doc, word_limit=cv_checks.word_count(SOP))
    read = _tool("read_document", {"document_id": doc["id"]})
    assert read["limits"] == {"word_limit": cv_checks.word_count(SOP), "page_limit": None, "words": cv_checks.word_count(SOP)}
    out = _tool(
        "suggest_changes",
        {
            "document_id": doc["id"],
            "suggestions": [{"find": "I want to study soft robotics.", "replace": "I want to study soft robotics deeply."}],
        },
    )
    assert out["suggestions"][0]["over_limit"]
    assert "limit" in out["note"] and "cut" in out["note"]


def test_a_selection_suggestion_is_told_the_budget(monkeypatch):
    fake = _Fake('{"replace": "I study soft robotics.", "rationale": "Shorter."}')
    monkeypatch.setattr(suggest, "get_provider", lambda **_: fake)
    with _client() as client:
        doc = _create(client)
        doc = _limit(client, doc, word_limit=cv_checks.word_count(SOP))
        start = SOP.index("I want")
        r = _ask(client, doc, SOP, start, start + len("I want to study soft robotics."))
        assert r.status_code == 200, r.text
        prompt = fake.calls[0]["messages"][0]["content"]
        assert f"{cv_checks.word_count(SOP)}-word limit" in prompt and "Don't make the passage longer" in prompt


def test_a_statement_cannot_take_in_a_publication_the_student_never_had():
    with _client() as client:
        _create(client, "cv", CV, "CV")
        doc = _limit(client, _create(client), word_limit=200)
        [s] = _suggest(
            client,
            doc,
            [("At the Soft Robotics Lab I built a gripper.", "At the Soft Robotics Lab I built a gripper, published in Nature.")],
        )
        assert "nature" in s["claim_check"]["new_terms"]
        refused = client.post(f"/api/cv/suggestions/{s['id']}/accept", json={})
        assert refused.status_code in (400, 409, 422)
        assert client.get(f"/api/cv/documents/{doc['id']}").json()["markdown"] == SOP


def test_placeholders_are_found_in_any_kind():
    text = "# CV\n\n- TODO: dates\n- Improved accuracy by [X%] at [insert company].\n- See [my site](http://x).\n- lorem ipsum\n"
    found = [f["quote"] for f in cv_checks.run_checks(text, "cv")]
    assert found == ["TODO", "[X%]", "[insert company]", "lorem ipsum"]


def test_a_statement_is_checked_against_the_cv_and_the_targets():
    with _client() as client:
        _create(client, "cv", CV, "CV")
        text = (
            "# Statement of purpose\n\n"
            "At the Soft Robotics Lab I built a gripper in 2021.\n"
            "I studied at the Univrsity of Ghana.\n"
            "I want to work with Professor Ada Lovelace and Dr. Zed Quillfeather.\n"
        )
        doc = _create(client, markdown=text)

        async def add_target():
            async with SessionLocal() as session:
                session.add(
                    Application(
                        user_id=TEST_USER_ID,
                        school="ETH Zurich",
                        professors=[{"name": "Ada Lovelace"}],
                    )
                )
                await session.commit()

        asyncio.run(add_target())
        r = client.get(f"/api/cv/documents/{doc['id']}/checks")
        assert r.status_code == 200, r.text
        findings = {f["kind"]: f for f in r.json()["findings"]}
        assert set(findings) == {"date_mismatch", "name_mismatch", "unknown_faculty"}
        assert "2023–2025" in findings["date_mismatch"]["message"]
        assert findings["name_mismatch"]["quote"] == "Univrsity of Ghana"
        assert findings["unknown_faculty"]["quote"] == "Dr. Zed Quillfeather"
        lines = text.splitlines()
        assert all(f["quote"] in lines[f["line"]] for f in r.json()["findings"])
        assert client.get(f"/api/cv/documents/{doc['id']}").json()["revision"] == doc["revision"]
    read = _tool("read_document", {"document_id": doc["id"]})
    assert {c["kind"] for c in read["checks"]} == set(findings)


def test_a_cv_is_only_checked_for_placeholders():
    with _client() as client:
        doc = _create(client, "cv", CV + "- Worked with Dr. Nobody Known in 2010 at the Soft Robotics Lab.\n", "CV")
        assert client.get(f"/api/cv/documents/{doc['id']}/checks").json()["findings"] == []


def test_a_version_is_checked_on_its_own_text():
    with _client() as client:
        doc = _create(client)
        v = client.post(f"/api/cv/documents/{doc['id']}/versions", json={"name": "For ETH"}).json()
        client.put(
            f"/api/cv/versions/{v['id']}",
            json={"base_revision": v["revision"], "markdown": SOP + "\nTBD: why ETH.\n"},
        )
        r = client.get(f"/api/cv/documents/{doc['id']}/checks", params={"version_id": v["id"]})
        assert [f["quote"] for f in r.json()["findings"]] == ["TBD"]
        assert client.get(f"/api/cv/documents/{doc['id']}/checks").json()["findings"] == []


def test_migration_adds_limits_and_drops_them_again():
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "045_fork_lineage")
        _run(
            _execute(
                url,
                """
                INSERT INTO users (id, email, password_hash) VALUES ('u1', 'u1@example.com', 'x');
                INSERT INTO cv_documents (id, title, format, status, size_bytes, user_id, markdown, revision)
                VALUES ('d1', 'SOP', 'md', 'ready', 0, 'u1', '# SOP', 1);
                """,
            )
        )
        command.upgrade(cfg, "046_document_limits")
        [row] = _run(_fetch(url, "SELECT word_limit, page_limit FROM cv_documents"))
        assert row["word_limit"] is None and row["page_limit"] is None
        command.downgrade(cfg, "045_fork_lineage")
        cols = _run(
            _fetch(
                url,
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'cv_documents'",
            )
        )
        assert "word_limit" not in {c["column_name"] for c in cols}
        command.upgrade(cfg, "head")

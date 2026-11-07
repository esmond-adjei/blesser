import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from alembic import command
from api.assistant import tools as assistant_tools
from api.core.config import settings
from api.core.db import SessionLocal
from api.cv import models as cv_models
from api.cv import service as cv_service
from api.cv import suggest
from api.main import app
from tests.conftest import TEST_USER_ID
from tests.test_cv_api import _execute
from tests.test_cv_suggest import _Fake
from tests.test_migrations import _cfg, _fetch, _run, _scratch_db

SOP = (
    "# Statement of purpose\n\n"
    "I want to study soft robotics.\n\n"
    "At the Soft Robotics Lab I built a gripper in Python.\n\n"
    "I ran 120 grasping trials.\n"
)


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cv_storage_dir", str(tmp_path / "cv_storage"))


@pytest.fixture(autouse=True)
def _clean():
    async def _wipe():
        async with SessionLocal() as session:
            for m in (cv_models.CvSuggestion, cv_models.CvTailoredVersion, cv_models.CvDocument):
                await session.execute(delete(m))
            await session.commit()

    asyncio.run(_wipe())


def _client():
    return TestClient(app)


def _sop(client, markdown=SOP):
    r = client.post(
        "/api/cv/documents/text", json={"title": "SOP", "markdown": markdown, "kind": "sop"}
    )
    assert r.status_code == 200, r.text
    return r.json()


def _fork(client, doc, name="SOP for MIT"):
    r = client.post(f"/api/cv/documents/{doc['id']}/versions", json={"name": name})
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


def _accept(client, s, **body):
    # These tests are about where text goes, not about new words.
    return client.post(
        f"/api/cv/suggestions/{s['id']}/accept", json={"confirm_new_terms": True, **body}
    )


def _listed(client, version=None, doc=None):
    params = {"version_id": version["id"]} if version else {"document_id": doc["id"], "base_only": True}
    return {s["id"]: s for s in client.get("/api/cv/suggestions", params=params).json()}


def test_a_suggestion_on_a_fork_leaves_the_base_unchanged():
    with _client() as client:
        base = _sop(client)
        v = _fork(client, base)
        [s] = _suggest(client, base, [("I want to study", "I hope to study")], v)
        assert _accept(client, s).status_code == 200
        assert "I hope to study" in client.get(f"/api/cv/versions/{v['id']}").json()["markdown"]
        assert client.get(f"/api/cv/documents/{base['id']}").json()["markdown"] == SOP


def test_a_rejected_suggestion_is_recorded():
    with _client() as client:
        base = _sop(client)
        [s] = _suggest(client, base, [("I want to study", "I hope to study")])
        r = client.post(f"/api/cv/suggestions/{s['id']}/reject")
        assert r.status_code == 200
        listed = _listed(client, doc=base)[s["id"]]
        assert listed["status"] == "rejected" and listed["resolved_at"]
        assert client.get(f"/api/cv/documents/{base['id']}").json()["markdown"] == SOP


def test_removing_a_suggestions_text_makes_it_stale_and_nothing_is_applied():
    with _client() as client:
        base = _sop(client)
        [s] = _suggest(client, base, [("I ran 120 grasping trials.", "I ran 120 trials.")])
        # The student rewrites that sentence by hand.
        edited = SOP.replace("I ran 120 grasping trials.", "I ran grasping trials.")
        client.put(
            f"/api/cv/documents/{base['id']}",
            json={"base_revision": base["revision"], "markdown": edited},
        )
        assert _listed(client, doc=base)[s["id"]]["applicable"] is False
        r = _accept(client, s)
        assert r.status_code == 409 and r.json()["detail"]["reason"] == "stale"
        assert _listed(client, doc=base)[s["id"]]["status"] == "stale"
        assert client.get(f"/api/cv/documents/{base['id']}").json()["markdown"] == edited


def test_a_quote_that_only_matches_loosely_is_never_applied():
    with _client() as client:
        base = _sop(client)
        [s] = _suggest(client, base, [("I ran 120 grasping trials.", "I ran 120 trials.")])
        # Same words, different spacing: no longer the exact text.
        loose = SOP.replace("I ran 120 grasping trials.", "I ran 120  grasping\ntrials.")
        client.put(
            f"/api/cv/documents/{base['id']}",
            json={"base_revision": base["revision"], "markdown": loose},
        )
        r = _accept(client, s)
        assert r.status_code == 409 and r.json()["detail"]["reason"] == "stale"
        assert client.get(f"/api/cv/documents/{base['id']}").json()["markdown"] == loose


def test_a_reflowed_quote_is_stored_as_the_exact_text_it_stands_for():
    with _client() as client:
        base = _sop(client)
        [s] = _suggest(client, base, [("I ran 120\ngrasping   trials.", "I ran 120 trials.")])
        assert s["find"] == "I ran 120 grasping trials." and s["applicable"]
        bad = client.post(
            f"/api/cv/documents/{base['id']}/suggestions",
            json={"suggestions": [{"find": "Not in the text", "replace": "x"}]},
        )
        assert bad.status_code == 400


def test_accepting_one_suggestion_makes_an_overlapping_one_stale():
    with _client() as client:
        base = _sop(client)
        first, overlapping, elsewhere = _suggest(
            client,
            base,
            [
                ("I built a gripper in Python.", "I built a soft gripper in Python."),
                ("a gripper in Python", "a Python gripper"),
                ("I want to study", "I hope to study"),
            ],
        )
        assert _accept(client, first).status_code == 200
        listed = _listed(client, doc=base)
        assert listed[overlapping["id"]]["status"] == "stale"
        assert listed[overlapping["id"]]["applicable"] is False
        assert listed[elsewhere["id"]]["status"] == "pending" and listed[elsewhere["id"]]["applicable"]
        assert _accept(client, overlapping).status_code == 409
        assert _accept(client, elsewhere).status_code == 200


def test_a_suggestion_whose_quote_now_appears_twice_goes_stale():
    with _client() as client:
        base = _sop(client)
        trials, copy = _suggest(
            client,
            base,
            [
                ("I ran 120 grasping trials.", "I ran trials."),
                ("I want to study soft robotics.", "I want to study soft robotics. I ran 120 grasping trials."),
            ],
        )
        assert _accept(client, copy).status_code == 200
        # They didn't overlap, but its quote is now in the text twice.
        assert _listed(client, doc=base)[trials["id"]]["status"] == "stale"


def test_a_stale_suggestion_can_be_dismissed():
    with _client() as client:
        base = _sop(client)
        a, b = _suggest(
            client, base, [("I built a gripper", "I built a soft gripper"), ("a gripper in", "one gripper in")]
        )
        _accept(client, a)
        r = client.post(f"/api/cv/suggestions/{b['id']}/reject")
        assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_the_assistant_never_stores_a_quote_that_isnt_in_the_text():
    with _client() as client:
        base = _sop(client)

    async def go():
        async with SessionLocal() as session:
            return await assistant_tools.HANDLERS["suggest_changes"](
                {
                    "document_id": base["id"],
                    "suggestions": [
                        {"find": "I want to study", "replace": "I hope to study"},
                        {"find": "Nowhere in it", "replace": "x"},
                    ],
                },
                session,
                TEST_USER_ID,
            )

    out = asyncio.run(go())
    assert out["suggestions"][0]["applicable"] is True
    assert out["suggestions"][1] == {"id": None, "applicable": False, "stored": False, "find": "Nowhere in it"}
    with _client() as client:
        assert len(_listed(client, doc=base)) == 1


def test_a_stale_suggestion_can_be_asked_for_again(monkeypatch):
    fake = _Fake('{"replace": "At the Soft Robotics Lab I built a soft gripper in Python and C.", "rationale": "Same change."}')
    monkeypatch.setattr(suggest, "get_provider", lambda **_: fake)
    with _client() as client:
        base = _sop(client)
        [s] = _suggest(
            client, base, [("At the Soft Robotics Lab I built a gripper in Python.", "At the Soft Robotics Lab I built a soft gripper in Python.")]
        )
        edited = SOP.replace("in Python.", "in Python and C.")
        client.put(
            f"/api/cv/documents/{base['id']}", json={"base_revision": 1, "markdown": edited}
        )
        r = client.post(f"/api/cv/suggestions/{s['id']}/refresh", json={})
        assert r.status_code == 200, r.text
        [fresh] = r.json()
        assert fresh["find"] == "At the Soft Robotics Lab I built a gripper in Python and C."
        assert fresh["applicable"] and fresh["status"] == "pending"
        prompt = fake.calls[0]["messages"][0]["content"]
        assert "in Python and C." in prompt and "built a soft gripper in Python." in prompt
        old = _listed(client, doc=base)[s["id"]]
        assert old["status"] == "stale" and old["superseded_by"] == fresh["id"]
        assert client.get(f"/api/cv/documents/{base['id']}").json()["markdown"] == edited
        assert client.post(f"/api/cv/suggestions/{s['id']}/refresh", json={}).status_code == 409


def test_asking_again_when_the_passage_is_gone(monkeypatch):
    fake = _Fake()
    monkeypatch.setattr(suggest, "get_provider", lambda **_: fake)
    with _client() as client:
        base = _sop(client)
        [s] = _suggest(client, base, [("I ran 120 grasping trials.", "I ran 120 trials.")])
        client.put(
            f"/api/cv/documents/{base['id']}",
            json={"base_revision": 1, "markdown": "# Statement of purpose\n\nShort now.\n"},
        )
        r = client.post(f"/api/cv/suggestions/{s['id']}/refresh", json={})
        assert r.status_code == 409 and r.json()["detail"]["reason"] == "gone"
        assert fake.calls == []


def test_closest_passage_picks_the_edited_lines():
    text = "# A\n\nFirst line here.\nSecond line, edited a bit.\n\nThird.\n"
    span = suggest.closest_passage(text, "Second line, edited.")
    assert span is not None and text[span[0] : span[1]] == "Second line, edited a bit."
    assert suggest.closest_passage(text, "Something else entirely different") is None


def test_editing_the_base_flags_the_variant_and_leaves_it_untouched():
    with _client() as client:
        base = _sop(client)
        v = _fork(client, base)
        assert v["forked_from_revision"] == base["revision"] and v["base_updated"] is False
        tailored = SOP.replace("I want to study soft robotics.", "I want to study soft robotics at MIT.")
        client.put(f"/api/cv/versions/{v['id']}", json={"base_revision": 1, "markdown": tailored})
        new_base = SOP.replace("I ran 120 grasping trials.", "I ran 150 grasping trials.").replace(
            "I want to study soft robotics.", "I want to study soft robots."
        )
        client.put(f"/api/cv/documents/{base['id']}", json={"base_revision": 1, "markdown": new_base})

        got = client.get(f"/api/cv/versions/{v['id']}").json()
        assert got["base_updated"] is True and got["markdown"] == tailored
        listed = client.get("/api/cv/documents").json()[0]["versions"][0]
        assert listed["base_updated"] is True

        changes = client.get(f"/api/cv/versions/{v['id']}/base-changes").json()
        assert changes["base_updated"] and changes["forked_from_revision"] == 1
        by_after = {c["after"].strip(): c for c in changes["changes"]}
        assert by_after["I ran 150 grasping trials."]["applicable"] is True
        assert by_after["I want to study soft robots."]["applicable"] is False
        assert client.get(f"/api/cv/versions/{v['id']}").json()["markdown"] == tailored

        synced = client.post(f"/api/cv/versions/{v['id']}/sync").json()
        assert synced["skipped"] == 1 and len(synced["suggestions"]) == 1
        s = synced["suggestions"][0]
        assert s["created_by"] == "sync" and s["claim_check"]["passed"]
        after = client.get(f"/api/cv/versions/{v['id']}").json()
        assert after["markdown"] == tailored and after["base_updated"] is False
        assert _accept(client, s).status_code == 200
        final = client.get(f"/api/cv/versions/{v['id']}").json()["markdown"]
        assert "I ran 150 grasping trials." in final and "soft robotics at MIT." in final
        assert client.get(f"/api/cv/documents/{base['id']}").json()["markdown"] == new_base


def test_keeping_a_variant_as_is_clears_the_flag_without_touching_it():
    with _client() as client:
        base = _sop(client)
        v = _fork(client, base)
        client.put(
            f"/api/cv/documents/{base['id']}",
            json={"base_revision": 1, "markdown": SOP + "\nMore.\n"},
        )
        kept = client.post(f"/api/cv/versions/{v['id']}/keep").json()
        assert kept["base_updated"] is False and kept["markdown"] == SOP
        assert kept["revision"] == v["revision"]
        assert client.get(f"/api/cv/versions/{v['id']}/base-changes").json()["changes"] == []


def test_renaming_the_base_is_not_a_change_to_offer():
    with _client() as client:
        base = _sop(client)
        v = _fork(client, base)
        client.put(f"/api/cv/documents/{base['id']}", json={"base_revision": 1, "title": "Renamed"})
        assert client.get(f"/api/cv/versions/{v['id']}").json()["base_updated"] is False


def test_base_changes_widen_an_ambiguous_line_with_context():
    forked = "# A\n\n- Python\n\n# B\n\n- Python\n"
    base = "# A\n\n- Python\n\n# B\n\n- Rust\n"
    [c] = cv_service.base_changes(forked, base, forked)
    assert c["applicable"] and c["find"].count("- Python") == 1 and "# B" in c["find"]
    assert c["replace"] == c["find"].replace("- Python", "- Rust")


def test_migration_starts_existing_variants_from_the_base_as_it_is():
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "044_document_kinds")
        _run(
            _execute(
                url,
                """
                INSERT INTO users (id, email, password_hash) VALUES ('u1', 'u1@example.com', 'x');
                INSERT INTO cv_documents (id, title, format, status, size_bytes, user_id, markdown, revision)
                VALUES ('d1', 'CV', 'md', 'ready', 0, 'u1', '# Base', 4);
                INSERT INTO cv_tailored_versions (id, document_id, name, markdown, revision, user_id)
                VALUES ('v1', 'd1', 'For MIT', '# Variant', 1, 'u1');
                """,
            )
        )
        command.upgrade(cfg, "045_fork_lineage")
        [row] = _run(_fetch(url, "SELECT forked_from_revision, forked_from_markdown FROM cv_tailored_versions"))
        assert row["forked_from_revision"] == 4 and row["forked_from_markdown"] == "# Base"
        command.downgrade(cfg, "044_document_kinds")
        command.upgrade(cfg, "head")

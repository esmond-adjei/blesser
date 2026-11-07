import asyncio
import logging
import uuid

import asyncpg
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from alembic import command
from api.agent.tools import ToolContext, dispatch
from api.core.db import SessionLocal
from api.main import app
from api.prospects.models import RunSchool, School
from api.runs.budgets import run_budget
from api.runs.models import ResearchTask, Run
from tests.conftest import TEST_USER_ID
from tests.test_migrations import _cfg, _dsn, _fetch, _run, _scratch_db


async def _execute(url: str, sql: str) -> None:
    conn = await asyncpg.connect(_dsn(url))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def _uid() -> str:
    # The suite shares one account, so every school here gets its own name.
    return uuid.uuid4().hex[:8]


def _make_run(**budgets) -> str:
    async def setup():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID,
                region="Anywhere",
                field="robotics",
                degree_level="phd",
                interest_statement="robots",
                status="running",
                **budgets,
            )
            session.add(run)
            await session.commit()
            return run.id

    return asyncio.run(setup())


def _save(run_id: str, **payload) -> dict:
    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            return await dispatch("save_program", payload, ToolContext(session=session, run=run))

    return asyncio.run(go())


def _schools_named(name: str) -> list[School]:
    async def go():
        async with SessionLocal() as session:
            rows = await session.execute(
                select(School).where(School.user_id == TEST_USER_ID, School.name == name)
            )
            return list(rows.scalars().all())

    return asyncio.run(go())


def _links(school_id: str) -> set[str]:
    async def go():
        async with SessionLocal() as session:
            rows = await session.execute(
                select(RunSchool.run_id).where(RunSchool.school_id == school_id)
            )
            return {r for (r,) in rows.all()}

    return asyncio.run(go())


def _research_tasks(run_id: str, program_id: str) -> int:
    async def go():
        async with SessionLocal() as session:
            return (
                await session.execute(
                    select(func.count())
                    .select_from(ResearchTask)
                    .where(
                        ResearchTask.run_id == run_id,
                        ResearchTask.target_id == program_id,
                        ResearchTask.task_type == "research_professor",
                    )
                )
            ).scalar()

    return asyncio.run(go())


def test_two_runs_share_one_school_and_its_programmes():
    school = f"Shared University {_uid()}"
    run_a, run_b = _make_run(), _make_run()
    a = _save(run_a, school_name=school, program_name="PhD in Robotics")
    b = _save(run_b, school_name=school.upper(), program_name="PhD in Vision", school_country="Ghana")

    assert a["school_id"] == b["school_id"]
    rows = _schools_named(school)
    assert len(rows) == 1
    assert rows[0].country == "Ghana"
    assert _links(a["school_id"]) == {run_a, run_b}

    client = TestClient(app)
    for run_id in (run_a, run_b):
        tree = client.get(f"/api/runs/{run_id}/programs").json()
        mine = next(s for s in tree if s["id"] == a["school_id"])
        assert {p["name"] for p in mine["programs"]} == {"PhD in Robotics", "PhD in Vision"}
    page = client.get(f"/api/schools/{a['school_id']}").json()
    assert {p["name"] for p in page["programs"]} == {"PhD in Robotics", "PhD in Vision"}


def test_a_programme_another_run_found_is_reused_and_researched_again():
    school = f"Reuse University {_uid()}"
    run_a, run_b = _make_run(), _make_run()
    first = _save(run_a, school_name=school, program_name="PhD in Robotics")
    again = _save(run_b, school_name=school, program_name="phd in robotics.")

    assert again["program_id"] == first["program_id"]
    assert again.get("reused") is True
    # Each run scores its own candidates, so each queues the research.
    assert _research_tasks(run_a, first["program_id"]) == 1
    assert _research_tasks(run_b, first["program_id"]) == 1
    repeat = _save(run_b, school_name=school, program_name="PhD in Robotics")
    assert repeat["deduped"] is True
    assert _research_tasks(run_b, first["program_id"]) == 1


def test_programme_matched_by_department_page():
    school = f"Dept University {_uid()}"
    run_a, run_b = _make_run(), _make_run()
    first = _save(
        run_a,
        school_name=school,
        program_name="PhD in Computer Science",
        department_url="https://cs.example.edu/phd/",
    )
    second = _save(
        run_b,
        school_name=school,
        program_name="Doctorate in Computing",
        department_url="http://www.cs.example.edu/phd",
    )
    assert second["program_id"] == first["program_id"]


def test_school_matched_by_website_host():
    host = f"u{_uid()}.example.edu"
    run_a, run_b = _make_run(), _make_run()
    first = _save(
        run_a, school_name=f"Short Name {host}", program_name="PhD A", school_website=f"https://www.{host}/"
    )
    second = _save(
        run_b, school_name=f"Long Official Name {host}", program_name="PhD B", school_website=f"http://{host}"
    )
    assert second["school_id"] == first["school_id"]


def test_run_caps_count_the_runs_links():
    known = f"Known University {_uid()}"
    other = f"Other University {_uid()}"
    run_a = _make_run()
    run_b = _make_run(max_programs=1)
    _save(run_a, school_name=known, program_name="PhD A")

    # Linking a school the account has spends run B's school cap once.
    linked = _save(run_b, school_name=known, program_name="PhD B")
    assert "program_id" in linked
    more = _save(run_b, school_name=known, program_name="PhD C")
    assert "program_id" in more
    refused = _save(run_b, school_name=other, program_name="PhD D")
    assert "error" in refused

    async def budgets():
        async with SessionLocal() as session:
            return (
                await run_budget(session, await session.get(Run, run_a)),
                await run_budget(session, await session.get(Run, run_b)),
            )

    budget_a, budget_b = asyncio.run(budgets())
    assert budget_a["programs"]["used"] == 1
    assert budget_b["programs"]["used"] == 1


def test_deleting_a_run_keeps_a_school_another_run_uses():
    shared = f"Kept University {_uid()}"
    own = f"Gone University {_uid()}"
    run_a, run_b = _make_run(), _make_run()
    kept = _save(run_a, school_name=shared, program_name="PhD A")
    gone = _save(run_a, school_name=own, program_name="PhD B")
    _save(run_b, school_name=shared, program_name="PhD C")

    client = TestClient(app)
    assert client.get(f"/api/runs/{run_a}/delete-preview").json()["schools"] == 1
    assert client.delete(f"/api/runs/{run_a}").status_code == 200

    assert _schools_named(own) == []
    assert len(_schools_named(shared)) == 1
    assert _links(kept["school_id"]) == {run_b}
    assert _links(gone["school_id"]) == set()
    page = client.get(f"/api/schools/{kept['school_id']}").json()
    assert {p["name"] for p in page["programs"]} == {"PhD A", "PhD C"}

    assert client.delete(f"/api/runs/{run_b}").status_code == 200
    assert _schools_named(shared) == []


def test_adding_a_school_by_hand_links_the_one_the_account_has():
    school = f"Manual University {_uid()}"
    run_a, run_b = _make_run(), _make_run()
    found = _save(run_a, school_name=school, program_name="PhD A")

    client = TestClient(app)
    added = client.post(
        f"/api/runs/{run_b}/schools",
        json={"name": school.lower(), "country": None, "website_url": None, "programs": [{"name": "PhD A"}]},
    )
    assert added.status_code == 200, added.text
    body = added.json()
    assert body["id"] == found["school_id"]
    assert [p["id"] for p in body["programs"]] == [found["program_id"]]
    assert _links(found["school_id"]) == {run_a, run_b}
    assert _research_tasks(run_b, found["program_id"]) == 1


def test_programmes_added_at_a_shared_school_queue_on_its_latest_run():
    school = f"Latest University {_uid()}"
    run_a, run_b = _make_run(), _make_run()
    first = _save(run_a, school_name=school, program_name="PhD A")
    _save(run_b, school_name=school, program_name="PhD B")

    created = TestClient(app).post(
        f"/api/schools/{first['school_id']}/programs", json={"name": "PhD New", "department_url": None}
    )
    assert created.status_code == 200, created.text
    assert _research_tasks(run_b, created.json()["id"]) == 1
    assert _research_tasks(run_a, created.json()["id"]) == 0


def test_migration_merges_each_accounts_duplicate_schools(caplog):
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "038_faculty_rosters")
        _run(
            _execute(
                url,
                """
                INSERT INTO users (id, email, password_hash) VALUES
                  ('u1', 'u1@example.com', 'x'), ('u2', 'u2@example.com', 'x');
                INSERT INTO runs (id, user_id, region, field, degree_level, interest_statement, status, created_at) VALUES
                  ('r1', 'u1', 'r', 'f', 'phd', 'i', 'done', '2026-01-01'),
                  ('r2', 'u1', 'r', 'f', 'phd', 'i', 'done', '2026-02-01'),
                  ('r3', 'u2', 'r', 'f', 'phd', 'i', 'done', '2026-03-01');
                INSERT INTO schools (id, run_id, user_id, name, origin, tier, image_url) VALUES
                  ('s1', 'r1', 'u1', 'Uni of Examples', 'agent', 'top', NULL),
                  ('s2', 'r2', 'u1', 'UNI OF EXAMPLES', 'agent', 'solid', 'https://e.x/logo.png'),
                  ('s3', 'r3', 'u2', 'Uni of Examples', 'user', NULL, NULL);
                INSERT INTO programs (id, school_id, user_id, name) VALUES
                  ('p1', 's1', 'u1', 'PhD in AI'),
                  ('p2', 's2', 'u1', 'phd in ai'),
                  ('p3', 's2', 'u1', 'PhD in Vision');
                INSERT INTO professors (id, program_id, user_id, name, openalex_id) VALUES
                  ('a1', 'p1', 'u1', 'Ada', 'A1'),
                  ('a2', 'p2', 'u1', 'Ada', 'A1'),
                  ('a3', 'p2', 'u1', 'Grace', 'A2');
                INSERT INTO candidate_scores (id, run_id, user_id, professor_id, status) VALUES
                  ('c1', 'r1', 'u1', 'a1', 'scored'),
                  ('c2', 'r2', 'u1', 'a2', 'scored');
                INSERT INTO research_tasks (id, run_id, user_id, task_type, status, target_id) VALUES
                  ('t2', 'r2', 'u1', 'research_professor', 'done', 'p2');
                """,
            )
        )
        with caplog.at_level(logging.INFO, logger="alembic.runtime.migration"):
            command.upgrade(cfg, "head")

        schools = _run(_fetch(url, "SELECT id, user_id, image_url, run_id FROM schools ORDER BY id"))
        assert [(s["id"], s["user_id"]) for s in schools] == [("s1", "u1"), ("s3", "u2")]
        assert schools[0]["image_url"] == "https://e.x/logo.png"
        links = _run(_fetch(url, "SELECT run_id, school_id, origin, tier FROM run_schools ORDER BY run_id"))
        assert [tuple(r) for r in links] == [
            ("r1", "s1", "agent", "top"),
            ("r2", "s1", "agent", "solid"),
            ("r3", "s3", "user", None),
        ]
        programs = _run(_fetch(url, "SELECT id, school_id FROM programs ORDER BY id"))
        assert [tuple(p) for p in programs] == [("p1", "s1"), ("p3", "s1")]
        professors = _run(_fetch(url, "SELECT id, program_id FROM professors ORDER BY id"))
        assert [tuple(p) for p in professors] == [("a1", "p1"), ("a3", "p1")]
        candidates = _run(_fetch(url, "SELECT id, professor_id FROM candidate_scores ORDER BY id"))
        assert [tuple(c) for c in candidates] == [("c1", "a1"), ("c2", "a1")]
        task = _run(_fetch(url, "SELECT target_id FROM research_tasks WHERE id = 't2'"))
        assert task[0]["target_id"] == "p1"
        assert "account u1 had 2 school rows, now 1" in caplog.text
        assert "3 school rows merged into 2" in caplog.text

        # Reversible up to the merge: links go, run_id is required again.
        command.downgrade(cfg, "038_faculty_rosters")
        assert _run(_fetch(url, "SELECT count(*) AS n FROM schools WHERE run_id IS NULL"))[0]["n"] == 0
        command.upgrade(cfg, "head")


def _scored(program_id: str, runs_scores: list[tuple[str, float]], openalex_id: str) -> tuple[str, list[str]]:
    """A professor on a programme with one candidate per (run, score)."""
    from api.candidates.models import CandidateScore, CandidateStatus
    from api.prospects.models import Professor

    async def go():
        async with SessionLocal() as session:
            prof = Professor(user_id=TEST_USER_ID, program_id=program_id, name="Prof Shared", openalex_id=openalex_id)
            session.add(prof)
            await session.flush()
            ids = []
            for run_id, score in runs_scores:
                cand = CandidateScore(
                    user_id=TEST_USER_ID, run_id=run_id, professor_id=prof.id,
                    similarity_score=score, rationale="fits", status=CandidateStatus.scored,
                )
                session.add(cand)
                await session.flush()
                ids.append(cand.id)
            await session.commit()
            return prof.id, ids

    return asyncio.run(go())


def test_a_known_professor_is_scored_again_for_another_run():
    from api.prospects import tools as prospect_tools
    from api.prospects.models import Professor, Program

    name = f"Dedup University {_uid()}"
    run_a, run_b = _make_run(), _make_run()
    saved = _save(run_a, school_name=name, program_name="PhD in Robotics")
    _save(run_b, school_name=name, program_name="PhD in Robotics")
    openalex_id = f"A{_uid()}"
    prof_id, (cand_a,) = _scored(saved["program_id"], [(run_a, 0.7)], openalex_id)

    def dedup(run_id):
        async def go():
            async with SessionLocal() as session:
                run = await session.get(Run, run_id)
                program = await session.get(Program, saved["program_id"])
                prof = await session.get(Professor, prof_id)
                ctx = ToolContext(session=session, run=run, program=program)
                return await prospect_tools.complete_dedup(ctx, {"openalex_id": openalex_id, "name": "Prof Shared"}, prof)

        return asyncio.run(go())

    result = dedup(run_b)
    assert result.get("candidate_id") != cand_a
    assert "error" in result
    assert dedup(run_a)["candidate_id"] == cand_a


def test_account_listing_shows_each_school_once_with_its_runs_and_faculty():
    client = TestClient(app)
    name = f"Listed University {_uid()}"
    run_a, run_b = _make_run(), _make_run()
    a = _save(run_a, school_name=name, program_name="PhD in Robotics")
    _save(run_b, school_name=name, program_name="PhD in Vision")

    listed = [s for s in client.get("/api/schools").json() if s["name"] == name]
    assert len(listed) == 1
    assert listed[0]["run_ids"] == [run_a, run_b]
    assert sorted(p["name"] for p in listed[0]["programs"]) == ["PhD in Robotics", "PhD in Vision"]

    _scored(a["program_id"], [(run_a, 0.4), (run_b, 0.6)], f"A{_uid()}")
    faculty = client.get(f"/api/schools/{a['school_id']}/faculty").json()
    best = next(f for f in faculty if f["name"] == "Prof Shared")
    assert best["similarity_score"] == 0.6
    assert best["candidate_run_id"] == run_b


def test_a_professor_scored_by_two_runs_still_opens():
    name = f"Two Scores University {_uid()}"
    run_a, run_b = _make_run(), _make_run()
    saved = _save(run_a, school_name=name, program_name="PhD in Robotics")
    _save(run_b, school_name=name, program_name="PhD in Robotics")
    prof_id, cands = _scored(saved["program_id"], [(run_a, 0.7), (run_b, 0.8)], f"A{_uid()}")

    page = TestClient(app).get(f"/api/professors/{prof_id}")
    assert page.status_code == 200, page.text
    assert page.json()["candidate_id"] in cands


def test_a_professor_is_listed_unmatched_then_checked_and_saved_as_a_match():
    from api.prospects.models import Paper, Professor

    client = TestClient(app)
    run_id = _make_run()
    saved = _save(run_id, school_name=f"Catalog University {_uid()}", program_name="PhD in Robotics")

    async def add():
        async with SessionLocal() as session:
            prof = Professor(user_id=TEST_USER_ID, program_id=saved["program_id"], name=f"Prof {_uid()}")
            session.add(prof)
            await session.flush()
            session.add(Paper(user_id=TEST_USER_ID, professor_id=prof.id, title="Legged robots", abstract="robots that walk"))
            await session.commit()
            return prof.id

    prof_id = asyncio.run(add())
    row = next(p for p in client.get("/api/professors").json() if p["id"] == prof_id)
    assert row["candidate_id"] is None

    checked = client.post(f"/api/professors/{prof_id}/match", json={"run_id": run_id})
    assert checked.status_code == 200, checked.text
    assert checked.json()["paper"] == "Legged robots"
    assert checked.json()["candidate_id"] is None

    kept = client.post(f"/api/professors/{prof_id}/match", json={"run_id": run_id, "save": True}).json()
    row = next(p for p in client.get("/api/professors").json() if p["id"] == prof_id)
    assert row["candidate_id"] == kept["candidate_id"]

    async def set_rationale():
        from api.candidates.models import CandidateScore
        async with SessionLocal() as session:
            (await session.get(CandidateScore, kept["candidate_id"])).rationale = "Her lab builds legged robots."
            await session.commit()
    asyncio.run(set_rationale())
    again = client.post(f"/api/professors/{prof_id}/match", json={"run_id": run_id, "save": True}).json()
    assert again["candidate_id"] == kept["candidate_id"]
    assert client.get(f"/api/candidates/{kept['candidate_id']}").json()["rationale"] == "Her lab builds legged robots."


def test_editing_a_professor_a_run_only_looked_up_saves_them_first():
    from datetime import UTC, datetime

    from api.prospects.models import ProfessorIndex

    saved = _save(_make_run(), school_name=f"Lookup University {_uid()}", program_name="PhD in Robotics")

    async def add():
        async with SessionLocal() as session:
            entry = ProfessorIndex(
                user_id=TEST_USER_ID, name="Prof Looked Up", name_key=f"looked up {_uid()}",
                school_name="Lookup University", school_key=_uid(), program_id=saved["program_id"],
                openalex_id=f"A{_uid()}", works=[{"title": "Walking robots"}], outcome="no_match",
                looked_up_at=datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None),
            )
            session.add(entry)
            await session.commit()
            return entry.id

    entry_id = asyncio.run(add())
    edited = TestClient(app).patch(f"/api/professors/{entry_id}", json={"bio": "Builds walking robots."})
    assert edited.status_code == 200, edited.text
    assert edited.json()["id"] != entry_id
    assert edited.json()["bio"] == "Builds walking robots."
    assert [p["title"] for p in edited.json()["papers"]] == ["Walking robots"]


def test_a_professor_is_checked_against_an_interest_document():
    from api.cv.models import CvDocument
    from api.prospects.models import Paper, Professor

    client = TestClient(app)
    saved = _save(_make_run(), school_name=f"Doc University {_uid()}", program_name="PhD in Robotics")

    async def add():
        async with SessionLocal() as session:
            doc = CvDocument(user_id=TEST_USER_ID, title="Interests", kind="interest", markdown="legged robots that walk")
            prof = Professor(user_id=TEST_USER_ID, program_id=saved["program_id"], name=f"Prof {_uid()}")
            session.add_all([doc, prof])
            await session.flush()
            session.add(Paper(user_id=TEST_USER_ID, professor_id=prof.id, title="Legged robots", abstract="robots that walk"))
            await session.commit()
            return doc.id, prof.id

    doc_id, prof_id = asyncio.run(add())
    checked = client.post(f"/api/professors/{prof_id}/match", json={"document_id": doc_id})
    assert checked.status_code == 200, checked.text
    # No run scores against this document, so there's nowhere to save it.
    assert checked.json()["run_id"] is None
    assert client.post(f"/api/professors/{prof_id}/match", json={"document_id": doc_id, "save": True}).status_code == 400


def test_papers_come_from_openalex_and_are_not_stored_twice(monkeypatch):
    from api.prospects import openalex
    from api.prospects import service as prospect_service
    from api.prospects.models import Professor

    citations = iter([3, 9])

    async def works(author_id, *args, **kwargs):
        assert author_id == "A42"
        return [{"title": "Legged robots", "abstract": "walking", "year": 2025, "url": None,
                 "citations": next(citations), "publication_type": "conference-paper",
                 "coauthors": [{"name": "Ada Lovelace", "openalex_id": "A7"}]}]

    monkeypatch.setattr(openalex, "get_recent_works", works)
    saved = _save(_make_run(), school_name=f"Papers University {_uid()}", program_name="PhD in Robotics")

    async def go():
        async with SessionLocal() as session:
            prof = Professor(user_id=TEST_USER_ID, program_id=saved["program_id"], name=f"Prof {_uid()}")
            session.add(prof)
            await session.commit()
            first = await prospect_service.save_professor_papers(session, TEST_USER_ID, prof.id, "https://openalex.org/a42")
            again = await prospect_service.save_professor_papers(session, TEST_USER_ID, prof.id, "A42")
            return first, again

    first, again = asyncio.run(go())
    assert first["papers_added"] == 1 and first["openalex_id"] == "A42"
    assert again["papers_added"] == 0 and len(again["papers"]) == 1
    (paper,) = again["papers"]
    assert paper["citations"] == 9
    assert paper["publication_type"] == "conference-paper"
    assert paper["coauthors"] == [{"name": "Ada Lovelace", "openalex_id": "A7"}]


def test_openalex_works_keep_citations_and_other_authors(monkeypatch):
    from api.prospects import openalex

    async def get_json(path, params, **kwargs):
        return {"results": [{
            "title": "Legged robots", "publication_year": 2025, "cited_by_count": 12,
            "type": "article", "type_crossref": "proceedings-article",
            "authorships": [
                {"author": {"id": "https://openalex.org/A42", "display_name": "Prof Self"}},
                {"author": {"id": "https://openalex.org/A7", "display_name": "Ada Lovelace"}},
            ],
        }]}

    monkeypatch.setattr(openalex, "_get_json", get_json)
    (work,) = asyncio.run(openalex.get_recent_works("A42"))
    assert work["citations"] == 12
    assert work["publication_type"] == "conference-paper"
    assert work["coauthors"] == [{"name": "Ada Lovelace", "openalex_id": "A7"}]
    assert "coauthors" not in openalex.brief_works([work])[0]


def test_openalex_publication_type_uses_source_and_preserves_unknown():
    from api.prospects.openalex import _publication_type

    assert _publication_type({"type": "article", "primary_location": {"source": {"type": "journal"}}}) == "journal-article"
    assert _publication_type({"type": "article", "primary_location": {"source": {"type": "conference"}}}) == "conference-paper"
    assert _publication_type({"type": "preprint"}) == "preprint"
    assert _publication_type({}) is None

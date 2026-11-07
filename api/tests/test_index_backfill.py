"""Rows are written at head and the migration undone and redone, so the backfill sees them as old rows."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from api.auth.models import User
from api.candidates.models import CandidateScore, CandidateStatus
from api.outreach.models import EmailDraft
from api.prospects.models import (
    Paper,
    Professor,
    ProfessorIndex,
    ProfessorOptOut,
    Program,
    RunSchool,
    School,
)
from api.runs.models import Run
from tests.test_migrations import _cfg, _fetch, _run, _scratch_db

T0 = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)


async def _seed(url: str) -> dict:
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            user = User(email="backfill@example.com", password_hash="x")
            s.add(user)
            await s.flush()
            u = user.id

            def run(text, at):
                return Run(user_id=u, region="US", field="robotics", degree_level="phd",
                           interest_statement=text, status="done", created_at=at)

            run_a, run_b, run_c = run("Robots", T0), run("Robots ", T0 + timedelta(days=1)), run("Vision", T0)
            s.add_all([run_a, run_b, run_c])
            await s.flush()
            school = School(user_id=u, name="Backfill University", tier="reach")
            s.add(school)
            await s.flush()
            s.add_all([
                RunSchool(run_id=run_a.id, school_id=school.id, tier="target", found_at=T0),
                RunSchool(run_id=run_b.id, school_id=school.id, tier="safety", found_at=T0 + timedelta(days=1)),
            ])
            p1 = Program(user_id=u, school_id=school.id, name="PhD in Robots")
            p2 = Program(user_id=u, school_id=school.id, name="PhD in Control")
            s.add_all([p1, p2])
            await s.flush()

            def prof(name, program, openalex=None, **kw):
                return Professor(user_id=u, program_id=program.id, name=name, openalex_id=openalex, socials=[], **kw)

            ada1 = prof("Ada Lovelace", p1, "https://openalex.org/A1", bio="Robots.", bio_source="faculty_page")
            ada2 = prof("Prof. Ada Lovelace", p2, "A1", email="ada@example.edu")
            bob1, bob2 = prof("Bob Byte", p1), prof("Bob Byte", p2)
            carl = prof("Carl Gone", p1)
            s.add_all([ada1, ada2, bob1, bob2, carl])
            s.add(ProfessorOptOut(name_key="carl gone|backfill university"))
            await s.flush()
            s.add_all([
                Paper(user_id=u, professor_id=ada1.id, title="Paper X", url="https://doi.org/10.1145/ABC.9"),
                Paper(user_id=u, professor_id=ada2.id, title="Paper X.", url="https://doi.org/10.1145/abc.9"),
            ])
            older = CandidateScore(user_id=u, run_id=run_a.id, professor_id=ada1.id, similarity_score=0.7,
                                   rationale="old", status=CandidateStatus.scored, created_at=T0)
            newer = CandidateScore(user_id=u, run_id=run_b.id, professor_id=ada2.id, similarity_score=0.9,
                                   rationale="new", status=CandidateStatus.rejected, created_at=T0 + timedelta(days=1))
            vision = CandidateScore(user_id=u, run_id=run_c.id, professor_id=bob1.id, similarity_score=0.5,
                                    rationale="eh", status=CandidateStatus.sent, created_at=T0)
            s.add_all([older, newer, vision])
            await s.flush()
            s.add(EmailDraft(user_id=u, candidate_id=older.id, subject="Hi", body="Hello"))
            s.add(ProfessorIndex(user_id=u, name="Dee Lookup", name_key="dee lookup", school_id=school.id,
                                 school_name="Backfill University", school_key="backfill university",
                                 openalex_id="A9", author={}, works=[{"title": "Work W", "year": 2023}],
                                 outcome="no_match", looked_up_at=T0))
            await s.commit()
            return {"user": u, "school": school.id, "older": older.id, "newer": newer.id,
                    "runs": [run_a.id, run_b.id, run_c.id]}
    finally:
        await engine.dispose()


def _one(url, sql):
    return _run(_fetch(url, sql))


def test_backfill_folds_old_rows_into_the_index_and_workspace():
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "head")
        ids = _run(_seed(url))
        command.downgrade(cfg, "046_document_limits")
        command.upgrade(cfg, "head")

        # Ada by OpenAlex id (under either spelling), Bob by name at the
        # school; Carl opted out.
        people = {r["name_key"]: r for r in _one(url, "SELECT * FROM index_professors")}
        assert set(people) == {"ada lovelace", "bob byte", "dee lookup"}
        ada = people["ada lovelace"]
        assert ada["openalex_id"] == "A1" and ada["bio"] == "Robots." and ada["email"] == "ada@example.edu"
        assert '"faculty_page"' in ada["provenance"]
        affiliations = _one(url, f"SELECT program_id FROM professor_affiliations WHERE professor_id = '{ada['id']}'")
        assert len(affiliations) == 2
        papers = _one(url, "SELECT p.work_key FROM index_papers p JOIN paper_authors a ON a.paper_id = p.id "
                           f"WHERE a.professor_id = '{ada['id']}'")
        assert [p["work_key"] for p in papers] == ["doi:10.1145/abc.9"]
        assert _one(url, f"SELECT works_fetched_at FROM index_professors WHERE id = '{people['dee lookup']['id']}'")[0][0]

        docs = _one(url, "SELECT id, markdown FROM cv_documents WHERE kind = 'interest' ORDER BY markdown")
        assert [d["markdown"] for d in docs] == ["Robots", "Vision"]
        run_docs = {r["id"]: r["interest_document_id"] for r in _one(url, "SELECT id, interest_document_id FROM runs")}
        a, b, c = ids["runs"]
        assert run_docs[a] == run_docs[b] != run_docs[c]

        matches = _one(url, f"SELECT * FROM matches WHERE professor_id = '{ada['id']}'")
        assert len(matches) == 1
        match = matches[0]
        assert (match["score"], match["status"], match["rationale"]) == (0.9, "passed", "new")
        history = _one(url, f"SELECT candidate_id FROM match_scores WHERE match_id = '{match['id']}' ORDER BY scored_at")
        assert [h["candidate_id"] for h in history] == [ids["older"], ids["newer"]]
        assert _one(url, f"SELECT count(*) FROM match_evidence WHERE match_id = '{match['id']}'")[0][0] == 1
        assert _one(url, f"SELECT match_id FROM email_drafts WHERE candidate_id = '{ids['older']}'")[0][0] == match["id"]
        bob = _one(url, f"SELECT status FROM matches WHERE professor_id = '{people['bob byte']['id']}'")
        assert [m["status"] for m in bob] == ["contacted"]
        assert _one(url, "SELECT count(*) FROM candidate_scores WHERE match_id IS NULL")[0][0] == 0

        shortlist = _one(url, "SELECT school_id, tier FROM school_shortlist")
        assert [(r["school_id"], r["tier"]) for r in shortlist] == [(ids["school"], "safety")]
        assert _one(url, "SELECT count(*) FROM professor_index WHERE index_professor_id IS NULL")[0][0] == 0

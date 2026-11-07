"""index and workspace: public facts apart from what belongs to the student

Revision ID: 047_index_workspace
Revises: 046_document_limits
Create Date: 2026-10-24

"""

import json
import logging
import re
import unicodedata
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from html import unescape

import sqlalchemy as sa

from alembic import op

revision: str = "047_index_workspace"
down_revision: str | Sequence[str] | None = "046_document_limits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")


def _id() -> str:
    return str(uuid.uuid4())


def _fk(target: str, ondelete: str, **kw) -> sa.Column:
    name = kw.pop("name")
    return sa.Column(name, sa.String(), sa.ForeignKey(target, ondelete=ondelete), **kw)


def upgrade() -> None:
    op.create_table(
        "index_professors",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("users.id", "CASCADE", name="user_id", nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("name_key", sa.String(), nullable=False),
        sa.Column("openalex_id", sa.String(), nullable=True),
        sa.Column("orcid", sa.String(19), nullable=True),
        sa.Column("dblp_pid", sa.String(), nullable=True),
        sa.Column("homepage_url", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("lab_name", sa.String(), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("photo_url", sa.String(), nullable=True),
        sa.Column("socials", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("profile_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("works_fetched_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "openalex_id", name="uq_index_professor_openalex"),
    )
    op.create_index("ix_index_professors_user_id", "index_professors", ["user_id"])
    op.create_index("ix_index_professors_user_name", "index_professors", ["user_id", "name_key"])

    op.create_table(
        "professor_affiliations",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("index_professors.id", "CASCADE", name="professor_id", nullable=False),
        _fk("schools.id", "CASCADE", name="school_id", nullable=False),
        _fk("programs.id", "SET NULL", name="program_id", nullable=True),
        sa.Column("department", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("professor_id", "school_id", "program_id", name="uq_affiliation_place"),
    )
    for col in ("professor_id", "school_id", "program_id"):
        op.create_index(f"ix_professor_affiliations_{col}", "professor_affiliations", [col])

    op.create_table(
        "index_papers",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("users.id", "CASCADE", name="user_id", nullable=False),
        sa.Column("work_key", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("doi", sa.String(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "work_key", name="uq_index_paper_work"),
    )
    op.create_index("ix_index_papers_user_id", "index_papers", ["user_id"])

    op.create_table(
        "paper_authors",
        _fk("index_papers.id", "CASCADE", name="paper_id", nullable=False),
        _fk("index_professors.id", "CASCADE", name="professor_id", nullable=False),
        sa.PrimaryKeyConstraint("paper_id", "professor_id"),
    )
    op.create_index("ix_paper_authors_professor_id", "paper_authors", ["professor_id"])

    op.create_table(
        "admission_cycles",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("users.id", "CASCADE", name="user_id", nullable=False),
        _fk("programs.id", "CASCADE", name="program_id", nullable=False),
        sa.Column("term", sa.String(64), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("funding", sa.Text(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("status", sa.String(16), server_default="unknown", nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("program_id", "term", name="uq_admission_cycle_term"),
    )
    op.create_index("ix_admission_cycles_user_id", "admission_cycles", ["user_id"])
    op.create_index("ix_admission_cycles_program_id", "admission_cycles", ["program_id"])

    op.create_table(
        "matches",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("users.id", "CASCADE", name="user_id", nullable=False),
        _fk("index_professors.id", "CASCADE", name="professor_id", nullable=False),
        _fk("cv_documents.id", "CASCADE", name="interest_document_id", nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), server_default="shortlisted", nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "professor_id", "interest_document_id", name="uq_match_interest"),
    )
    for col in ("user_id", "professor_id", "interest_document_id"):
        op.create_index(f"ix_matches_{col}", "matches", [col])

    op.create_table(
        "match_scores",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("matches.id", "CASCADE", name="match_id", nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        _fk("runs.id", "SET NULL", name="run_id", nullable=True),
        _fk("candidate_scores.id", "SET NULL", name="candidate_id", nullable=True, unique=True),
        sa.Column("interest_revision", sa.Integer(), nullable=True),
        sa.Column("scored_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_match_scores_match_id", "match_scores", ["match_id"])
    op.create_index("ix_match_scores_run_id", "match_scores", ["run_id"])

    op.create_table(
        "match_evidence",
        _fk("matches.id", "CASCADE", name="match_id", nullable=False),
        _fk("index_papers.id", "CASCADE", name="paper_id", nullable=False),
        sa.PrimaryKeyConstraint("match_id", "paper_id"),
    )
    op.create_index("ix_match_evidence_paper_id", "match_evidence", ["paper_id"])

    op.create_table(
        "school_shortlist",
        _fk("users.id", "CASCADE", name="user_id", nullable=False),
        _fk("schools.id", "CASCADE", name="school_id", nullable=False),
        sa.Column("tier", sa.String(16), nullable=True),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("added_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "school_id"),
    )
    op.create_index("ix_school_shortlist_school_id", "school_shortlist", ["school_id"])

    op.create_table(
        "index_overrides",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("users.id", "CASCADE", name="user_id", nullable=False),
        sa.Column("entity", sa.String(16), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "entity", "entity_id", "field", name="uq_index_override_field"),
    )
    op.create_index("ix_index_overrides_user_id", "index_overrides", ["user_id"])

    for table, col, target in _LINKS:
        op.add_column(table, _fk(target, "SET NULL", name=col, nullable=True))
        if table != "runs":
            op.create_index(f"ix_{table}_{col}", table, [col])

    _backfill(op.get_bind())


#: (table, column, target) for every legacy row's link to its new one.
_LINKS = [
    ("professors", "index_professor_id", "index_professors.id"),
    ("papers", "index_paper_id", "index_papers.id"),
    ("professor_index", "index_professor_id", "index_professors.id"),
    ("candidate_scores", "match_id", "matches.id"),
    ("email_drafts", "match_id", "matches.id"),
    ("applications", "program_id", "programs.id"),
    ("applications", "cycle_id", "admission_cycles.id"),
    ("applications", "match_id", "matches.id"),
    ("runs", "interest_document_id", "cv_documents.id"),
]


# Copies of api/index/keys.py and api/prospects/optouts.py, frozen for this migration.

_TAG = re.compile(r"<[^>]{0,200}>")
_NON_WORD = re.compile(r"[^a-z0-9]+")
_HONORIFIC = re.compile(r"^(prof(essor)?|dr|mr|mrs|ms|mx)\.?\s+", re.IGNORECASE)
_DEGREES = re.compile(r",?\s+(ph\.?\s?d|m\.?d|m\.?sc|dphil)\.?$", re.IGNORECASE)
_DOI = re.compile(r"(10\.\d{4,9}/\S+)", re.IGNORECASE)
_OPENALEX_WORK = re.compile(r"openalex\.org/(W\d+)", re.IGNORECASE)


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    plain = _TAG.sub("", unescape(text))
    folded = unicodedata.normalize("NFKD", plain)
    ascii_only = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return _NON_WORD.sub(" ", ascii_only.lower()).strip()


def _person_key(name: str | None) -> str:
    cleaned = (name or "").strip()
    while True:
        stripped = _HONORIFIC.sub("", cleaned)
        if stripped == cleaned:
            break
        cleaned = stripped
    cleaned = _DEGREES.sub("", cleaned).strip(" ,")
    return _normalize(cleaned or name)


def _openalex(value: str | None) -> str | None:
    raw = (value or "").strip().rstrip("/")
    return raw.rsplit("/", 1)[-1].upper() or None


def _doi(value: str | None) -> str | None:
    match = _DOI.search(value or "")
    return match.group(1).rstrip(".,;)").lower() if match else None


def _work_key(title: str, year, url: str | None, doi: str | None = None, work_id: str | None = None) -> str:
    found = _doi(doi) or _doi(url)
    if found:
        return f"doi:{found}"
    work = (work_id or "").rstrip("/").rsplit("/", 1)[-1].upper()
    if not work.startswith("W"):
        match = _OPENALEX_WORK.search(url or "")
        work = match.group(1).upper() if match else ""
    if work:
        return f"openalex:{work}"
    return f"title:{_normalize(title)}|{year or ''}"


def _optout_norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())).strip()


def _optout_key(name: str | None, school: str | None) -> str | None:
    n, s = _optout_norm(name), _optout_norm(school)
    return f"{n}|{s}" if n and s else None




class _Backfill:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.now = datetime.now(UTC).replace(tzinfo=None)
        rows = conn.execute(sa.text("SELECT openalex_id, name_key FROM professor_optouts")).all()
        self.out_ids = {_openalex(r[0]) for r in rows if r[0]}
        self.out_keys = {r[1] for r in rows if r[1]}
        self.by_openalex: dict[tuple[str, str], str] = {}
        self.by_name: dict[tuple[str, str, str], str] = {}
        self.openalex_of: dict[str, str | None] = {}
        self.papers: dict[tuple[str, str], str] = {}
        self.counts = dict.fromkeys(("interests", "people", "papers", "matches", "shortlist"), 0)

    def x(self, sql: str, **params):
        return self.conn.execute(sa.text(sql), params)

    def opted_out(self, openalex_id, name, school) -> bool:
        return bool(
            (openalex_id and _openalex(openalex_id) in self.out_ids)
            or (_optout_key(name, school) in self.out_keys)
        )

    def interests(self) -> None:
        docs = {
            (r[1], r[2]): r[0]
            for r in self.x("SELECT id, user_id, markdown FROM cv_documents WHERE kind = 'interest'").all()
        }
        runs = self.x(
            "SELECT id, user_id, field, region, interest_statement FROM runs ORDER BY created_at, id"
        ).all()
        for run_id, user_id, field, region, text in runs:
            text = (text or "").strip()
            if not text:
                continue
            doc_id = docs.get((user_id, text))
            if doc_id is None:
                doc_id = _id()
                topic = " · ".join(p for p in (field, region) if p)
                self.x(
                    """
                    INSERT INTO cv_documents (id, user_id, title, kind, format, status, size_bytes, markdown, revision)
                    VALUES (:id, :user_id, :title, 'interest', 'md', 'ready', 0, :text, 1)
                    """,
                    id=doc_id,
                    user_id=user_id,
                    title=(f"Interests: {topic}" if topic else "Research interests")[:200],
                    text=text,
                )
                docs[(user_id, text)] = doc_id
                self.counts["interests"] += 1
            self.x("UPDATE runs SET interest_document_id = :d WHERE id = :r", d=doc_id, r=run_id)

    def person(self, user_id, name, openalex_id, school_id) -> str:
        oa = _openalex(openalex_id)
        key = _person_key(name)
        found = self.by_openalex.get((user_id, oa)) if oa else None
        if found is None:
            named = self.by_name.get((user_id, school_id, key))
            # Same name at the same school, unless OpenAlex says it is someone else.
            if named and (not oa or self.openalex_of.get(named) in (None, oa)):
                found = named
        if found:
            if oa and (user_id, oa) not in self.by_openalex:
                # Known by name until now: the id is theirs too.
                self.x(
                    "UPDATE index_professors SET openalex_id = :oa WHERE id = :id AND openalex_id IS NULL",
                    oa=oa,
                    id=found,
                )
                self.by_openalex[(user_id, oa)] = found
                self.openalex_of[found] = oa
            self.by_name.setdefault((user_id, school_id, key), found)
            return found
        pid = _id()
        self.x(
            """
            INSERT INTO index_professors (id, user_id, name, name_key, openalex_id, socials, provenance)
            VALUES (:id, :user_id, :name, :key, :oa, CAST('[]' AS JSON), CAST('{}' AS JSON))
            """,
            id=pid,
            user_id=user_id,
            name=name,
            key=key,
            oa=oa,
        )
        if oa:
            self.by_openalex[(user_id, oa)] = pid
        self.openalex_of[pid] = oa
        self.by_name.setdefault((user_id, school_id, key), pid)
        self.counts["people"] += 1
        return pid

    def affiliate(self, pid, school_id, program_id, source, at) -> None:
        self.x(
            """
            INSERT INTO professor_affiliations (id, professor_id, school_id, program_id, source, verified_at)
            VALUES (:id, :p, :s, :g, :source, :at)
            ON CONFLICT ON CONSTRAINT uq_affiliation_place DO NOTHING
            """,
            id=_id(),
            p=pid,
            s=school_id,
            g=program_id,
            source=source,
            at=at or self.now,
        )

    def fill(self, pid, row) -> None:
        """Fill the person's empty profile fields from a professor row."""
        current = self.x(
            "SELECT homepage_url, email, lab_name, bio, photo_url, socials, provenance FROM index_professors WHERE id = :id",
            id=pid,
        ).mappings().one()
        sets, params = {}, {"id": pid}
        provenance = dict(_json(current["provenance"]) or {})
        for legacy, field in (
            ("profile_url", "homepage_url"),
            ("email", "email"),
            ("lab_name", "lab_name"),
            ("bio", "bio"),
            ("photo_url", "photo_url"),
        ):
            if row[legacy] and not current[field]:
                sets[field] = row[legacy]
                source = (row["bio_source"] if field == "bio" else None) or "research"
                provenance[field] = {"source": source, "fetched_at": self.now.isoformat()}
        socials = list(_json(current["socials"]) or [])
        known = {(s or {}).get("url") for s in socials}
        extra = [s for s in _json(row["socials"]) or [] if (s or {}).get("url") not in known]
        if not sets and not extra:
            return
        assignments = [f"{k} = :{k}" for k in sets]
        params.update(sets)
        assignments.append("socials = CAST(:socials AS JSON)")
        params["socials"] = json.dumps(socials + extra)
        assignments.append("provenance = CAST(:prov AS JSON)")
        params["prov"] = json.dumps(provenance)
        assignments.append("profile_fetched_at = :now")
        params["now"] = self.now
        self.x(f"UPDATE index_professors SET {', '.join(assignments)} WHERE id = :id", **params)

    def paper(self, user_id, pid, title, abstract, year, url, venue=None, doi=None, work_id=None, at=None) -> str | None:
        if not title:
            return None
        key = _work_key(title, year, url, doi, work_id)
        paper_id = self.papers.get((user_id, key))
        if paper_id is None:
            paper_id = _id()
            self.x(
                """
                INSERT INTO index_papers (id, user_id, work_key, title, abstract, year, venue, url, doi, source, fetched_at)
                VALUES (:id, :u, :k, :t, :a, :y, :v, :url, :doi, 'openalex', :at)
                """,
                id=paper_id,
                u=user_id,
                k=key,
                t=title,
                a=abstract,
                y=year if isinstance(year, int) else None,
                v=venue,
                url=url,
                doi=_doi(doi) or _doi(url),
                at=at or self.now,
            )
            self.papers[(user_id, key)] = paper_id
            self.counts["papers"] += 1
        self.x(
            "INSERT INTO paper_authors (paper_id, professor_id) VALUES (:p, :a) ON CONFLICT DO NOTHING",
            p=paper_id,
            a=pid,
        )
        return paper_id

    def professors(self) -> None:
        rows = self.x(
            """
            SELECT p.id, p.user_id, p.name, p.openalex_id, p.profile_url, p.email, p.lab_name, p.bio,
                   p.bio_source, p.photo_url, p.socials, p.program_id, g.school_id, s.name AS school
            FROM professors p JOIN programs g ON g.id = p.program_id JOIN schools s ON s.id = g.school_id
            ORDER BY p.user_id, p.id
            """
        ).mappings().all()
        for row in rows:
            if self.opted_out(row["openalex_id"], row["name"], row["school"]):
                continue
            pid = self.person(row["user_id"], row["name"], row["openalex_id"], row["school_id"])
            self.fill(pid, row)
            self.affiliate(pid, row["school_id"], row["program_id"], "roster", None)
            self.x("UPDATE professors SET index_professor_id = :p WHERE id = :id", p=pid, id=row["id"])

    def lookups(self) -> None:
        """professor_index entries: the same people, with their works."""
        rows = self.x(
            """
            SELECT e.id, e.user_id, e.name, e.openalex_id, e.school_id, e.program_id, e.school_name,
                   e.works, e.profile_url, e.looked_up_at
            FROM professor_index e ORDER BY e.user_id, e.looked_up_at, e.id
            """
        ).mappings().all()
        for row in rows:
            if self.opted_out(row["openalex_id"], row["name"], row["school_name"]):
                continue
            if row["school_id"] is None and (row["user_id"], _openalex(row["openalex_id"])) not in self.by_openalex:
                # No school left to place them at, and no one to merge into.
                continue
            pid = self.person(row["user_id"], row["name"], row["openalex_id"], row["school_id"])
            if row["school_id"]:
                self.affiliate(pid, row["school_id"], row["program_id"], "lookup", row["looked_up_at"])
            for work in _json(row["works"]) or []:
                if isinstance(work, dict):
                    self.paper(
                        row["user_id"], pid, work.get("title"), work.get("abstract"), work.get("year"),
                        work.get("url"), work.get("venue"), work.get("doi"), work.get("id"), row["looked_up_at"],
                    )
            self.x(
                """
                UPDATE index_professors SET works_fetched_at = GREATEST(COALESCE(works_fetched_at, :at), :at),
                       homepage_url = COALESCE(homepage_url, :url)
                WHERE id = :id
                """,
                at=row["looked_up_at"],
                url=row["profile_url"],
                id=pid,
            )
            self.x("UPDATE professor_index SET index_professor_id = :p WHERE id = :id", p=pid, id=row["id"])

    def legacy_papers(self) -> None:
        rows = self.x(
            """
            SELECT pa.id, pa.user_id, pa.title, pa.abstract, pa.year, pa.url, p.index_professor_id
            FROM papers pa JOIN professors p ON p.id = pa.professor_id
            WHERE p.index_professor_id IS NOT NULL ORDER BY pa.id
            """
        ).mappings().all()
        touched = set()
        for row in rows:
            paper_id = self.paper(
                row["user_id"], row["index_professor_id"], row["title"], row["abstract"], row["year"], row["url"]
            )
            if paper_id:
                self.x("UPDATE papers SET index_paper_id = :p WHERE id = :id", p=paper_id, id=row["id"])
                touched.add(row["index_professor_id"])
        for pid in touched:
            self.x(
                "UPDATE index_professors SET works_fetched_at = COALESCE(works_fetched_at, :now) WHERE id = :id",
                now=self.now,
                id=pid,
            )

    def matches(self) -> None:
        rows = self.x(
            """
            SELECT c.id, c.user_id, c.run_id, c.similarity_score, c.rationale, c.status, c.created_at,
                   c.professor_id, p.index_professor_id, r.interest_document_id, d.revision
            FROM candidate_scores c
            JOIN professors p ON p.id = c.professor_id
            JOIN runs r ON r.id = c.run_id
            JOIN cv_documents d ON d.id = r.interest_document_id
            WHERE p.index_professor_id IS NOT NULL
            ORDER BY c.created_at, c.id
            """
        ).mappings().all()
        found: dict[tuple, str] = {}
        for row in rows:
            key = (row["user_id"], row["index_professor_id"], row["interest_document_id"])
            match_id = found.get(key)
            if match_id is None:
                match_id = _id()
                self.x(
                    """
                    INSERT INTO matches (id, user_id, professor_id, interest_document_id, created_at, updated_at)
                    VALUES (:id, :u, :p, :d, :at, :at)
                    """,
                    id=match_id,
                    u=row["user_id"],
                    p=row["index_professor_id"],
                    d=row["interest_document_id"],
                    at=row["created_at"] or self.now,
                )
                found[key] = match_id
                self.counts["matches"] += 1
            self.x(
                """
                INSERT INTO match_scores (id, match_id, score, rationale, run_id, candidate_id, interest_revision, scored_at)
                VALUES (:id, :m, :s, :r, :run, :c, :rev, :at)
                """,
                id=_id(),
                m=match_id,
                s=row["similarity_score"],
                r=row["rationale"],
                run=row["run_id"],
                c=row["id"],
                rev=row["revision"],
                at=row["created_at"] or self.now,
            )
            # Rows come oldest first: the last scoring of a match sets it.
            status = str(row["status"] or "")
            self.x(
                "UPDATE matches SET score = :s, rationale = :r, status = :st WHERE id = :m",
                s=row["similarity_score"],
                r=row["rationale"],
                st={"rejected": "passed", "sent": "contacted"}.get(status, "shortlisted"),
                m=match_id,
            )
            self.x(
                """
                INSERT INTO match_evidence (match_id, paper_id)
                SELECT :m, index_paper_id FROM papers
                WHERE professor_id = :p AND index_paper_id IS NOT NULL
                ON CONFLICT DO NOTHING
                """,
                m=match_id,
                p=row["professor_id"],
            )
            self.x("UPDATE candidate_scores SET match_id = :m WHERE id = :c", m=match_id, c=row["id"])
            self.x("UPDATE email_drafts SET match_id = :m WHERE candidate_id = :c", m=match_id, c=row["id"])

    def shortlist(self) -> None:
        result = self.x(
            """
            INSERT INTO school_shortlist (user_id, school_id, tier)
            SELECT s.user_id, s.id, COALESCE(
                (SELECT rs.tier FROM run_schools rs
                 WHERE rs.school_id = s.id AND rs.tier IS NOT NULL
                 ORDER BY rs.found_at DESC LIMIT 1),
                s.tier)
            FROM schools s
            ON CONFLICT DO NOTHING
            """
        )
        self.counts["shortlist"] = result.rowcount or 0


def _json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _backfill(conn) -> None:
    fill = _Backfill(conn)
    fill.interests()
    fill.professors()
    fill.lookups()
    fill.legacy_papers()
    fill.matches()
    fill.shortlist()
    log.info("index_workspace: backfilled %s", fill.counts)


def downgrade() -> None:
    for table, col, _target in reversed(_LINKS):
        if table != "runs":
            op.drop_index(f"ix_{table}_{col}", table_name=table)
        op.drop_column(table, col)
    for table in (
        "index_overrides",
        "school_shortlist",
        "match_evidence",
        "match_scores",
        "matches",
        "admission_cycles",
        "paper_authors",
        "index_papers",
        "professor_affiliations",
        "index_professors",
    ):
        op.drop_table(table)

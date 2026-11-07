"""run schools: one school per account, linked to the runs that use it

Revision ID: 039_run_schools
Revises: 038_faculty_rosters
Create Date: 2026-10-17

Downgrade does not undo the merge of duplicate schools.
"""

import logging
import re
import unicodedata
from collections.abc import Sequence
from html import unescape

import sqlalchemy as sa

from alembic import op

revision: str = "039_run_schools"
down_revision: str | Sequence[str] | None = "038_faculty_rosters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")

_TAG = re.compile(r"<[^>]{0,200}>")
_NON_WORD = re.compile(r"[^a-z0-9]+")


def _normalize(text: str | None) -> str:
    """Copy of api.core.textnorm.normalize_text, frozen for this migration."""
    if not text:
        return ""
    plain = _TAG.sub("", unescape(text))
    folded = unicodedata.normalize("NFKD", plain)
    ascii_only = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return _NON_WORD.sub(" ", ascii_only.lower()).strip()


def upgrade() -> None:
    op.create_table(
        "run_schools",
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "school_id",
            sa.String(),
            sa.ForeignKey("schools.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("found_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("origin", sa.String(16), server_default="agent", nullable=False),
        sa.Column("tier", sa.String(16), nullable=True),
    )
    op.create_index("ix_run_schools_school_id", "run_schools", ["school_id"])
    op.execute(
        """
        INSERT INTO run_schools (run_id, school_id, found_at, origin, tier)
        SELECT s.run_id, s.id, r.created_at, s.origin, s.tier
        FROM schools s JOIN runs r ON r.id = s.run_id
        """
    )
    _merge_duplicates(op.get_bind())
    op.alter_column("schools", "run_id", existing_type=sa.String(), nullable=True)


def _merge_duplicates(conn) -> None:
    """Fold each account's copies of a school (same normalized name) into
    the oldest, then each school's same-named programmes into the oldest,
    then a programme's professors with the same OpenAlex id."""
    schools = conn.execute(
        sa.text(
            """
            SELECT s.id, s.user_id, s.name, s.country, s.website_url, s.image_url,
                   s.openalex_institution_id, s.institution_names
            FROM schools s LEFT JOIN runs r ON r.id = s.run_id
            ORDER BY s.user_id, r.created_at NULLS LAST, s.id
            """
        )
    ).mappings().all()
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in schools:
        groups.setdefault((row["user_id"], _normalize(row["name"])), []).append(dict(row))
    before: dict[str, int] = {}
    after: dict[str, int] = {}
    for (user_id, _key), rows in groups.items():
        before[user_id] = before.get(user_id, 0) + len(rows)
        after[user_id] = after.get(user_id, 0) + 1
        keep, dupes = rows[0], rows[1:]
        for dupe in dupes:
            _merge_school(conn, keep, dupe)
    for user_id in sorted(before):
        if before[user_id] != after[user_id]:
            log.info(
                "run_schools: account %s had %d school rows, now %d",
                user_id,
                before[user_id],
                after[user_id],
            )
    log.info(
        "run_schools: %d school rows merged into %d",
        sum(before.values()),
        sum(after.values()),
    )


def _merge_school(conn, keep: dict, dupe: dict) -> None:
    fill = {
        col: dupe[col]
        for col in (
            "country",
            "website_url",
            "image_url",
            "openalex_institution_id",
            "institution_names",
        )
        if not keep[col] and dupe[col]
    }
    if fill:
        sets = ", ".join(f"{col} = :{col}" for col in fill)
        conn.execute(sa.text(f"UPDATE schools SET {sets} WHERE id = :id"), {**fill, "id": keep["id"]})
        keep.update(fill)
    conn.execute(
        sa.text(
            """
            INSERT INTO run_schools (run_id, school_id, found_at, origin, tier)
            SELECT run_id, :keep, found_at, origin, tier FROM run_schools
            WHERE school_id = :dupe
            ON CONFLICT (run_id, school_id) DO NOTHING
            """
        ),
        {"keep": keep["id"], "dupe": dupe["id"]},
    )
    conn.execute(sa.text("DELETE FROM run_schools WHERE school_id = :dupe"), {"dupe": dupe["id"]})
    conn.execute(
        sa.text("UPDATE programs SET school_id = :keep WHERE school_id = :dupe"),
        {"keep": keep["id"], "dupe": dupe["id"]},
    )
    conn.execute(sa.text("DELETE FROM schools WHERE id = :dupe"), {"dupe": dupe["id"]})
    _merge_programs(conn, keep["id"])


def _merge_programs(conn, school_id: str) -> None:
    programs = conn.execute(
        sa.text("SELECT id, name, department_url FROM programs WHERE school_id = :s ORDER BY id"),
        {"s": school_id},
    ).mappings().all()
    by_name: dict[str, dict] = {}
    for row in programs:
        key = _normalize(row["name"])
        keep = by_name.get(key)
        if keep is None:
            by_name[key] = dict(row)
            continue
        if not keep["department_url"] and row["department_url"]:
            conn.execute(
                sa.text("UPDATE programs SET department_url = :u WHERE id = :id"),
                {"u": row["department_url"], "id": keep["id"]},
            )
            keep["department_url"] = row["department_url"]
        _merge_program(conn, keep["id"], row["id"])


def _merge_program(conn, keep: str, dupe: str) -> None:
    # Same OpenAlex id under both copies: merge, moving candidates and papers.
    pairs = conn.execute(
        sa.text(
            """
            SELECT d.id AS dupe, k.id AS keep FROM professors d
            JOIN professors k ON k.program_id = :keep AND k.openalex_id = d.openalex_id
            WHERE d.program_id = :dupe AND d.openalex_id IS NOT NULL
            """
        ),
        {"keep": keep, "dupe": dupe},
    ).mappings().all()
    for pair in pairs:
        params = {"keep": pair["keep"], "dupe": pair["dupe"]}
        conn.execute(
            sa.text("UPDATE candidate_scores SET professor_id = :keep WHERE professor_id = :dupe"),
            params,
        )
        kept_papers = conn.execute(
            sa.text("SELECT count(*) FROM papers WHERE professor_id = :keep"), params
        ).scalar()
        if kept_papers:
            conn.execute(sa.text("DELETE FROM papers WHERE professor_id = :dupe"), params)
        else:
            conn.execute(
                sa.text("UPDATE papers SET professor_id = :keep WHERE professor_id = :dupe"),
                params,
            )
        conn.execute(sa.text("DELETE FROM professors WHERE id = :dupe"), params)
    params = {"keep": keep, "dupe": dupe}
    conn.execute(sa.text("UPDATE professors SET program_id = :keep WHERE program_id = :dupe"), params)
    conn.execute(sa.text("UPDATE research_tasks SET target_id = :keep WHERE target_id = :dupe"), params)
    conn.execute(sa.text("DELETE FROM programs WHERE id = :dupe"), params)


def downgrade() -> None:
    op.execute(
        """
        UPDATE schools s SET run_id = first.run_id
        FROM (
            SELECT DISTINCT ON (school_id) school_id, run_id FROM run_schools
            ORDER BY school_id, found_at, run_id
        ) first
        WHERE s.id = first.school_id AND s.run_id IS NULL
        """
    )
    # A school no run links to has no run to belong to in the old schema.
    op.execute(
        """
        DELETE FROM papers WHERE professor_id IN (
            SELECT p.id FROM professors p JOIN programs g ON g.id = p.program_id
            JOIN schools s ON s.id = g.school_id WHERE s.run_id IS NULL
            AND NOT EXISTS (SELECT 1 FROM candidate_scores c WHERE c.professor_id = p.id))
        """
    )
    op.execute(
        """
        DELETE FROM professors WHERE program_id IN (
            SELECT g.id FROM programs g JOIN schools s ON s.id = g.school_id
            WHERE s.run_id IS NULL)
        AND NOT EXISTS (SELECT 1 FROM candidate_scores c WHERE c.professor_id = professors.id)
        """
    )
    op.execute(
        """
        DELETE FROM programs WHERE school_id IN (SELECT id FROM schools WHERE run_id IS NULL)
        AND NOT EXISTS (SELECT 1 FROM professors p WHERE p.program_id = programs.id)
        """
    )
    op.execute(
        """
        DELETE FROM schools WHERE run_id IS NULL
        AND NOT EXISTS (SELECT 1 FROM programs g WHERE g.school_id = schools.id)
        """
    )
    op.drop_index("ix_run_schools_school_id", table_name="run_schools")
    op.drop_table("run_schools")
    op.alter_column("schools", "run_id", existing_type=sa.String(), nullable=False)

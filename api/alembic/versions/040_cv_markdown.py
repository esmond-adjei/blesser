"""cv markdown: base CVs in Markdown, tailored versions, suggestions

Revision ID: 040_cv_markdown
Revises: 039_run_schools
Create Date: 2026-10-19

Downgrade restores the old tables empty; Markdown text and tailored versions are lost.
"""

import json
import logging
import re
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "040_cv_markdown"
down_revision: str | Sequence[str] | None = "039_run_schools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")

_OLD_TABLES = ("cv_proposals", "cv_branches", "cv_versions")

#: Copy of api/cv/markdown.py units_to_markdown, frozen for this migration.
_SECTION_WORDS = {
    "education", "experience", "work experience", "research experience",
    "professional experience", "employment", "publications", "projects",
    "skills", "technical skills", "awards", "honors", "honours",
    "certifications", "activities", "leadership", "teaching", "references",
    "summary", "profile", "objective", "interests", "research interests",
    "languages", "presentations", "grants", "coursework", "contact",
}
_BULLET = re.compile(r"^\s*(?:[-*+•●▪◦–·]|\d{1,2}[.)])\s+")
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s*)?\d{1,3}(?:\s*(?:/|of)\s*\d{1,3})?\s*$", re.IGNORECASE)


def _clean(text: str) -> str:
    text = re.sub(r"[  ]+", " ", text or "")
    text = re.sub(r"\s*\t[\t ]*", " — ", text.strip())
    return "  \n".join(line.strip() for line in text.split("\n") if line.strip())


def units_to_markdown(units: list[dict]) -> str:
    def part(u: dict) -> str:
        return ((u.get("source") or {}).get("part")) or ""

    ordered = sorted(
        units or [],
        key=lambda u: 0 if "/header" in part(u) else 2 if "/footer" in part(u) else 1,
    )
    blocks: list[str] = []
    bullets: list[str] = []
    for u in ordered:
        kind = u.get("type")
        text = _clean(u.get("text") or "")
        if kind == "image" or not text:
            continue
        if "/footer" in part(u) and _PAGE_NUMBER.match(text):
            continue
        if kind == "bullet":
            bullets.append("- " + _BULLET.sub("", text))
            continue
        if bullets:
            blocks.append("\n".join(bullets))
            bullets = []
        if kind == "heading":
            blocks.append("## " + text)
        elif text.rstrip(":").lower() in _SECTION_WORDS and len(text) <= 40:
            blocks.append("## " + text.rstrip(":"))
        else:
            blocks.append(text)
    if bullets:
        blocks.append("\n".join(bullets))
    return "\n\n".join(b for b in blocks if b.strip()).strip() + "\n"


def upgrade() -> None:
    op.add_column("cv_documents", sa.Column("markdown", sa.Text(), server_default="", nullable=False))
    op.add_column("cv_documents", sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
    op.add_column("cv_documents", sa.Column("source_path", sa.Text(), nullable=True))
    op.alter_column("cv_documents", "original_sha256", existing_type=sa.String(), nullable=True)

    bind = op.get_bind()
    docs = bind.execute(
        sa.text(
            """
            SELECT d.id, d.head_version_id, v.ir_json
            FROM cv_documents d LEFT JOIN cv_versions v ON v.id = d.head_version_id
            """
        )
    ).mappings().all()
    converted = 0
    for doc in docs:
        ir = doc["ir_json"] or {}
        if isinstance(ir, str):
            ir = json.loads(ir)
        markdown = units_to_markdown(ir.get("units") or []) if ir else ""
        # The latest DOCX the student had, else the upload itself.
        source = (
            f"cv/{doc['id']}/versions/{doc['head_version_id']}/document.docx"
            if doc["head_version_id"]
            else f"cv/{doc['id']}/original/source.docx"
        )
        bind.execute(
            sa.text("UPDATE cv_documents SET markdown = :md, source_path = :src WHERE id = :id"),
            {"md": markdown if markdown.strip() else "", "src": source, "id": doc["id"]},
        )
        converted += 1
    log.info("cv_markdown: converted %d CV document(s) to Markdown", converted)

    op.create_table(
        "cv_tailored_versions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("cv_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("markdown", sa.Text(), server_default="", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "candidate_id",
            sa.String(),
            sa.ForeignKey("candidate_scores.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "professor_id",
            sa.String(),
            sa.ForeignKey("professors.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "application_id",
            sa.String(),
            sa.ForeignKey("applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_label", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    for col in ("document_id", "candidate_id", "professor_id", "application_id", "user_id"):
        op.create_index(f"ix_cv_tailored_versions_{col}", "cv_tailored_versions", [col])
    op.create_table(
        "cv_suggestions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("cv_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.String(),
            sa.ForeignKey("cv_tailored_versions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("find", sa.Text(), nullable=False),
        sa.Column("replace", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("claim_check", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    for col in ("document_id", "version_id", "status", "user_id"):
        op.create_index(f"ix_cv_suggestions_{col}", "cv_suggestions", [col])

    for table in _OLD_TABLES:
        op.drop_table(table)
    op.drop_column("cv_documents", "fidelity_class")
    op.drop_column("cv_documents", "head_version_id")
    op.drop_column("cv_documents", "redo_stack")


def _owned(table: str) -> None:
    """The user_id column, index and FK migrations 015/016 gave a table."""
    op.add_column(table, sa.Column("user_id", sa.String(), nullable=False))
    op.create_index(f"ix_{table}_user_id", table, ["user_id"])
    op.create_foreign_key(
        f"fk_{table}_user_id", table, "users", ["user_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.add_column(
        "cv_documents",
        sa.Column("fidelity_class", sa.String(), server_default="high", nullable=False),
    )
    op.add_column("cv_documents", sa.Column("head_version_id", sa.String(), nullable=True))
    op.add_column(
        "cv_documents",
        sa.Column("redo_stack", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
    )
    op.execute("UPDATE cv_documents SET original_sha256 = '' WHERE original_sha256 IS NULL")
    op.alter_column("cv_documents", "original_sha256", existing_type=sa.String(), nullable=False)

    op.create_table(
        "cv_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("parent_version_id", sa.String(), nullable=True),
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("ir_json", sa.JSON(), nullable=False),
        sa.Column("operations_json", sa.JSON(), nullable=False),
        sa.Column("quality_report_json", sa.JSON(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["cv_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cv_versions_branch_id", "cv_versions", ["branch_id"])
    op.create_index("ix_cv_versions_document_id", "cv_versions", ["document_id"])
    op.create_table(
        "cv_branches",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("target_context", sa.JSON(), nullable=False),
        sa.Column("base_version_id", sa.String(), nullable=False),
        sa.Column("head_version_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["cv_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "name", name="uq_cv_branch_doc_name"),
    )
    op.create_index("ix_cv_branches_document_id", "cv_branches", ["document_id"])
    op.create_table(
        "cv_proposals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("base_version_id", sa.String(), nullable=False),
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("operations_json", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("verification_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["cv_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cv_proposals_document_id", "cv_proposals", ["document_id"])
    op.create_index("ix_cv_proposals_status", "cv_proposals", ["status"])
    for table in ("cv_versions", "cv_branches", "cv_proposals"):
        _owned(table)

    op.drop_table("cv_suggestions")
    op.drop_table("cv_tailored_versions")
    op.drop_column("cv_documents", "source_path")
    op.drop_column("cv_documents", "revision")
    op.drop_column("cv_documents", "markdown")

"""professor index: every professor a run looked up, kept per account

Revision ID: 042_professor_index
Revises: 041_notifications
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "042_professor_index"
down_revision: str | Sequence[str] | None = "041_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "professor_index",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("name_key", sa.String(), nullable=False),
        sa.Column(
            "school_id",
            sa.String(),
            sa.ForeignKey("schools.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("school_name", sa.String(), nullable=False),
        sa.Column("school_key", sa.String(), nullable=False),
        sa.Column(
            "program_id",
            sa.String(),
            sa.ForeignKey("programs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("program_name", sa.String(), nullable=True),
        sa.Column("openalex_id", sa.String(), nullable=False),
        sa.Column("author", sa.JSON(), nullable=False),
        sa.Column("works", sa.JSON(), nullable=False),
        sa.Column("profile_url", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("looked_up_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "school_key", "name_key", name="uq_professor_index_school_name"
        ),
    )
    op.create_index("ix_professor_index_user_id", "professor_index", ["user_id"])
    op.create_index("ix_professor_index_school_id", "professor_index", ["school_id"])
    op.create_index("ix_professor_index_run_id", "professor_index", ["run_id"])
    op.create_index(
        "ix_professor_index_user_openalex", "professor_index", ["user_id", "openalex_id"]
    )


def downgrade() -> None:
    op.drop_table("professor_index")

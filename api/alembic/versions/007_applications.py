"""application tracker

Revision ID: 007
Revises: 006
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007"
down_revision: str | Sequence[str] | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("school", sa.String(), nullable=False),
        sa.Column("program", sa.String(), nullable=False),
        sa.Column("degree_type", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=False),
        sa.Column("link", sa.String(), nullable=False),
        sa.Column("requirements", sa.JSON(), nullable=False),
        sa.Column("offer", sa.Text(), nullable=False),
        sa.Column("deadline", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("professors", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("fee_waiver", sa.Boolean(), nullable=False),
        sa.Column("fee_waiver_notes", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_applications_school", "applications", ["school"])
    op.create_index("ix_applications_run_id", "applications", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_applications_run_id", table_name="applications")
    op.drop_index("ix_applications_school", table_name="applications")
    op.drop_table("applications")

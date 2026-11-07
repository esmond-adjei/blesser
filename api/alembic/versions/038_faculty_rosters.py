"""faculty rosters: faculty_rosters

Revision ID: 038_faculty_rosters
Revises: 037_openalex_responses
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "038_faculty_rosters"
down_revision: str | Sequence[str] | None = "037_openalex_responses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "faculty_rosters",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("names", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_faculty_rosters_expires_at", "faculty_rosters", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_faculty_rosters_expires_at", table_name="faculty_rosters")
    op.drop_table("faculty_rosters")

"""school institution ids: schools.openalex_institution_id, institution_names

Revision ID: 029_school_institution
Revises: 028_school_tiers
Create Date: 2026-10-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "029_school_institution"
down_revision: str | Sequence[str] | None = "028_school_tiers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "schools", sa.Column("openalex_institution_id", sa.String(32), nullable=True)
    )
    op.add_column("schools", sa.Column("institution_names", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("schools", "institution_names")
    op.drop_column("schools", "openalex_institution_id")

"""school tiers: runs.school_tiers, schools.tier

Revision ID: 028_school_tiers
Revises: 027_compliance
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "028_school_tiers"
down_revision: str | Sequence[str] | None = "027_compliance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("school_tiers", sa.Text(), nullable=True))
    op.add_column("schools", sa.Column("tier", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("schools", "tier")
    op.drop_column("runs", "school_tiers")

"""school origin: separate agent research budget from user additions

Revision ID: 019_school_origin
Revises: 018_user_profile
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "019_school_origin"
down_revision: str | Sequence[str] | None = "018_user_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "schools",
        sa.Column("origin", sa.String(16), nullable=False, server_default="agent"),
    )


def downgrade() -> None:
    op.drop_column("schools", "origin")

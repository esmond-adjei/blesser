"""task pause/cancel statuses

Revision ID: 005
Revises: 004
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005"
down_revision: str | Sequence[str] | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain VARCHAR (native_enum=False) sized to the longest label; widen for "cancelled".
    op.alter_column(
        "research_tasks",
        "status",
        existing_type=sa.VARCHAR(length=7),
        type_=sa.String(length=16),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "research_tasks",
        "status",
        existing_type=sa.String(length=16),
        type_=sa.VARCHAR(length=7),
        existing_nullable=False,
    )

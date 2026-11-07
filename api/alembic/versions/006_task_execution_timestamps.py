"""task execution timestamps

Revision ID: 006
Revises: 005
Create Date: 2026-09-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006"
down_revision: str | Sequence[str] | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("research_tasks", sa.Column("started_at", sa.DateTime(), nullable=True))
    op.add_column(
        "research_tasks", sa.Column("finished_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("research_tasks", "finished_at")
    op.drop_column("research_tasks", "started_at")

"""task wait: research_tasks.wait_until

Revision ID: 034_task_wait_until
Revises: 033_plan_selection
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "034_task_wait_until"
down_revision: str | Sequence[str] | None = "033_plan_selection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("research_tasks", sa.Column("wait_until", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("research_tasks", "wait_until")

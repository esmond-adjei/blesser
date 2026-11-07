"""task lease: claimed_by + attempt on research_tasks

Revision ID: 026_task_lease
Revises: 025_agent_flows
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "026_task_lease"
down_revision: str | Sequence[str] | None = "025_agent_flows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("research_tasks", sa.Column("claimed_by", sa.String(), nullable=True))
    op.add_column(
        "research_tasks",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("research_tasks", "attempt")
    op.drop_column("research_tasks", "claimed_by")

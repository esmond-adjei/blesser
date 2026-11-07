"""agent controls: runs.agent_states

Revision ID: 036_run_agent_states
Revises: 035_task_metrics
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "036_run_agent_states"
down_revision: str | Sequence[str] | None = "035_task_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("agent_states", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "agent_states")

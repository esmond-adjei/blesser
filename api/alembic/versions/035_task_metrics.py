"""task metrics: model, cache reads, model and tool time, narrow path

Revision ID: 035_task_metrics
Revises: 034_task_wait_until
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "035_task_metrics"
down_revision: str | Sequence[str] | None = "034_task_wait_until"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    ("provider", sa.String()),
    ("model", sa.String()),
    ("cache_read_tokens", sa.Integer()),
    ("model_seconds", sa.Float()),
    ("tool_seconds", sa.Float()),
    ("path", sa.String()),
    ("path_reason", sa.String()),
)


def upgrade() -> None:
    for name, type_ in COLUMNS:
        op.add_column("research_tasks", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("research_tasks", name)

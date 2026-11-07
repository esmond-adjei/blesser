"""plan selection: users.plan_selected_at

Revision ID: 033_plan_selection
Revises: 032_model_default
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "033_plan_selection"
down_revision: str | Sequence[str] | None = "032_model_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("plan_selected_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE users SET plan_selected_at = created_at")


def downgrade() -> None:
    op.drop_column("users", "plan_selected_at")

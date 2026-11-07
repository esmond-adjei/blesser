"""user billing plan

Revision ID: 024_user_plan
Revises: 023_usage_daily
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "024_user_plan"
down_revision: str | Sequence[str] | None = "023_usage_daily"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("plan", sa.String(16), nullable=False, server_default="free")
    )


def downgrade() -> None:
    op.drop_column("users", "plan")

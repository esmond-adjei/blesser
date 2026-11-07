"""agent full access: Gradis makes changes without approval cards

Revision ID: 050_agent_full_access
Revises: 049_context_window
Create Date: 2026-10-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "050_agent_full_access"
down_revision: str | Sequence[str] | None = "049_context_window"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("agent_full_access", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "agent_full_access")

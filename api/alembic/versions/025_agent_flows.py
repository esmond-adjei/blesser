"""user-definable agent flows

Revision ID: 025_agent_flows
Revises: 024_user_plan
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "025_agent_flows"
down_revision: str | Sequence[str] | None = "024_user_plan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_flows",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("base", sa.String(32), nullable=False, server_default="standard"),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "flow_id",
            sa.String(),
            sa.ForeignKey("agent_flows.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("runs", "flow_id")
    op.drop_table("agent_flows")

"""agent tool registry and task switches

Revision ID: 013_agent_registry
Revises: 012_auth_users
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "013_agent_registry"
down_revision: str | Sequence[str] | None = "012_auth_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_tools",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "read_only", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "confirm_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("name", "scope"),
    )
    op.create_table(
        "agent_tasks",
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("tools", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("task_type"),
    )


def downgrade() -> None:
    op.drop_table("agent_tasks")
    op.drop_table("agent_tools")

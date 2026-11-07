"""provider model configs

Revision ID: 014_provider_configs
Revises: 013_agent_registry
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "014_provider_configs"
down_revision: str | Sequence[str] | None = "013_agent_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_configs",
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False, server_default=""),
        sa.Column("api_key", sa.String(), nullable=False, server_default=""),
        sa.Column("base_url", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("provider"),
    )


def downgrade() -> None:
    op.drop_table("provider_configs")

"""Auto (the system model) by default; own models opt-in and switchable

Revision ID: 032_model_default
Revises: 031_school_image
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "032_model_default"
down_revision: str | Sequence[str] | None = "031_school_image"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("prefer_own_model", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "provider_configs",
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.execute(
        """
        UPDATE runs SET llm_provider = (
            SELECT pc.provider FROM provider_configs pc
            WHERE pc.user_id = runs.user_id AND pc.is_active AND pc.model <> ''
            ORDER BY pc.provider LIMIT 1
        )
        WHERE llm_provider IS NULL
        """
    )
    op.execute("UPDATE runs SET llm_provider = 'system' WHERE llm_provider IS NULL")


def downgrade() -> None:
    op.drop_column("provider_configs", "enabled")
    op.drop_column("users", "prefer_own_model")

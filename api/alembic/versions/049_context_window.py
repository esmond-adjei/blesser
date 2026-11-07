"""context window: a saved model's context size, set once in settings

Revision ID: 049_context_window
Revises: 048_message_model
Create Date: 2026-10-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "049_context_window"
down_revision: str | Sequence[str] | None = "048_message_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("provider_configs", sa.Column("context_window", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("provider_configs", "context_window")

"""message model: which model wrote a Gradis reply

Revision ID: 048_message_model
Revises: 047_index_workspace
Create Date: 2026-10-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "048_message_model"
down_revision: str | Sequence[str] | None = "047_index_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assistant_messages", sa.Column("model", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("assistant_messages", "model")

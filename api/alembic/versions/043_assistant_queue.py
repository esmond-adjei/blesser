"""assistant queue: prompts sent while Gradis works

Revision ID: 043_assistant_queue
Revises: 042_professor_index
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "043_assistant_queue"
down_revision: str | Sequence[str] | None = "042_professor_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_queue",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(),
            sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("urgent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    for col in ("conversation_id", "user_id"):
        op.create_index(f"ix_assistant_queue_{col}", "assistant_queue", [col])


def downgrade() -> None:
    op.drop_table("assistant_queue")

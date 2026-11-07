"""assistant conversations

Revision ID: 1fa9ccfb410e
Revises: 007
Create Date: 2026-10-04 09:42:55.847993

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '1fa9ccfb410e'
down_revision: str | Sequence[str] | None = '007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('assistant_conversations',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('history_json', sa.Text(), nullable=True),
    sa.Column('pending_call_json', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('assistant_messages',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('conversation_id', sa.String(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('tool_calls_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['assistant_conversations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('assistant_messages')
    op.drop_table('assistant_conversations')

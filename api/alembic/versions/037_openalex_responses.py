"""openalex cache: openalex_responses

Revision ID: 037_openalex_responses
Revises: 036_run_agent_states
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "037_openalex_responses"
down_revision: str | Sequence[str] | None = "036_run_agent_states"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "openalex_responses",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_openalex_responses_expires_at", "openalex_responses", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_openalex_responses_expires_at", table_name="openalex_responses")
    op.drop_table("openalex_responses")

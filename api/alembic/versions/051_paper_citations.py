"""paper citations: cited-by counts and co-authors on saved papers

Revision ID: 051_paper_citations
Revises: 050_agent_full_access
Create Date: 2026-10-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "051_paper_citations"
down_revision: str | Sequence[str] | None = "050_agent_full_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("papers", sa.Column("citations", sa.Integer(), nullable=True))
    op.add_column("papers", sa.Column("coauthors", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("papers", "coauthors")
    op.drop_column("papers", "citations")

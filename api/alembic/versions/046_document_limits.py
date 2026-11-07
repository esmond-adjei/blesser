"""document limits: optional word and page limits; a suggestion's limit check

Revision ID: 046_document_limits
Revises: 045_fork_lineage
Create Date: 2026-10-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "046_document_limits"
down_revision: str | Sequence[str] | None = "045_fork_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("cv_documents", "cv_tailored_versions")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("word_limit", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("page_limit", sa.Integer(), nullable=True))
    op.add_column("cv_suggestions", sa.Column("limit_check", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("cv_suggestions", "limit_check")
    for table in _TABLES:
        op.drop_column(table, "page_limit")
        op.drop_column(table, "word_limit")

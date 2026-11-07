"""fork lineage: what each variant was forked from; refreshed suggestions

Revision ID: 045_fork_lineage
Revises: 044_document_kinds
Create Date: 2026-10-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "045_fork_lineage"
down_revision: str | Sequence[str] | None = "044_document_kinds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cv_tailored_versions", sa.Column("forked_from_revision", sa.Integer(), nullable=True)
    )
    op.add_column(
        "cv_tailored_versions", sa.Column("forked_from_markdown", sa.Text(), nullable=True)
    )
    op.execute(
        """
        UPDATE cv_tailored_versions AS v
        SET forked_from_revision = d.revision, forked_from_markdown = d.markdown
        FROM cv_documents AS d
        WHERE d.id = v.document_id
        """
    )
    op.add_column("cv_suggestions", sa.Column("superseded_by", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("cv_suggestions", "superseded_by")
    op.drop_column("cv_tailored_versions", "forked_from_markdown")
    op.drop_column("cv_tailored_versions", "forked_from_revision")

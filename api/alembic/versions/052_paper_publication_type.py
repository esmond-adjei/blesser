"""Store the publication type of saved and indexed papers.

Revision ID: 052_paper_publication_type
Revises: 051_paper_citations
"""

import sqlalchemy as sa

from alembic import op

revision = "052_paper_publication_type"
down_revision = "051_paper_citations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("papers", sa.Column("publication_type", sa.String(), nullable=True))
    op.add_column("index_papers", sa.Column("publication_type", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("index_papers", "publication_type")
    op.drop_column("papers", "publication_type")

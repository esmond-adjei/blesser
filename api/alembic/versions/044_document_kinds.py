"""document kinds and folders: CVs become one kind of document

Revision ID: 044_document_kinds
Revises: 043_assistant_queue
Create Date: 2026-10-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "044_document_kinds"
down_revision: str | Sequence[str] | None = "043_assistant_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_folders",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_document_folders_user_id", "document_folders", ["user_id"])
    op.add_column(
        "cv_documents",
        sa.Column("kind", sa.String(32), server_default="cv", nullable=False),
    )
    op.add_column(
        "cv_documents",
        sa.Column(
            "folder_id",
            sa.String(),
            sa.ForeignKey("document_folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_cv_documents_kind", "cv_documents", ["kind"])
    op.create_index("ix_cv_documents_folder_id", "cv_documents", ["folder_id"])


def downgrade() -> None:
    op.drop_index("ix_cv_documents_folder_id", table_name="cv_documents")
    op.drop_index("ix_cv_documents_kind", table_name="cv_documents")
    op.drop_column("cv_documents", "folder_id")
    op.drop_column("cv_documents", "kind")
    op.drop_index("ix_document_folders_user_id", table_name="document_folders")
    op.drop_table("document_folders")

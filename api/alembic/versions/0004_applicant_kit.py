"""Private applicant profiles, projects, documents and saved answers."""

import sqlalchemy as sa

from alembic import op

revision = "0004_applicant_kit"
down_revision = "0003"
branch_labels = None
depends_on = None


def owner():
    return sa.Column(
        "user_id",
        sa.String(),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


def timestamp(name):
    return sa.Column(name, sa.DateTime(), server_default=sa.func.now(), nullable=False)


def upgrade():
    op.create_table(
        "applicant_profiles",
        owner(),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("sensitive", sa.Text(), nullable=False),
        timestamp("updated_at"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "applicant_documents",
        sa.Column("id", sa.String(), primary_key=True),
        owner(),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False, unique=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        timestamp("created_at"),
    )
    op.create_index(
        "ix_applicant_documents_user_id", "applicant_documents", ["user_id"]
    )
    op.create_index(
        "uq_applicant_document_default",
        "applicant_documents",
        ["user_id", "kind"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_table(
        "applicant_projects",
        sa.Column("id", sa.String(), primary_key=True),
        owner(),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column(
            "logo_document_id",
            sa.String(),
            sa.ForeignKey("applicant_documents.id", ondelete="SET NULL"),
        ),
        timestamp("created_at"),
        timestamp("updated_at"),
    )
    op.create_index("ix_applicant_projects_user_id", "applicant_projects", ["user_id"])
    op.create_table(
        "applicant_document_projects",
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("applicant_documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("applicant_projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "applicant_answers",
        sa.Column("id", sa.String(), primary_key=True),
        owner(),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("applicant_projects.id", ondelete="SET NULL"),
        ),
        sa.Column("word_count", sa.Integer(), nullable=False),
        timestamp("updated_at"),
    )
    op.create_index("ix_applicant_answers_user_id", "applicant_answers", ["user_id"])
    op.create_index(
        "ix_applicant_answers_project_id", "applicant_answers", ["project_id"]
    )


def downgrade():
    for name in (
        "applicant_answers",
        "applicant_document_projects",
        "applicant_projects",
        "applicant_documents",
        "applicant_profiles",
    ):
        op.drop_table(name)

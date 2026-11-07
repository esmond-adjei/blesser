"""Opportunity catalogue, to-dos and calendar feeds; applications can track an opportunity.

Revision ID: 054_opportunities
Revises: 053_faculty_application_tool
"""

import sqlalchemy as sa

from alembic import op

revision = "054_opportunities"
down_revision = "053_faculty_application_tool"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("organization", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("eligibility", sa.Text(), nullable=False),
        sa.Column("benefits", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=False),
        sa.Column("countries", sa.JSON(), nullable=False),
        sa.Column("requirements", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("deadline", sa.String(), nullable=False),
        sa.Column("deadline_date", sa.Date(), nullable=True),
        sa.Column("rolling", sa.Boolean(), nullable=False),
        sa.Column("link", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("dedupe_key", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    for column in ("category", "created_by", "deadline_date", "kind", "run_id", "status"):
        op.create_index(f"ix_opportunities_{column}", "opportunities", [column])

    op.create_table(
        "todos",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.String(), nullable=True),
        sa.Column("application_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("application_id", "done", "due_date", "opportunity_id", "user_id"):
        op.create_index(f"ix_todos_{column}", "todos", [column])

    op.create_table(
        "calendar_feeds",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("token_hash"),
    )

    op.add_column("applications", sa.Column("opportunity_id", sa.String(), nullable=True))
    op.create_index("ix_applications_opportunity_id", "applications", ["opportunity_id"])
    op.create_foreign_key(
        "applications_opportunity_id_fkey",
        "applications",
        "opportunities",
        ["opportunity_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("applications_opportunity_id_fkey", "applications", type_="foreignkey")
    op.drop_index("ix_applications_opportunity_id", table_name="applications")
    op.drop_column("applications", "opportunity_id")
    op.drop_table("calendar_feeds")
    op.drop_table("todos")
    op.drop_table("opportunities")

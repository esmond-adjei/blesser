"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-09-21 01:40:23.225841

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=False),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("degree_level", sa.String(), nullable=False),
        sa.Column("interest_statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("interest_embedding", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "research_tasks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("target_name", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "done",
                "error",
                name="taskstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("log", sa.Text(), nullable=True),
        sa.Column("final_text", sa.Text(), nullable=True),
        sa.Column("turns", sa.Integer(), nullable=True),
        sa.Column("messages_json", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "schools",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("website_url", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "programs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("school_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("department_url", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["school_id"],
            ["schools.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tool_call_logs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["research_tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "professors",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("program_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("profile_url", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("openalex_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "program_id", "openalex_id", name="uq_professor_program_openalex"
        ),
    )
    op.create_table(
        "candidate_scores",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("professor_id", sa.String(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "discovered",
                "researched",
                "scored",
                "drafted",
                "approved",
                "rejected",
                "sent",
                name="candidatestatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["professor_id"],
            ["professors.id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "papers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("professor_id", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["professor_id"],
            ["professors.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "email_drafts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("candidate_id", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_scores.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("email_drafts")
    op.drop_table("papers")
    op.drop_table("candidate_scores")
    op.drop_table("professors")
    op.drop_table("tool_call_logs")
    op.drop_table("programs")
    op.drop_table("schools")
    op.drop_table("research_tasks")
    op.drop_table("runs")

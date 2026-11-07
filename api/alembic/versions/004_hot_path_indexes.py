"""hot-path indexes

Revision ID: 004
Revises: 003
Create Date: 2026-09-24 21:37:21.064658

"""

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | Sequence[str] | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_candidate_scores_professor_id"),
        "candidate_scores",
        ["professor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_candidate_scores_run_id"), "candidate_scores", ["run_id"], unique=False
    )
    op.create_index(
        op.f("ix_email_drafts_candidate_id"),
        "email_drafts",
        ["candidate_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_papers_professor_id"), "papers", ["professor_id"], unique=False
    )
    op.create_index(
        op.f("ix_professors_openalex_id"), "professors", ["openalex_id"], unique=False
    )
    op.create_index(
        op.f("ix_professors_program_id"), "professors", ["program_id"], unique=False
    )
    op.create_index(
        op.f("ix_programs_school_id"), "programs", ["school_id"], unique=False
    )
    op.create_index(
        op.f("ix_research_tasks_created_at"),
        "research_tasks",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_tasks_run_id"), "research_tasks", ["run_id"], unique=False
    )
    op.create_index(
        op.f("ix_research_tasks_status"), "research_tasks", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_research_tasks_target_id"),
        "research_tasks",
        ["target_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_tasks_task_type"),
        "research_tasks",
        ["task_type"],
        unique=False,
    )
    op.create_index(op.f("ix_schools_run_id"), "schools", ["run_id"], unique=False)
    op.create_index(
        op.f("ix_tool_call_logs_task_id"), "tool_call_logs", ["task_id"], unique=False
    )
    op.create_index(
        op.f("ix_worker_heartbeats_last_seen_at"),
        "worker_heartbeats",
        ["last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_worker_heartbeats_last_seen_at"), table_name="worker_heartbeats"
    )
    op.drop_index(op.f("ix_tool_call_logs_task_id"), table_name="tool_call_logs")
    op.drop_index(op.f("ix_schools_run_id"), table_name="schools")
    op.drop_index(op.f("ix_research_tasks_task_type"), table_name="research_tasks")
    op.drop_index(op.f("ix_research_tasks_target_id"), table_name="research_tasks")
    op.drop_index(op.f("ix_research_tasks_status"), table_name="research_tasks")
    op.drop_index(op.f("ix_research_tasks_run_id"), table_name="research_tasks")
    op.drop_index(op.f("ix_research_tasks_created_at"), table_name="research_tasks")
    op.drop_index(op.f("ix_programs_school_id"), table_name="programs")
    op.drop_index(op.f("ix_professors_program_id"), table_name="professors")
    op.drop_index(op.f("ix_professors_openalex_id"), table_name="professors")
    op.drop_index(op.f("ix_papers_professor_id"), table_name="papers")
    op.drop_index(op.f("ix_email_drafts_candidate_id"), table_name="email_drafts")
    op.drop_index(op.f("ix_candidate_scores_run_id"), table_name="candidate_scores")
    op.drop_index(
        op.f("ix_candidate_scores_professor_id"), table_name="candidate_scores"
    )

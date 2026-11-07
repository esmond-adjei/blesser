"""Add application saving to the original faculty task defaults.

Revision ID: 053_faculty_application_tool
Revises: 052_paper_publication_type
"""

from alembic import op

revision = "053_faculty_application_tool"
down_revision = "052_paper_publication_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE agent_tasks
        SET tools = (tools::jsonb || '["save_application"]'::jsonb)::json
        WHERE task_type = 'research_professor'
          AND tools::jsonb = '["search_web", "fetch_page", "spawn_professor_research", "confirm_no_match"]'::jsonb
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE agent_tasks
        SET tools = '["search_web", "fetch_page", "spawn_professor_research", "confirm_no_match"]'::json
        WHERE task_type = 'research_professor'
          AND tools::jsonb = '["search_web", "fetch_page", "spawn_professor_research", "confirm_no_match", "save_application"]'::jsonb
    """)

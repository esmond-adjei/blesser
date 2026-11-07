"""per-account data ownership, enforce

Revision ID: 016_account_ownership_enforce
Revises: 015_account_ownership
Create Date: 2026-10-14

Backfills here (the API boots with `upgrade head`, so there is no window
after 015): orphan rows go to the only account, else the upgrade refuses;
assign them with `python -m scripts.backfill_owner --email ...` and restart.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "016_account_ownership_enforce"
down_revision: str | Sequence[str] | None = "015_account_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNED_TABLES: tuple[str, ...] = (
    "runs",
    "research_tasks",
    "tool_call_logs",
    "schools",
    "programs",
    "professors",
    "papers",
    "candidate_scores",
    "email_drafts",
    "applications",
    "cv_documents",
    "cv_versions",
    "cv_branches",
    "cv_proposals",
    "assistant_conversations",
    "assistant_messages",
    "provider_configs",
    "agent_tools",
    "agent_tasks",
)

# Copied from scripts.backfill_owner.BACKFILL so the migration stays frozen. Parents first.
CHILD_PARENTS: tuple[tuple[str, str, str, str], ...] = (
    ("research_tasks", "runs", "run_id", "id"),
    ("schools", "runs", "run_id", "id"),
    ("candidate_scores", "runs", "run_id", "id"),
    ("tool_call_logs", "research_tasks", "task_id", "id"),
    ("programs", "schools", "school_id", "id"),
    ("email_drafts", "candidate_scores", "candidate_id", "id"),
    ("professors", "programs", "program_id", "id"),
    ("papers", "professors", "professor_id", "id"),
    ("cv_versions", "cv_documents", "document_id", "id"),
    ("cv_branches", "cv_documents", "document_id", "id"),
    ("cv_proposals", "cv_documents", "document_id", "id"),
    ("assistant_messages", "assistant_conversations", "conversation_id", "id"),
)


def _orphan_count(conn, table: str) -> int:
    return conn.execute(
        sa.text(f"SELECT COUNT(*) FROM {table} WHERE user_id IS NULL")
    ).scalar()


def _single_owner(conn) -> str | None:
    rows = conn.execute(
        sa.text("SELECT id FROM users ORDER BY created_at, id LIMIT 2")
    ).all()
    return rows[0][0] if len(rows) == 1 else None


def upgrade() -> None:
    bind = op.get_bind()
    orphans = {t: _orphan_count(bind, t) for t in OWNED_TABLES}
    total = sum(orphans.values())
    if total:
        owner = _single_owner(bind)
        if owner is None:
            details = ", ".join(f"{t}: {n}" for t, n in orphans.items() if n)
            raise RuntimeError(
                f"016_account_ownership_enforce: {total} row(s) have no owner "
                f"({details}) and the database does not hold exactly one "
                "account, so ownership is ambiguous. Assign them explicitly, "
                "then restart the API: cd api && uv run python -m "
                "scripts.backfill_owner --email you@example.com "
                "(add --create to also create that account)."
            )
        for table in OWNED_TABLES:
            if table in {c[0] for c in CHILD_PARENTS}:
                continue
            bind.execute(
                sa.text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
                {"uid": owner},
            )
        for table, parent, fk, pk in CHILD_PARENTS:
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET user_id = {parent}.user_id "
                    f"FROM {parent} "
                    f"WHERE {table}.{fk} = {parent}.{pk} "
                    f"AND {table}.user_id IS NULL"
                )
            )
    for table in OWNED_TABLES:
        op.alter_column(table, "user_id", existing_type=sa.String(), nullable=False)
    op.drop_constraint("provider_configs_pkey", "provider_configs", type_="primary")
    op.create_primary_key("provider_configs_pkey", "provider_configs", ["user_id", "provider"])
    op.drop_constraint("agent_tools_pkey", "agent_tools", type_="primary")
    op.create_primary_key("agent_tools_pkey", "agent_tools", ["user_id", "name", "scope"])
    op.drop_constraint("agent_tasks_pkey", "agent_tasks", type_="primary")
    op.create_primary_key("agent_tasks_pkey", "agent_tasks", ["user_id", "task_type"])


def downgrade() -> None:
    op.drop_constraint("agent_tasks_pkey", "agent_tasks", type_="primary")
    op.create_primary_key("agent_tasks_pkey", "agent_tasks", ["task_type"])
    op.drop_constraint("agent_tools_pkey", "agent_tools", type_="primary")
    op.create_primary_key("agent_tools_pkey", "agent_tools", ["name", "scope"])
    op.drop_constraint("provider_configs_pkey", "provider_configs", type_="primary")
    op.create_primary_key("provider_configs_pkey", "provider_configs", ["provider"])
    for table in reversed(OWNED_TABLES):
        op.alter_column(table, "user_id", existing_type=sa.String(), nullable=True)

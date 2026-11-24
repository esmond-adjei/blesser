"""System checks get their own scan kind, and every scan must name its kind."""

from alembic import op

revision = "0019_check_scan_kind"
down_revision = "0018_scan_kinds"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE scans SET kind = 'check' WHERE kind = 'member' AND ("
        "focus = 'Scheduled listing checks' OR focus LIKE 'Re-verify only %')"
    )
    op.alter_column("scans", "kind", server_default=None)


def downgrade():
    op.alter_column("scans", "kind", server_default="member")
    op.execute("UPDATE scans SET kind = 'member' WHERE kind = 'check'")

"""Scan schedules: scans that repeat. The catalogue sweep becomes the first staff schedule.

The old `sweep_hours` site setting, when above zero, turns into one staff schedule of
every category, and the setting row is removed.
"""

import json
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0015_scan_schedules"
down_revision = "0014_member_sources"
branch_labels = None
depends_on = None

CATEGORIES = ["startup", "research", "student"]


def _sweep_hours(bind) -> int:
    row = bind.execute(
        sa.text("SELECT value FROM site_settings WHERE key = 'sweep_hours'")
    ).first()
    if row is None:
        return 0
    value = row[0]
    if isinstance(value, str):
        value = json.loads(value)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def upgrade():
    op.create_table(
        "scan_schedules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("audience", sa.String(8), nullable=False),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(80), nullable=False, server_default=""),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("region", sa.String(120), nullable=False, server_default=""),
        sa.Column("focus", sa.Text(), nullable=False, server_default=""),
        sa.Column("sites", sa.JSON(), nullable=False),
        sa.Column("interval_hours", sa.Integer(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("pause_reason", sa.String(16), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column(
            "last_scan_id",
            sa.String(),
            sa.ForeignKey("scans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("empty_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("touched_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(audience = 'member' AND user_id IS NOT NULL) "
            "OR (audience = 'staff' AND user_id IS NULL)",
            name="ck_scan_schedules_owner",
        ),
    )
    op.create_index("ix_scan_schedules_user_id", "scan_schedules", ["user_id"])
    op.create_index("ix_scan_schedules_next_run_at", "scan_schedules", ["next_run_at"])
    op.add_column(
        "scans",
        sa.Column(
            "schedule_id",
            sa.String(),
            sa.ForeignKey("scan_schedules.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_scans_schedule_id", "scans", ["schedule_id"])
    op.add_column(
        "scan_finds",
        sa.Column("updated", sa.Boolean(), nullable=False, server_default="false"),
    )

    bind = op.get_bind()
    hours = _sweep_hours(bind)
    if hours > 0:
        now = datetime.now(UTC).replace(tzinfo=None)
        # The sweep ran when the sweep account's newest scan was older than the interval;
        # starting due keeps that: the first hourly pass applies the same rule.
        bind.execute(
            sa.text(
                "INSERT INTO scan_schedules (id, audience, name, categories, region, "
                "focus, sites, interval_hours, paused, next_run_at, runs, empty_runs, "
                "touched_at, created_at) VALUES (:id, 'staff', 'Catalogue sweep', "
                "CAST(:categories AS json), '', '', CAST('[]' AS json), :hours, false, :now, 0, 0, :now, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "categories": json.dumps(CATEGORIES),
                "hours": hours,
                "now": now,
            },
        )
    bind.execute(sa.text("DELETE FROM site_settings WHERE key = 'sweep_hours'"))


def downgrade():
    bind = op.get_bind()
    sweep = bind.execute(
        sa.text(
            "SELECT interval_hours FROM scan_schedules WHERE audience = 'staff' "
            "AND paused = false ORDER BY created_at LIMIT 1"
        )
    ).first()
    bind.execute(
        sa.text(
            "INSERT INTO site_settings (key, value) VALUES ('sweep_hours', CAST(:value AS json)) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {"value": json.dumps(sweep[0] if sweep else 0)},
    )
    op.drop_column("scan_finds", "updated")
    op.drop_index("ix_scans_schedule_id", table_name="scans")
    op.drop_column("scans", "schedule_id")
    op.drop_table("scan_schedules")

"""notifications: inbox, push subscriptions, preferences, deadline dates

Revision ID: 041_notifications
Revises: 040_cv_markdown
Create Date: 2026-10-20

"""

import logging
import re
from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa

from alembic import op

revision: str = "041_notifications"
down_revision: str | Sequence[str] | None = "040_cv_markdown"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")

#: Copy of api/applications/dates.py parse_deadline, frozen for this migration.
_MONTHS = {
    name: i + 1
    for i, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ]
    )
    for name in names
}
_ISO = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_DMY_NUMERIC = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")
_DAY_MONTH_YEAR = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)\.?,?\s+(\d{4})$")
_MONTH_DAY_YEAR = re.compile(r"^([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$")


def _make(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_deadline(text: str | None) -> date | None:
    raw = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not raw:
        return None
    if m := _ISO.match(raw):
        return _make(int(m[1]), int(m[2]), int(m[3]))
    if m := _DMY_NUMERIC.match(raw):
        first, second, year = int(m[1]), int(m[2]), int(m[3])
        if first > 12 >= second:
            return _make(year, second, first)
        if second > 12 >= first:
            return _make(year, first, second)
        return None
    if m := _DAY_MONTH_YEAR.match(raw):
        month = _MONTHS.get(m[2])
        return _make(int(m[3]), month, int(m[1])) if month else None
    if m := _MONTH_DAY_YEAR.match(raw):
        month = _MONTHS.get(m[1])
        return _make(int(m[3]), month, int(m[2])) if month else None
    return None


def _user_fk() -> sa.Column:
    return sa.Column(
        "user_id",
        sa.String(),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), primary_key=True),
        _user_fk(),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(500), server_default="", nullable=False),
        sa.Column("link", sa.String(500), server_default="", nullable=False),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("in_inbox", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("delivery", sa.String(64), nullable=True),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index(
        "ix_notifications_undelivered",
        "notifications",
        ["created_at"],
        postgresql_where=sa.text("delivered_at IS NULL"),
    )

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(), primary_key=True),
        _user_fk(),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(255), nullable=False),
        sa.Column("auth", sa.String(255), nullable=False),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_ok_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])

    op.create_table(
        "notification_preferences",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("channels", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("quiet_start", sa.String(5), nullable=True),
        sa.Column("quiet_end", sa.String(5), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("email_digest", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_digest_on", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    op.add_column("applications", sa.Column("deadline_date", sa.Date(), nullable=True))
    op.create_index("ix_applications_deadline_date", "applications", ["deadline_date"])

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, deadline FROM applications WHERE coalesce(deadline, '') <> ''")
    ).mappings().all()
    parsed = 0
    for row in rows:
        when = parse_deadline(row["deadline"])
        if when is None:
            continue
        bind.execute(
            sa.text("UPDATE applications SET deadline_date = :d WHERE id = :id"),
            {"d": when, "id": row["id"]},
        )
        parsed += 1
    log.info(
        "notifications: parsed %d of %d application deadline(s) to dates", parsed, len(rows)
    )


def downgrade() -> None:
    op.drop_index("ix_applications_deadline_date", table_name="applications")
    op.drop_column("applications", "deadline_date")
    op.drop_table("notification_preferences")
    op.drop_table("push_subscriptions")
    op.drop_table("notifications")

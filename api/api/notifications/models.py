"""Notification inbox rows, push subscriptions and per-account preferences.

Rows are created in the causing transaction (a rollback never notifies) and
delivered after commit. dedupe_key is unique per account.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.ids import new_id


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
        # The delivery loop's scan: only rows still waiting.
        Index(
            "ix_notifications_undelivered",
            "created_at",
            postgresql_where=text("delivered_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    # Push-safe wording: never CV text, draft content or professor details.
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(500), default="")
    # In-app path the notification opens (e.g. /runs/<id>).
    link: Mapped[str] = mapped_column(String(500), default="")
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(200))
    # False when the account turned the inbox off for this kind; the row
    # still exists so dedupe and push/email delivery work.
    in_inbox: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # How it went out: "push", "email", "push,email", "none" or "capped".
    delivery: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PushSubscription(Base):
    """One browser or device. The endpoint is the push service's URL for
    it; p256dh/auth encrypt the payload to that browser alone."""

    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # An endpoint belongs to one account; subscribing from another moves it.
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NotificationPreference(Base):
    """Per-account settings. channels is {kind: {channel: bool}}, holding
    only what differs from the defaults in events.KINDS."""

    __tablename__ = "notification_preferences"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    channels: Mapped[dict] = mapped_column(JSON, default=dict)
    # Quiet hours, "HH:MM" local time; push and email wait until the end.
    quiet_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    quiet_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # IANA name; NULL until the browser reports one (UTC meanwhile).
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # One email a day listing unread notifications (off by default).
    email_digest: Mapped[bool] = mapped_column(Boolean, default=False)
    last_digest_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

"""Personal to-dos and the private calendar feed that publishes them.

A to-do may point at an opportunity or a tracked application, so "Draft the
pitch deck" sits next to the deadline it serves. Everything here is private to
its owner (`user_id`).
"""

import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.ids import new_id
from api.core.secrets import EncryptedString


class TodoPriority(str, enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String)
    notes: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String, default=TodoPriority.normal.value)
    done: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Manual order within the list; lower first.
    position: Mapped[int] = mapped_column(Integer, default=0)
    opportunity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    application_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )


class CalendarFeed(Base):
    """One secret iCalendar subscription URL per account; rotating it revokes the old one."""

    __tablename__ = "calendar_feeds"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # sha256 of the URL token, for lookup; the token itself is stored encrypted
    # (core/secrets.py) so the URL can be shown again.
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    token: Mapped[str] = mapped_column(EncryptedString)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

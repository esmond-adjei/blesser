"""Application tracker: the opportunities a person is pursuing, and how far along they are."""

import enum
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.ids import new_id


class ApplicationStatus(str, enum.Enum):
    saved = "saved"
    preparing = "preparing"
    submitted = "submitted"
    interview = "interview"
    accepted = "accepted"
    rejected = "rejected"


#: Still working towards the deadline: reminders and the calendar feed cover these.
OPEN_STATUSES = (ApplicationStatus.saved.value, ApplicationStatus.preparing.value)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String)
    organization: Mapped[str] = mapped_column(String, default="")
    # Grant, fellowship, accelerator... free text so hand-added entries fit too.
    kind: Mapped[str] = mapped_column(String, default="")
    location: Mapped[str] = mapped_column(String, default="")
    link: Mapped[str] = mapped_column(String, default="")
    benefits: Mapped[str] = mapped_column(String, default="")
    # Checklist: [{"label": str, "done": bool}].
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    deadline: Mapped[str] = mapped_column(String, default="")
    # Schedulable copy of `deadline` (applications/dates.py); reminders run on this.
    deadline_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, default=ApplicationStatus.saved.value)
    notes: Mapped[str] = mapped_column(Text, default="")
    # The catalogue opportunity this tracks, when it came from there.
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

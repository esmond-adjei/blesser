"""Application tracker: grad applications, manual or agent-indexed.

Rows are keyed by school + program for upserts; agent saves only fill empty
fields so researcher edits are never clobbered.
"""

import enum
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.ids import new_id


class ApplicationStatus(str, enum.Enum):
    wishlist = "wishlist"
    applying = "applying"
    submitted = "submitted"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"


class ApplicationSource(str, enum.Enum):
    manual = "manual"
    agent = "agent"


class Application(Base):

    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    school: Mapped[str] = mapped_column(String, index=True)
    program: Mapped[str] = mapped_column(String, default="")
    degree_type: Mapped[str] = mapped_column(String, default="phd")
    location: Mapped[str] = mapped_column(String, default="")
    link: Mapped[str] = mapped_column(String, default="")
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    offer: Mapped[str] = mapped_column(Text, default="")
    deadline: Mapped[str] = mapped_column(String, default="")
    # Schedulable copy of `deadline` (applications/dates.py); reminders run on this.
    deadline_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, default=ApplicationStatus.wishlist.value)
    professors: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    fee_waiver: Mapped[bool] = mapped_column(Boolean, default=False)
    fee_waiver_notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String, default=ApplicationSource.manual.value)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id"), nullable=True, index=True
    )
    # What it is for in the index and workspace, when known.
    program_id: Mapped[str | None] = mapped_column(
        ForeignKey("programs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cycle_id: Mapped[str | None] = mapped_column(
        ForeignKey("admission_cycles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    match_id: Mapped[str | None] = mapped_column(
        ForeignKey("matches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The catalogue opportunity this application tracks (api/opportunities).
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Agent-saved rows inherit the triggering run's owner.
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

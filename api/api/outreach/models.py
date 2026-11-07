"""Outreach domain: email drafts. The system never sends email; sending is manual."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.db import Base
from api.core.ids import new_id

if TYPE_CHECKING:
    from api.candidates.models import CandidateScore


class EmailDraft(Base):
    __tablename__ = "email_drafts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_scores.id"), index=True
    )
    subject: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # The match it was written for; NULL until synced.
    match_id: Mapped[str | None] = mapped_column(
        ForeignKey("matches.id", ondelete="SET NULL"), nullable=True, index=True
    )

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    candidate: Mapped["CandidateScore"] = relationship(back_populates="draft")

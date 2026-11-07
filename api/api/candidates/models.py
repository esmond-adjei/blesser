"""Candidate domain: scored professors awaiting review."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.db import Base
from api.core.ids import new_id

if TYPE_CHECKING:
    from api.outreach.models import EmailDraft
    from api.prospects.models import Professor
    from api.runs.models import Run


class CandidateStatus(str, enum.Enum):
    discovered = "discovered"  # professor identified, not yet researched
    researched = "researched"  # papers pulled from OpenAlex
    scored = "scored"
    drafted = "drafted"
    approved = "approved"
    rejected = "rejected"
    sent = "sent"  # manually marked sent (system never sends)


class CandidateScore(Base):
    """One professor, scored and (eventually) drafted: the row you review."""

    __tablename__ = "candidate_scores"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    professor_id: Mapped[str] = mapped_column(ForeignKey("professors.id"), index=True)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=True)
    rationale: Mapped[str] = mapped_column(
        Text, nullable=True
    )  # why the agent thinks this is a match
    status: Mapped[str] = mapped_column(
        Enum(CandidateStatus, native_enum=False), default=CandidateStatus.discovered
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # The match this scoring belongs to; NULL until synced.
    match_id: Mapped[str | None] = mapped_column(
        ForeignKey("matches.id", ondelete="SET NULL"), nullable=True, index=True
    )

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    run: Mapped["Run"] = relationship(back_populates="candidates")
    professor: Mapped["Professor"] = relationship()
    draft: Mapped["EmailDraft"] = relationship(
        back_populates="candidate", uselist=False, cascade="all, delete-orphan"
    )

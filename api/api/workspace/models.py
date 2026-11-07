"""The workspace: what belongs to the student.

A match is the student × a professor × one interest statement; rescoring adds
to its history instead of making another match. Evidence points at index
papers, never copies. Overrides are the student's private corrections to
index facts.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.db import Base
from api.core.ids import new_id

#: Set by the student; candidate statuses map onto it (rejected is passed,
#: sent is contacted).
MATCH_STATUSES = ("shortlisted", "contacted", "passed")


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "professor_id", "interest_document_id", name="uq_match_interest"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    professor_id: Mapped[str] = mapped_column(
        ForeignKey("index_professors.id", ondelete="CASCADE"), index=True
    )
    interest_document_id: Mapped[str] = mapped_column(
        ForeignKey("cv_documents.id", ondelete="CASCADE"), index=True
    )
    # The latest score and its reasons; the history is in match_scores.
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="shortlisted", server_default="shortlisted"
    )
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    scores: Mapped[list["MatchScore"]] = relationship(
        back_populates="match", cascade="all, delete-orphan", order_by="MatchScore.scored_at"
    )


class MatchScore(Base):
    """One scoring of a match, by a run or a manual check."""

    __tablename__ = "match_scores"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    match_id: Mapped[str] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_scores.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    interest_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    match: Mapped[Match] = relationship(back_populates="scores")


class MatchEvidence(Base):
    """A paper the match rests on, in the index."""

    __tablename__ = "match_evidence"
    __table_args__ = (PrimaryKeyConstraint("match_id", "paper_id"),)

    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("index_papers.id", ondelete="CASCADE"), index=True
    )


class ShortlistEntry(Base):
    """A school on the student's list with their tier: a fact about the student."""

    __tablename__ = "school_shortlist"
    __table_args__ = (PrimaryKeyConstraint("user_id", "school_id"),)

    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


#: What an override can correct.
OVERRIDE_ENTITIES = ("professor", "affiliation", "school", "program", "cycle", "paper")


class IndexOverride(Base):
    """The student's correction to one index fact, shown only to them."""

    __tablename__ = "index_overrides"
    __table_args__ = (
        UniqueConstraint("user_id", "entity", "entity_id", "field", name="uq_index_override_field"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    entity: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[str] = mapped_column(String)
    field: Mapped[str] = mapped_column(String(64))
    value: Mapped[object] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

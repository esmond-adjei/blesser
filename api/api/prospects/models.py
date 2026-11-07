"""Prospect domain: Schools -> Programs -> Professors -> Papers."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.db import Base
from api.core.ids import new_id


class School(Base):
    __tablename__ = "schools"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    # Legacy, no longer written: run links are in RunSchool.
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String)
    country: Mapped[str] = mapped_column(String, nullable=True)
    website_url: Mapped[str] = mapped_column(String, nullable=True)
    # NULL shows the school's initials.
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # As first saved; per-run origin and tier, which caps count, are on RunSchool.
    origin: Mapped[str] = mapped_column(String(16), default="agent", server_default="agent")
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # A lookup that found nothing stores an empty list and no id.
    openalex_institution_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    institution_names: Mapped[str | None] = mapped_column(Text, nullable=True)

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    run_links: Mapped[list["RunSchool"]] = relationship(
        back_populates="school", cascade="all, delete-orphan"
    )
    programs: Mapped[list["Program"]] = relationship(
        back_populates="school", cascade="all, delete-orphan"
    )


class RunSchool(Base):
    """A run's use of one of the account's schools; run caps and tier shares count links."""

    __tablename__ = "run_schools"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    school_id: Mapped[str] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    found_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # "agent" spends the run's programme cap; "user" has a separate allowance.
    origin: Mapped[str] = mapped_column(String(16), default="agent", server_default="agent")
    # NULL for runs without tiers and for schools a person added.
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)

    school: Mapped["School"] = relationship(back_populates="run_links")


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    department_url: Mapped[str] = mapped_column(String, nullable=True)

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    school: Mapped["School"] = relationship(back_populates="programs")
    professors: Mapped[list["Professor"]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )


class Professor(Base):
    __tablename__ = "professors"

    # NULL openalex_ids stay distinct in Postgres, so only identified authors dedup.
    __table_args__ = (
        UniqueConstraint(
            "program_id", "openalex_id", name="uq_professor_program_openalex"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    profile_url: Mapped[str] = mapped_column(String, nullable=True)
    email: Mapped[str] = mapped_column(String, nullable=True)
    openalex_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    lab_name: Mapped[str | None] = mapped_column(String, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio_source: Mapped[str | None] = mapped_column(String, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    socials: Mapped[list] = mapped_column(JSON, default=list)
    # Its person in the index; NULL until synced.
    index_professor_id: Mapped[str | None] = mapped_column(
        ForeignKey("index_professors.id", ondelete="SET NULL"), nullable=True, index=True
    )

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    program: Mapped["Program"] = relationship(back_populates="professors")
    papers: Mapped[list["Paper"]] = relationship(
        back_populates="professor", cascade="all, delete-orphan"
    )


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    professor_id: Mapped[str] = mapped_column(ForeignKey("professors.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str] = mapped_column(Text, nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=True)
    url: Mapped[str] = mapped_column(String, nullable=True)
    citations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publication_type: Mapped[str | None] = mapped_column(String, nullable=True)
    # [{"name", "openalex_id"}] in byline order.
    coauthors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # The same paper in the index; NULL until synced.
    index_paper_id: Mapped[str | None] = mapped_column(
        ForeignKey("index_papers.id", ondelete="SET NULL"), nullable=True, index=True
    )

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    professor: Mapped["Professor"] = relationship(back_populates="papers")


class ProfessorIndex(Base):
    """A professor lookup kept for reuse (professor_index.py). Never shared;
    outlives the run, school and programme (their ids go NULL)."""

    __tablename__ = "professor_index"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "school_key", "name_key", name="uq_professor_index_school_name"
        ),
        Index("ix_professor_index_user_openalex", "user_id", "openalex_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String)
    name_key: Mapped[str] = mapped_column(String)
    school_id: Mapped[str | None] = mapped_column(
        ForeignKey("schools.id", ondelete="SET NULL"), nullable=True, index=True
    )
    school_name: Mapped[str] = mapped_column(String)
    school_key: Mapped[str] = mapped_column(String)
    program_id: Mapped[str | None] = mapped_column(
        ForeignKey("programs.id", ondelete="SET NULL"), nullable=True
    )
    program_name: Mapped[str | None] = mapped_column(String, nullable=True)
    openalex_id: Mapped[str] = mapped_column(String)
    # As find_openalex_author returned it, so a reuse is grounded like a lookup.
    author: Mapped[dict] = mapped_column(JSON, default=dict)
    works: Mapped[list] = mapped_column(JSON, default=list)
    profile_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # "match" | "no_match"; the score is against that run's interests, so not reused.
    outcome: Mapped[str] = mapped_column(String(16))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    looked_up_at: Mapped[datetime] = mapped_column(DateTime)
    # Its person in the index; NULL until synced.
    index_professor_id: Mapped[str | None] = mapped_column(
        ForeignKey("index_professors.id", ondelete="SET NULL"), nullable=True, index=True
    )


class ProfessorOptOut(Base):
    """Not owned by an account: an opt-out applies to every account."""

    __tablename__ = "professor_optouts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    openalex_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # "name|school", for people without an OpenAlex id.
    name_key: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OpenAlexResponse(Base):
    """Successful public-API responses shared across accounts and workers.
    Public data only; other sources' keys start with their name."""

    __tablename__ = "openalex_responses"

    key: Mapped[str] = mapped_column(Text, primary_key=True)  # path?sorted params
    body: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class FacultyRoster(Base):
    """A department's faculty names, shared across accounts; public data only."""

    __tablename__ = "faculty_rosters"

    key: Mapped[str] = mapped_column(Text, primary_key=True)  # host + path
    names: Mapped[str] = mapped_column(Text)  # JSON list of names, page order
    source: Mapped[str] = mapped_column(String)  # "page" | "agent"
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)

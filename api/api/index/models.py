"""The index: public facts about the academic world.

Schools and programmes are the existing per-account rows; this adds
professors (once per account), affiliations, papers and admission cycles.
No column here is personal: the student's view lives in the workspace
(api/workspace/models.py). Every fact records its source and fetch time.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
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


class IndexProfessor(Base):
    """One person per account, identified by OpenAlex author id when known, else
    by name at a school."""

    __tablename__ = "index_professors"
    __table_args__ = (
        UniqueConstraint("user_id", "openalex_id", name="uq_index_professor_openalex"),
        Index("ix_index_professors_user_name", "user_id", "name_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String)
    # Normalized name, for matching a lead to a known person.
    name_key: Mapped[str] = mapped_column(String)
    # Identity: short OpenAlex id ("A123"), ORCID iD, DBLP person id.
    openalex_id: Mapped[str | None] = mapped_column(String, nullable=True)
    orcid: Mapped[str | None] = mapped_column(String(19), nullable=True)
    dblp_pid: Mapped[str | None] = mapped_column(String, nullable=True)
    homepage_url: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    lab_name: Mapped[str | None] = mapped_column(String, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    socials: Mapped[list] = mapped_column(JSON, default=list)
    # Where each field came from: {field: {"source", "url", "fetched_at"}}.
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # When the profile (bio, links, photo) and the works were last fetched.
    profile_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    works_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    affiliations: Mapped[list["Affiliation"]] = relationship(
        back_populates="professor", cascade="all, delete-orphan"
    )


class Affiliation(Base):
    """A professor's place at a school; one person can hold several. Until
    departments get rows, the programme's department page stands in."""

    __tablename__ = "professor_affiliations"
    __table_args__ = (
        UniqueConstraint(
            "professor_id", "school_id", "program_id", name="uq_affiliation_place"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    professor_id: Mapped[str] = mapped_column(
        ForeignKey("index_professors.id", ondelete="CASCADE"), index=True
    )
    school_id: Mapped[str] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    program_id: Mapped[str | None] = mapped_column(
        ForeignKey("programs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    department: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime)

    professor: Mapped[IndexProfessor] = relationship(back_populates="affiliations")


class IndexPaper(Base):
    """A paper, stored once per account and linked to its authors."""

    __tablename__ = "index_papers"
    __table_args__ = (UniqueConstraint("user_id", "work_key", name="uq_index_paper_work"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # What makes two records the same paper: "doi:…", "openalex:W…", or
    # "title:<normalized title>|<year>" (api/index/keys.py).
    work_key: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String, nullable=True)
    publication_type: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    doi: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class PaperAuthor(Base):
    __tablename__ = "paper_authors"
    __table_args__ = (PrimaryKeyConstraint("paper_id", "professor_id"),)

    paper_id: Mapped[str] = mapped_column(ForeignKey("index_papers.id", ondelete="CASCADE"))
    professor_id: Mapped[str] = mapped_column(
        ForeignKey("index_professors.id", ondelete="CASCADE"), index=True
    )


class AdmissionCycle(Base):
    """One intake of a programme: deadline, funding, link, status, last check."""

    __tablename__ = "admission_cycles"
    __table_args__ = (UniqueConstraint("program_id", "term", name="uq_admission_cycle_term"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    program_id: Mapped[str] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    # The intake as the programme names it: "Fall 2027".
    term: Mapped[str] = mapped_column(String(64))
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    funding: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    # "open", "closed" or "unknown".
    status: Mapped[str] = mapped_column(String(16), default="unknown", server_default="unknown")
    source: Mapped[str] = mapped_column(String(32))
    checked_at: Mapped[datetime] = mapped_column(DateTime)

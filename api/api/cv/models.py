"""Document tables: base documents, tailored versions, suggestions and
folders. They keep their cv_ names: a CV was the first kind of document.
Deletes are explicit and bottom-up (the runs convention)."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.ids import new_id

#: What a document is. Outreach emails are not documents: they live in
#: the Outbox as drafts.
DOCUMENT_KINDS = ("cv", "sop", "diversity_statement", "research_proposal", "interest", "note")


class DocumentFolder(Base):
    """One level of folders; a folder holds no text."""

    __tablename__ = "document_folders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )


class CvDocument(Base):
    """A base document (a CV, a statement of purpose, ...): the facts
    every tailored version starts from."""

    __tablename__ = "cv_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String)
    # One of DOCUMENT_KINDS.
    kind: Mapped[str] = mapped_column(String(32), default="cv", server_default="cv", index=True)
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # What was uploaded: "docx", "pdf", "md" or "txt" ("md" also for a CV
    # written in the editor from scratch).
    format: Mapped[str] = mapped_column(String, default="docx")
    status: Mapped[str] = mapped_column(String, default="ready")
    original_sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # The uploaded file, kept read-only for download; NULL when there was
    # none. Relative to settings.cv_storage_dir.
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Bumped on every write, so a save or an accepted suggestion based on
    # an older text is refused (409) instead of overwriting newer edits.
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Optional limits; NULL is none.
    word_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )


class CvTailoredVersion(Base):
    """A named copy of the base CV tailored for one professor (or an
    application), e.g. "CV for reinforcement learning"."""

    __tablename__ = "cv_tailored_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("cv_documents.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    markdown: Mapped[str] = mapped_column(Text, default="", server_default="")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # What it was tailored for. Kept when the target is deleted, so the
    # version survives a deleted run.
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_scores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    professor_id: Mapped[str | None] = mapped_column(
        ForeignKey("professors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    application_id: Mapped[str | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Shown even after the professor row is gone.
    target_label: Mapped[str | None] = mapped_column(String, nullable=True)
    # The base revision at fork time; base changes reach the version only as
    # suggestions the student asks for.
    forked_from_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forked_from_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional limits; NULL is none. A version without one uses its base's.
    word_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )


class CvSuggestion(Base):
    """One proposed change to a CV's text: replace `find` with `replace`.
    Nothing changes until the student accepts it (optionally edited)."""

    __tablename__ = "cv_suggestions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("cv_documents.id", ondelete="CASCADE"), index=True
    )
    # The tailored version it changes; NULL for the base CV itself.
    version_id: Mapped[str | None] = mapped_column(
        ForeignKey("cv_tailored_versions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    find: Mapped[str] = mapped_column(Text)
    replace: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Words the change adds that the base CV never mentions (see
    # api/cv/claims.py): {"passed": bool, "new_terms": [...]}.
    claim_check: Mapped[dict] = mapped_column(JSON, default=dict)
    # On a document with a limit: whether this change keeps it within
    # (service._limit_checks). NULL when there is no limit.
    limit_check: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # "pending" | "accepted" | "rejected" | "stale". Stale: its `find` no
    # longer occurs exactly once in the text, so it can't be applied.
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # The fresh suggestion asked for in place of this stale one.
    superseded_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String(16), default="assistant")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

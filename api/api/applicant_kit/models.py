from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.applicant_kit.encryption import EncryptedSensitive
from api.core.db import Base
from api.core.ids import new_id


class Profile(Base):
    __tablename__ = "applicant_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    sensitive: Mapped[dict] = mapped_column(EncryptedSensitive, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Project(Base):
    __tablename__ = "applicant_projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    logo_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("applicant_documents.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Document(Base):
    __tablename__ = "applicant_documents"
    __table_args__ = (
        Index(
            "uq_applicant_document_default",
            "user_id",
            "kind",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    filename: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String, unique=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DocumentProject(Base):
    __tablename__ = "applicant_document_projects"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("applicant_documents.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("applicant_projects.id", ondelete="CASCADE"), primary_key=True
    )


class Answer(Base):
    __tablename__ = "applicant_answers"
    __table_args__ = (
        Index(
            "ix_applicant_answers_normalized_question",
            "normalized_question",
            postgresql_using="gin",
            postgresql_ops={"normalized_question": "gin_trgm_ops"},
        ),
    )

    normalized_question: Mapped[str] = mapped_column(Text, default="")

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("applicant_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    word_count: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

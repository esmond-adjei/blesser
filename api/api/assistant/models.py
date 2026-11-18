from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.ids import new_id


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(80))
    private_context: Mapped[bool] = mapped_column(default=False)
    pending: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    turn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    turn_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (
        Index(
            "ix_assistant_messages_thread", "conversation_id", "position", unique=True
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE")
    )
    position: Mapped[int]
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    trace: Mapped[list[dict]] = mapped_column(JSON, default=list)
    sources: Mapped[list[dict]] = mapped_column(JSON, default=list)
    cited_deadlines: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

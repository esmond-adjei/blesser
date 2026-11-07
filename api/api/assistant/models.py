"""Gradis conversation tables: conversations (provider-format history and
any unconfirmed write call) and messages (the transcript the UI renders)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.db import Base
from api.core.ids import new_id


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String, default="New Gradis chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Provider-format history (JSON list) so later turns see earlier tool results.
    history_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Unconfirmed write call awaiting the user: {"id", "name", "arguments",
    # "text"} plus its history. Null when none is outstanding.
    pending_call_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    messages: Mapped[list["AssistantMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        String, ForeignKey("assistant_conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    # The turn's ordered log (text and tool calls), shaped like a run task's
    # `log`. Full payloads are intentionally not kept.
    tool_calls_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The model that wrote an assistant reply; None for user messages and older replies.
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Owner, copied from the conversation.
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    conversation: Mapped[AssistantConversation] = relationship(
        back_populates="messages"
    )


class AssistantQueueItem(Base):
    """A prompt sent while Gradis was working: answered after the turn, or
    handed to the running turn at its next decision point when urgent."""

    __tablename__ = "assistant_queue"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        String, ForeignKey("assistant_conversations.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    # Urgent: hand it to the running turn instead of waiting for it.
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Owner, copied from the conversation.
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    conversation: Mapped[AssistantConversation] = relationship()

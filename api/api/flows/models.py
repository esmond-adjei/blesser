"""User-defined agent flows."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.ids import new_id


class AgentFlow(Base):
    """A user's copy of a built-in flow, with per-step changes."""

    __tablename__ = "agent_flows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    base: Mapped[str] = mapped_column(String(32), default="standard")
    # [{"type": str, "enabled": bool, "tool_groups": [..], "tools": [..], "instructions": str}]
    steps: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

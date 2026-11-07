"""Provider registry: per-account model selection and BYO keys.

Work uses the system model unless a run or chat picks a row, or the account
opted in to its default row. Keys are never returned by any endpoint.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.secrets import EncryptedString


class ProviderConfig(Base):
    __tablename__ = "provider_configs"

    # Per-account keys: one row per (account, provider).
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String, primary_key=True)
    model: Mapped[str] = mapped_column(String, default="")
    # Encrypted at rest (api/core/secrets.py); reads return plaintext.
    api_key: Mapped[str] = mapped_column(EncryptedString, default="")
    base_url: Mapped[str] = mapped_column(String, default="")
    # Context window in tokens for the chat usage bar; None when unset.
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The account's default own model, used for unset choices only with
    # users.prefer_own_model.
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    # Switched off rows keep their details but are never used.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

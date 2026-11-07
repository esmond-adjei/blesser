"""Auth domain: users, rotating refresh grants and emailed tokens (hashes only)."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.ids import new_id


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    # Avatar is a server re-encoded WebP served by avatar_key (see auth/profile.py).
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    avatar_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    # NULL until the address is proven via an emailed link.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Which Terms + Privacy notice the account agreed to at sign-up.
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terms_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Billing plan id (api/billing/plans.py); set by billing at launch.
    plan: Mapped[str] = mapped_column(String(16), default="free", server_default="free")
    # When the account picked its plan; NULL = not yet (onboarding asks).
    plan_selected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Unset model choices use the system model (Auto) unless this is on;
    # then they use the account's default own model.
    prefer_own_model: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    # Gradis runs every change without an approval card when on.
    agent_full_access: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RefreshToken(Base):
    """One active refresh grant. Rotation deletes the presented row and
    issues a fresh one; logout deletes it. Only hashes are stored."""

    __tablename__ = "auth_refresh_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EmailToken(Base):
    """Single-use emailed link (password reset or email verification).
    Only the SHA-256 hash is stored; used_at marks consumption."""

    __tablename__ = "auth_email_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UserIdentity(Base):
    """A third-party sign-in (Google, ...) attached to one account."""

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_user_identities_provider_subject"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

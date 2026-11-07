"""Usage rollups: one row per (account, day, feature, provider, model)."""

from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base


class UsageDaily(Base):
    __tablename__ = "usage_daily"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    feature: Mapped[str] = mapped_column(String(32), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    model: Mapped[str] = mapped_column(String(128), primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)

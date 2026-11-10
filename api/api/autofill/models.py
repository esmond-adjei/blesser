from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base


class DailyUsage(Base):
    __tablename__ = "autofill_daily_usage"
    __table_args__ = (CheckConstraint("drafted_fields >= 0", name="ck_autofill_usage"),)

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    drafted_fields: Mapped[int] = mapped_column(Integer, default=0)

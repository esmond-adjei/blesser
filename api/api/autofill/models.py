from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.applicant_kit.encryption import EncryptedSensitive
from api.core.db import Base
from api.core.ids import new_id


class DailyUsage(Base):
    __tablename__ = "autofill_daily_usage"
    __table_args__ = (CheckConstraint("drafted_fields >= 0", name="ck_autofill_usage"),)

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    drafted_fields: Mapped[int] = mapped_column(Integer, default=0)


class Correction(Base):
    __tablename__ = "autofill_corrections"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "host", "label_key", "field_type", name="uq_autofill_correction"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    host: Mapped[str] = mapped_column(String(253))
    label: Mapped[str] = mapped_column(String(4000))
    label_key: Mapped[str] = mapped_column(String(64))
    field_type: Mapped[str] = mapped_column(String(50))
    descriptor: Mapped[dict] = mapped_column(JSON)
    filled: Mapped[dict] = mapped_column(EncryptedSensitive)
    value: Mapped[str | list | None] = mapped_column(EncryptedSensitive, nullable=True)
    wrong_field: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class FormReport(Base):
    __tablename__ = "autofill_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    page: Mapped[dict] = mapped_column(JSON)
    fields: Mapped[list] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(String(4000))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

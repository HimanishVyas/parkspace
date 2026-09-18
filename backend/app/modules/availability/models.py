import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin

MINUTES_PER_DAY = 24 * 60


class AvailabilityRule(UUIDPkMixin, TimestampMixin, Base):
    """A recurring weekly window during which the space may be booked.

    Times are minutes from local midnight (0..1440), which lets a rule end at
    exactly midnight — something a TIME column cannot express. A window that
    crosses midnight is stored as two rules, one per day.
    """

    __tablename__ = "availability_rules"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="day_of_week_range"),
        CheckConstraint("start_minute >= 0 AND start_minute < 1440", name="start_minute_range"),
        CheckConstraint("end_minute > 0 AND end_minute <= 1440", name="end_minute_range"),
        CheckConstraint("end_minute > start_minute", name="end_after_start"),
        Index("ix_availability_rules_space_day", "parking_space_id", "day_of_week"),
    )

    parking_space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parking_spaces.id", ondelete="CASCADE"), index=True
    )
    # 0 = Monday ... 6 = Sunday (matches datetime.weekday()).
    day_of_week: Mapped[int] = mapped_column(Integer)
    start_minute: Mapped[int] = mapped_column(Integer)
    end_minute: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AvailabilityBlock(UUIDPkMixin, TimestampMixin, Base):
    """An explicit period during which the space is unavailable, overriding the
    weekly rules (holidays, maintenance, owner needs the spot)."""

    __tablename__ = "availability_blocks"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="end_after_start"),
        Index("ix_availability_blocks_space_window", "parking_space_id", "start_at", "end_at"),
    )

    parking_space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parking_spaces.id", ondelete="CASCADE"), index=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(200))

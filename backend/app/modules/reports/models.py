import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin, str_enum


class IssueType(str, enum.Enum):
    SPACE_UNAVAILABLE = "SPACE_UNAVAILABLE"
    SPACE_OCCUPIED = "SPACE_OCCUPIED"
    ACCESS_PROBLEM = "ACCESS_PROBLEM"
    PROPERTY_DAMAGE = "PROPERTY_DAMAGE"
    PAYMENT_PROBLEM = "PAYMENT_PROBLEM"
    OTHER = "OTHER"


class ReportStatus(str, enum.Enum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class Report(UUIDPkMixin, TimestampMixin, Base):
    """An issue raised against a booking by either party.

    V1 is a reporting and record-keeping mechanism only: the platform reviews
    reports but makes no compensation or insurance promise.
    """

    __tablename__ = "reports"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    issue_type: Mapped[IssueType] = mapped_column(str_enum(IssueType), index=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[ReportStatus] = mapped_column(str_enum(ReportStatus), default=ReportStatus.OPEN, index=True)
    admin_notes: Mapped[str | None] = mapped_column(Text)
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    photos: Mapped[list["ReportPhoto"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", lazy="selectin"
    )


class ReportPhoto(UUIDPkMixin, TimestampMixin, Base):
    """Photo evidence attached to a report."""

    __tablename__ = "report_photos"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(500))

    report: Mapped[Report] = relationship(back_populates="photos")

import enum
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin, str_enum


class ReviewSubject(str, enum.Enum):
    """Who is being reviewed: the parking space (renter -> provider) or the
    renter (provider -> renter)."""

    SPACE = "SPACE"
    RENTER = "RENTER"


class Review(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        # One review per booking per direction.
        Index("uq_reviews_booking_subject", "booking_id", "subject", unique=True),
        Index("ix_reviews_space_created", "parking_space_id", "created_at"),
    )

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    subject: Mapped[ReviewSubject] = mapped_column(str_enum(ReviewSubject))
    # Set when subject == SPACE.
    parking_space_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parking_spaces.id", ondelete="CASCADE")
    )
    # Set when subject == RENTER.
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)

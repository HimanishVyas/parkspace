"""Ratings for completed bookings (PRD §23).

Deliberately minimal: one rating per booking per direction, only after the
booking has actually happened, and the listing's average is kept denormalised so
search and listing pages never aggregate on read.
"""
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, Forbidden, NotFound
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.parking.models import ParkingSpace
from app.modules.providers.models import Provider
from app.modules.reviews.models import Review, ReviewSubject
from app.modules.reviews.schemas import ReviewCreate
from app.modules.users.models import User

# Only a booking that ran can be reviewed.
REVIEWABLE_STATUSES = (BookingStatus.COMPLETED,)


async def create(db: AsyncSession, author: User, data: ReviewCreate) -> Review:
    booking = await db.get(Booking, data.booking_id)
    if booking is None:
        raise NotFound("Booking not found")
    if booking.status not in REVIEWABLE_STATUSES:
        raise Conflict("You can review a booking once it is completed", code="NOT_REVIEWABLE")

    provider = await db.get(Provider, booking.provider_id)
    is_renter = booking.renter_id == author.id
    is_provider = provider is not None and provider.user_id == author.id
    if not (is_renter or is_provider):
        raise Forbidden("You were not part of this booking")

    subject = ReviewSubject.SPACE if is_renter else ReviewSubject.RENTER
    duplicate = await db.scalar(
        select(Review.id).where(Review.booking_id == booking.id, Review.subject == subject)
    )
    if duplicate:
        raise Conflict("You have already reviewed this booking", code="ALREADY_REVIEWED")

    review = Review(
        booking_id=booking.id,
        author_id=author.id,
        subject=subject,
        rating=data.rating,
        comment=(data.comment or "").strip() or None,
        parking_space_id=booking.parking_space_id if subject == ReviewSubject.SPACE else None,
        target_user_id=booking.renter_id if subject == ReviewSubject.RENTER else None,
    )
    db.add(review)
    await db.flush()
    if subject == ReviewSubject.SPACE:
        await refresh_space_rating(db, booking.parking_space_id)
    return review


async def refresh_space_rating(db: AsyncSession, parking_space_id: uuid.UUID) -> None:
    row = (
        await db.execute(
            select(func.avg(Review.rating), func.count()).where(
                Review.parking_space_id == parking_space_id, Review.subject == ReviewSubject.SPACE
            )
        )
    ).one()
    space = await db.get(ParkingSpace, parking_space_id)
    if space is None:
        return
    space.rating_average = Decimal(row[0]).quantize(Decimal("0.01")) if row[0] is not None else None
    space.rating_count = int(row[1])
    await db.flush()


async def for_space(
    db: AsyncSession, parking_space_id: uuid.UUID, limit: int = 20, offset: int = 0
) -> tuple[list[tuple[Review, str]], Decimal | None, int]:
    rows = (
        await db.execute(
            select(Review, User.full_name)
            .join(User, User.id == Review.author_id)
            .where(Review.parking_space_id == parking_space_id, Review.subject == ReviewSubject.SPACE)
            .order_by(Review.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    aggregate = (
        await db.execute(
            select(func.avg(Review.rating), func.count()).where(
                Review.parking_space_id == parking_space_id, Review.subject == ReviewSubject.SPACE
            )
        )
    ).one()
    average = Decimal(aggregate[0]).quantize(Decimal("0.01")) if aggregate[0] is not None else None
    return [(row[0], row[1]) for row in rows], average, int(aggregate[1])


def display_name(full_name: str) -> str:
    """Reviews show a first name and an initial, not a full identity."""
    parts = full_name.strip().split()
    if not parts:
        return "Anonymous"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}."

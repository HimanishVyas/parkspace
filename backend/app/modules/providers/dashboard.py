"""Provider and society dashboard figures (PRD §16, §29).

Earnings are read straight off the bookings, whose money columns were frozen at
booking time — so a change to the commission setting never rewrites what a
provider was already told they earned.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import local_tz, utcnow
from app.modules.bookings.models import BLOCKING_STATUSES, Booking, BookingStatus
from app.modules.parking.models import ListingStatus, ParkingSpace
from app.modules.payments.models import Payout, PayoutBooking, PayoutStatus

ZERO = Decimal("0.00")

# Bookings that count as money the provider has genuinely earned.
EARNED_STATUSES = (BookingStatus.COMPLETED,)
# ...and money that is committed but not yet delivered.
EXPECTED_STATUSES = (BookingStatus.CONFIRMED, BookingStatus.ACTIVE)


@dataclass
class EarningsSummary:
    gross_booking_value: Decimal
    platform_fee: Decimal
    provider_earnings: Decimal
    booking_count: int


@dataclass
class ProviderDashboard:
    total_earnings: Decimal
    pending_payout: Decimal
    completed_payout: Decimal
    upcoming_earnings: Decimal
    current_month: EarningsSummary
    total_listings: int
    active_listings: int
    upcoming_bookings: int
    todays_bookings: int
    total_bookings: int


def month_bounds(moment: datetime | None = None) -> tuple[datetime, datetime]:
    """First and last instant of the local month containing `moment`."""
    tz = local_tz()
    local_now = (moment or utcnow()).astimezone(tz)
    start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


async def _sum(db: AsyncSession, column, *conditions) -> Decimal:
    value = await db.scalar(select(func.coalesce(func.sum(column), 0)).where(and_(*conditions)))
    return Decimal(value or 0).quantize(Decimal("0.01"))


async def earnings_between(
    db: AsyncSession, provider_id: uuid.UUID, start: datetime, end: datetime
) -> EarningsSummary:
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Booking.base_amount), 0),
                func.coalesce(func.sum(Booking.commission_amount), 0),
                func.coalesce(func.sum(Booking.provider_earning), 0),
                func.count(),
            ).where(
                Booking.provider_id == provider_id,
                Booking.status.in_(EARNED_STATUSES + EXPECTED_STATUSES),
                Booking.start_at >= start,
                Booking.start_at < end,
            )
        )
    ).one()
    return EarningsSummary(
        gross_booking_value=Decimal(row[0]).quantize(Decimal("0.01")),
        platform_fee=Decimal(row[1]).quantize(Decimal("0.01")),
        provider_earnings=Decimal(row[2]).quantize(Decimal("0.01")),
        booking_count=int(row[3]),
    )


async def build(db: AsyncSession, provider_id: uuid.UUID) -> ProviderDashboard:
    now = utcnow()
    month_start, month_end = month_bounds(now)
    tz = local_tz()
    today_start = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)

    total_earnings = await _sum(
        db, Booking.provider_earning, Booking.provider_id == provider_id, Booking.status.in_(EARNED_STATUSES)
    )
    upcoming_earnings = await _sum(
        db,
        Booking.provider_earning,
        Booking.provider_id == provider_id,
        Booking.status.in_(EXPECTED_STATUSES),
    )

    paid_out = await _sum(
        db, Payout.amount, Payout.provider_id == provider_id, Payout.status == PayoutStatus.PAID
    )
    # Anything earned but not yet attached to a completed payout.
    settled = await db.scalar(
        select(func.coalesce(func.sum(Booking.provider_earning), 0))
        .select_from(Booking)
        .join(PayoutBooking, PayoutBooking.booking_id == Booking.id)
        .join(Payout, Payout.id == PayoutBooking.payout_id)
        .where(Booking.provider_id == provider_id, Payout.status == PayoutStatus.PAID)
    )
    pending_payout = (total_earnings - Decimal(settled or 0)).quantize(Decimal("0.01"))

    total_listings = await db.scalar(
        select(func.count()).select_from(ParkingSpace).where(ParkingSpace.provider_id == provider_id)
    )
    active_listings = await db.scalar(
        select(func.count())
        .select_from(ParkingSpace)
        .where(ParkingSpace.provider_id == provider_id, ParkingSpace.status == ListingStatus.PUBLISHED)
    )
    upcoming_bookings = await db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.provider_id == provider_id,
            Booking.status.in_(BLOCKING_STATUSES),
            Booking.end_at > now,
        )
    )
    todays_bookings = await db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(Booking.provider_id == provider_id, Booking.created_at >= today_start)
    )
    total_bookings = await db.scalar(
        select(func.count()).select_from(Booking).where(Booking.provider_id == provider_id)
    )

    return ProviderDashboard(
        total_earnings=total_earnings,
        pending_payout=max(pending_payout, ZERO),
        completed_payout=paid_out,
        upcoming_earnings=upcoming_earnings,
        current_month=await earnings_between(db, provider_id, month_start, month_end),
        total_listings=int(total_listings or 0),
        active_listings=int(active_listings or 0),
        upcoming_bookings=int(upcoming_bookings or 0),
        todays_bookings=int(todays_bookings or 0),
        total_bookings=int(total_bookings or 0),
    )


async def monthly_breakdown(db: AsyncSession, provider_id: uuid.UUID, months: int = 6) -> list[dict]:
    """Earnings per calendar month, newest first — the provider's earnings table."""
    month_column = func.date_trunc("month", func.timezone(local_tz().key, Booking.start_at)).label("month")
    rows = (
        await db.execute(
            select(
                month_column,
                func.coalesce(func.sum(Booking.base_amount), 0),
                func.coalesce(func.sum(Booking.commission_amount), 0),
                func.coalesce(func.sum(Booking.provider_earning), 0),
                func.count(),
            )
            .where(
                Booking.provider_id == provider_id,
                Booking.status.in_(EARNED_STATUSES + EXPECTED_STATUSES),
            )
            .group_by(month_column)
            .order_by(month_column.desc())
            .limit(months)
        )
    ).all()
    return [
        {
            "month": row[0].strftime("%Y-%m"),
            "gross_booking_value": Decimal(row[1]).quantize(Decimal("0.01")),
            "platform_fee": Decimal(row[2]).quantize(Decimal("0.01")),
            "provider_earnings": Decimal(row[3]).quantize(Decimal("0.01")),
            "booking_count": int(row[4]),
        }
        for row in rows
    ]

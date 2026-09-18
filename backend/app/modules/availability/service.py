"""Availability rules: when a space can be booked.

Semantics (V1)
--------------
A provider describes availability as recurring weekly windows plus explicit
blocks. How a booking is checked against them depends on its duration type:

* ``HOURLY``  - the requested window must fall entirely inside the weekly
  availability windows, to the minute.
* ``DAILY`` / ``MONTHLY`` - every calendar date the booking touches must be an
  *operating day* (the space has at least one active rule for that weekday).
  The booking then reserves the whole contiguous period, including overnight,
  because that is what renting a spot by the day or month means.

A provider who wants to sell monthly parking on a space that is only open on
weekdays therefore has to open the weekend too — which is the honest answer,
since a renter paying for October should not find the gate shut on a Sunday.

All rule times are minutes from local midnight in ``settings.timezone``; the
pilot city has no DST, so local dates map cleanly onto wall-clock windows.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import local_tz
from app.modules.availability.models import MINUTES_PER_DAY, AvailabilityBlock, AvailabilityRule
from app.modules.parking.models import ParkingSpace, PricingUnit

Interval = tuple[int, int]


class Unavailable(Exception):
    """Raised with a renter-facing reason when a window cannot be booked."""

    def __init__(self, reason: str, code: str = "NOT_AVAILABLE"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


# --------------------------------------------------------------------------- #
# Pure interval maths (no database) — the part worth unit-testing directly.
# --------------------------------------------------------------------------- #
def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    """Sort and coalesce overlapping or touching intervals."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def intervals_for_weekday(rules: list[AvailabilityRule], weekday: int) -> list[Interval]:
    return merge_intervals(
        [(r.start_minute, r.end_minute) for r in rules if r.is_active and r.day_of_week == weekday]
    )


def covers(intervals: list[Interval], start_minute: int, end_minute: int) -> bool:
    """True when [start_minute, end_minute) lies entirely within `intervals`."""
    if start_minute >= end_minute:
        return True
    cursor = start_minute
    for interval_start, interval_end in intervals:
        if interval_start > cursor:
            return False
        cursor = max(cursor, interval_end)
        if cursor >= end_minute:
            return True
    return cursor >= end_minute


def daily_segments(start_local: datetime, end_local: datetime) -> list[tuple[date, int, int]]:
    """Split a local window into (date, start_minute, end_minute) per calendar day."""
    segments: list[tuple[date, int, int]] = []
    current = start_local.date()
    last = (end_local - timedelta(microseconds=1)).date()
    while current <= last:
        day_start = datetime.combine(current, datetime.min.time(), tzinfo=start_local.tzinfo)
        day_end = day_start + timedelta(days=1)
        segment_start = max(start_local, day_start)
        segment_end = min(end_local, day_end)
        start_minute = int((segment_start - day_start).total_seconds() // 60)
        end_minute = int((segment_end - day_start).total_seconds() // 60)
        if end_minute > start_minute:
            segments.append((current, start_minute, end_minute))
        current += timedelta(days=1)
    return segments


def rules_cover_window(
    rules: list[AvailabilityRule], start_at: datetime, end_at: datetime, unit: PricingUnit
) -> bool:
    """Apply the per-unit coverage semantics described in the module docstring."""
    tz = local_tz()
    start_local = start_at.astimezone(tz)
    end_local = end_at.astimezone(tz)
    segments = daily_segments(start_local, end_local)
    if not segments:
        return False
    for day, start_minute, end_minute in segments:
        available = intervals_for_weekday(rules, day.weekday())
        if not available:
            return False
        if unit == PricingUnit.HOURLY and not covers(available, start_minute, end_minute):
            return False
    return True


# --------------------------------------------------------------------------- #
# Database-backed checks
# --------------------------------------------------------------------------- #
async def get_rules(db: AsyncSession, parking_space_id: uuid.UUID) -> list[AvailabilityRule]:
    rows = await db.scalars(
        select(AvailabilityRule)
        .where(AvailabilityRule.parking_space_id == parking_space_id)
        .order_by(AvailabilityRule.day_of_week, AvailabilityRule.start_minute)
    )
    return list(rows.all())


async def get_blocks(
    db: AsyncSession, parking_space_id: uuid.UUID, start_at: datetime, end_at: datetime
) -> list[AvailabilityBlock]:
    rows = await db.scalars(
        select(AvailabilityBlock).where(
            AvailabilityBlock.parking_space_id == parking_space_id,
            AvailabilityBlock.start_at < end_at,
            AvailabilityBlock.end_at > start_at,
        )
    )
    return list(rows.all())


async def blocked_space_ids(
    db: AsyncSession, space_ids: list[uuid.UUID], start_at: datetime, end_at: datetime
) -> set[uuid.UUID]:
    """Spaces with a provider block overlapping the window — used by search."""
    if not space_ids:
        return set()
    rows = await db.scalars(
        select(AvailabilityBlock.parking_space_id).where(
            AvailabilityBlock.parking_space_id.in_(space_ids),
            AvailabilityBlock.start_at < end_at,
            AvailabilityBlock.end_at > start_at,
        )
    )
    return set(rows.all())


async def rules_by_space(
    db: AsyncSession, space_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[AvailabilityRule]]:
    if not space_ids:
        return {}
    rows = await db.scalars(
        select(AvailabilityRule).where(AvailabilityRule.parking_space_id.in_(space_ids))
    )
    grouped: dict[uuid.UUID, list[AvailabilityRule]] = {space_id: [] for space_id in space_ids}
    for rule in rows.all():
        grouped[rule.parking_space_id].append(rule)
    return grouped


async def taken_slots(
    db: AsyncSession,
    parking_space_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    exclude_booking_id: uuid.UUID | None = None,
) -> set[int]:
    """Slot indexes already held by a blocking booking over this window."""
    from app.modules.bookings.models import BLOCKING_STATUSES, Booking

    conditions = [
        Booking.parking_space_id == parking_space_id,
        Booking.status.in_(BLOCKING_STATUSES),
        Booking.start_at < end_at,
        Booking.end_at > start_at,
    ]
    if exclude_booking_id is not None:
        conditions.append(Booking.id != exclude_booking_id)
    rows = await db.scalars(select(Booking.slot_index).where(and_(*conditions)))
    return set(rows.all())


async def find_free_slot(
    db: AsyncSession,
    space: ParkingSpace,
    start_at: datetime,
    end_at: datetime,
    exclude_booking_id: uuid.UUID | None = None,
) -> int | None:
    """Lowest free slot index, or None when the space is fully booked.

    This is an optimistic read: the authoritative check is the exclusion
    constraint on `bookings`, which rejects a losing racer at COMMIT.
    """
    taken = await taken_slots(db, space.id, start_at, end_at, exclude_booking_id)
    for index in range(max(space.total_slots, 1)):
        if index not in taken:
            return index
    return None


async def assert_available(
    db: AsyncSession,
    space: ParkingSpace,
    start_at: datetime,
    end_at: datetime,
    unit: PricingUnit,
    exclude_booking_id: uuid.UUID | None = None,
) -> int:
    """Validate a window and return the slot index to use. Raises `Unavailable`."""
    rules = await get_rules(db, space.id)
    if not rules:
        raise Unavailable("This space has no availability set up yet", code="NO_AVAILABILITY")
    if not rules_cover_window(rules, start_at, end_at, unit):
        raise Unavailable("The space is not available for the selected times", code="OUTSIDE_AVAILABILITY")
    if await get_blocks(db, space.id, start_at, end_at):
        raise Unavailable("The provider has blocked this period", code="BLOCKED")
    slot_index = await find_free_slot(db, space, start_at, end_at, exclude_booking_id)
    if slot_index is None:
        raise Unavailable("This space is already booked for the selected times", code="ALREADY_BOOKED")
    return slot_index


# --------------------------------------------------------------------------- #
# Provider calendar
# --------------------------------------------------------------------------- #
@dataclass
class DayAvailability:
    day: date
    # Merged open windows for that weekday, as (start_minute, end_minute).
    windows: list[Interval]
    blocked: bool
    booked_slots: int
    total_slots: int

    @property
    def is_open(self) -> bool:
        return bool(self.windows) and not self.blocked and self.booked_slots < self.total_slots


async def build_calendar(
    db: AsyncSession, space: ParkingSpace, from_date: date, to_date: date
) -> list[DayAvailability]:
    """Per-day availability for the provider's calendar view."""
    from app.modules.bookings.models import BLOCKING_STATUSES, Booking

    tz = local_tz()
    window_start = datetime.combine(from_date, datetime.min.time(), tzinfo=tz)
    window_end = datetime.combine(to_date + timedelta(days=1), datetime.min.time(), tzinfo=tz)

    rules = await get_rules(db, space.id)
    blocks = await get_blocks(db, space.id, window_start, window_end)
    bookings = list(
        (
            await db.scalars(
                select(Booking).where(
                    Booking.parking_space_id == space.id,
                    Booking.status.in_(BLOCKING_STATUSES),
                    Booking.start_at < window_end,
                    Booking.end_at > window_start,
                )
            )
        ).all()
    )

    days: list[DayAvailability] = []
    current = from_date
    while current <= to_date:
        day_start = datetime.combine(current, datetime.min.time(), tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        overlaps = lambda s, e: s < day_end and e > day_start  # noqa: E731
        days.append(
            DayAvailability(
                day=current,
                windows=intervals_for_weekday(rules, current.weekday()),
                blocked=any(overlaps(b.start_at, b.end_at) for b in blocks),
                booked_slots=len({b.slot_index for b in bookings if overlaps(b.start_at, b.end_at)}),
                total_slots=max(space.total_slots, 1),
            )
        )
        current += timedelta(days=1)
    return days

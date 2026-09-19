"""Scheduled booking state transitions.

Bookings move through their lifecycle on the clock, not on a request, so these
run from a background loop (and can equally be driven by cron or a worker later
— `run_once` is the whole entry point).

Everything here is idempotent: each pass only touches rows still in the state it
is moving out of, so a missed tick or an overlapping run changes nothing.
"""
import logging
from datetime import timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.modules.bookings import notifications, overstay
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.notifications.service import deliver_email
from app.modules.settings.schemas import PlatformConfig

logger = logging.getLogger(__name__)

# Emails queued during a pass, sent after the transaction commits.
_PendingEmail = tuple[object, str, str, str]


async def expire_holds(db: AsyncSession) -> int:
    """Release slots held by bookings that were never paid for or accepted."""
    result = await db.execute(
        update(Booking)
        .where(
            Booking.status.in_([BookingStatus.PENDING_PAYMENT, BookingStatus.PENDING_APPROVAL]),
            Booking.hold_expires_at.is_not(None),
            Booking.hold_expires_at <= utcnow(),
        )
        .values(status=BookingStatus.EXPIRED, hold_expires_at=None)
    )
    return result.rowcount or 0


async def activate_started(db: AsyncSession) -> int:
    """Flip confirmed bookings to ACTIVE once their window opens.

    Listings that require an arrival code are excluded: on those, becoming
    ACTIVE is the *result* of the renter proving they are at the gate, so
    activating them on a timer would bypass the check entirely. They are left
    CONFIRMED until verified, and `complete_finished` still closes them out so
    an unverified booking cannot hang around forever.
    """
    from app.modules.parking.models import ParkingSpace

    now = utcnow()
    gated = select(ParkingSpace.id).where(ParkingSpace.requires_arrival_code.is_(True))
    result = await db.execute(
        update(Booking)
        .where(
            Booking.status == BookingStatus.CONFIRMED,
            Booking.start_at <= now,
            Booking.end_at > now,
            Booking.parking_space_id.not_in(gated),
        )
        .values(status=BookingStatus.ACTIVE)
    )
    return result.rowcount or 0


async def start_overstays(db: AsyncSession, config: PlatformConfig) -> list[Booking]:
    """Move bookings that ran past their grace period onto the meter.

    Only ACTIVE bookings — someone actually parked. A CONFIRMED booking whose
    window passed without a check-in is handled by `complete_finished`, because
    there is no evidence anybody turned up and billing them would be wrong.
    """
    now = utcnow()
    cutoff = now - timedelta(minutes=config.overstay_grace_minutes)
    rows = await db.scalars(
        select(Booking).where(Booking.status == BookingStatus.ACTIVE, Booking.end_at <= cutoff)
    )
    started = list(rows.all())
    for booking in started:
        booking.status = BookingStatus.OVERSTAYING
        overstay.freeze(booking, config, now)
    return started


async def complete_finished(db: AsyncSession, config: PlatformConfig) -> list[Booking]:
    """Close out bookings whose window has passed.

    Three groups end here:
      - CONFIRMED but never started: nobody turned up, nothing to bill.
      - ACTIVE but still inside the grace period: they left on time enough.
      - OVERSTAYING past the meter cap: the meter has stopped, so the bay is
        released and whatever accrued stays on the booking as owed. Holding the
        bay indefinitely for an abandoned car helps nobody.
    """
    now = utcnow()
    grace_cutoff = now - timedelta(minutes=config.overstay_grace_minutes)
    capped = now - timedelta(hours=config.overstay_max_hours)
    rows = await db.scalars(
        select(Booking).where(
            or_(
                and_(
                    Booking.status.in_([BookingStatus.ACTIVE, BookingStatus.CONFIRMED]),
                    Booking.end_at <= now,
                    Booking.end_at > grace_cutoff,
                ),
                and_(Booking.status == BookingStatus.CONFIRMED, Booking.end_at <= grace_cutoff),
                and_(Booking.status == BookingStatus.OVERSTAYING, Booking.end_at <= capped),
            )
        )
    )
    finished = list(rows.all())
    for booking in finished:
        if booking.status == BookingStatus.OVERSTAYING:
            overstay.freeze(booking, config, now)
        booking.status = BookingStatus.COMPLETED
        booking.completed_at = now
    return finished


async def due_reminders(db: AsyncSession, config: PlatformConfig) -> list[Booking]:
    now = utcnow()
    horizon = now + timedelta(hours=config.reminder_hours_before)
    rows = await db.scalars(
        select(Booking).where(
            Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.ACTIVE]),
            Booking.reminder_sent_at.is_(None),
            Booking.start_at > now,
            Booking.start_at <= horizon,
        )
    )
    due = list(rows.all())
    for booking in due:
        booking.reminder_sent_at = now
    return due


async def run_once(db: AsyncSession) -> dict[str, int]:
    """One maintenance pass. Returns a count per transition, for logging/tests."""
    from app.modules.settings.service import get_config

    config = await get_config(db)
    expired = await expire_holds(db)
    activated = await activate_started(db)
    # Order matters: a booking must go onto the meter before the completion
    # sweep looks at it, or a late renter would be closed out for free.
    overstaying = await start_overstays(db, config)
    completed = await complete_finished(db, config)
    reminders = await due_reminders(db, config)

    pending: list[_PendingEmail] = []
    for booking in overstaying:
        note = await _queue(db, booking, notifications.overstay_started)
        if note:
            pending.append(note)
    for booking in completed:
        note = await _queue(db, booking, notifications.booking_completed)
        if note:
            pending.append(note)
    for booking in reminders:
        note = await _queue(db, booking, notifications.booking_reminder)
        if note:
            pending.append(note)

    await db.commit()

    # Emails go out only once the state change is durable.
    for notification_id, address, subject, body in pending:
        await deliver_email(notification_id, address, subject, body)

    return {
        "expired": expired,
        "activated": activated,
        "overstaying": len(overstaying),
        "completed": len(completed),
        "reminders": len(reminders),
    }


async def _queue(db: AsyncSession, booking: Booking, sender) -> _PendingEmail | None:
    """Create the in-app notification now; hand back what the email needs."""
    created = await sender(db, None, booking)
    if created is None:
        return None
    note, address = created
    return (note.id, address, note.title, note.body)

"""Booking lifecycle.

Double-booking protection (PRD §13)
-----------------------------------
Three layers, of which only the last is authoritative:

1. Search hides spaces that are already taken — a convenience, nothing more.
2. `assert_available` re-checks rules, blocks and existing bookings inside the
   booking transaction and picks a free slot.
3. The `no_overlapping_bookings` exclusion constraint on the `bookings` table
   rejects an overlapping row at COMMIT. Two requests that pass step 2 at the
   same instant cannot both commit; the loser is retried against a fresh read of
   the slots, and gives up with 409 when the space is genuinely full.

Step 3 is what makes the guarantee real: it holds no matter how the application
is deployed, how many workers run, or what the frontend believes.
"""
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import BackgroundTasks
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.time import utcnow
from app.modules.availability import service as availability_service
from app.modules.availability.service import Unavailable
from app.modules.bookings import pricing
from app.modules.parking import bays
from app.modules.bookings.models import (
    BLOCKING_STATUSES,
    CANCELLABLE_STATUSES,
    Booking,
    BookingStatus,
)

# Statuses in which the renter has not been charged yet.
UNPAID_STATUSES = (BookingStatus.PENDING_PAYMENT, BookingStatus.PENDING_APPROVAL)
from app.modules.bookings.pricing import InvalidDuration, PriceBreakdown
from app.modules.bookings.schemas import BookingCreate
from app.modules.parking import service as parking_service
from app.modules.parking.models import ParkingSpace, PricingUnit, VehicleType
from app.modules.providers import service as provider_service
from app.modules.providers.models import Provider, ProviderType
from app.modules.settings.schemas import PlatformConfig
from app.modules.users.models import User
from app.modules.vehicles.models import Vehicle

logger = logging.getLogger(__name__)

# Unambiguous alphabet: no O/0, I/1, so a reference read off a phone screen and
# typed by a security guard doesn't come back wrong.
_REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_REFERENCE_PREFIX = "PS"
MAX_SLOT_RETRIES = 5


def generate_reference() -> str:
    return f"{_REFERENCE_PREFIX}-" + "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(6))


def _is_overlap_violation(exc: IntegrityError) -> bool:
    return "no_overlapping_bookings" in str(getattr(exc, "orig", exc))


def _is_reference_violation(exc: IntegrityError) -> bool:
    return "bookings_reference" in str(getattr(exc, "orig", exc)) or "ix_bookings_reference" in str(
        getattr(exc, "orig", exc)
    )


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #
def resolve_window(
    unit: PricingUnit, start_at: datetime, end_at: datetime | None, quantity: int | None
) -> tuple[datetime, datetime]:
    """Accept either an explicit end or a unit count, and normalise to a window."""
    if end_at is None and quantity is None:
        raise ValidationFailed("Provide either end_at or quantity", code="DURATION_REQUIRED")
    if end_at is not None:
        return start_at, end_at
    return start_at, pricing.end_for(unit, start_at, quantity)


def validate_timing(start_at: datetime, end_at: datetime, config: PlatformConfig) -> None:
    now = utcnow()
    if end_at <= start_at:
        raise ValidationFailed("End time must be after start time", code="INVALID_DURATION")
    if start_at < now - timedelta(minutes=1):
        raise ValidationFailed("Bookings cannot start in the past", code="START_IN_PAST")
    minimum_start = now + timedelta(minutes=config.booking_min_lead_minutes)
    if start_at < minimum_start - timedelta(minutes=1):
        raise ValidationFailed(
            f"Bookings must start at least {config.booking_min_lead_minutes} minutes from now",
            code="LEAD_TIME",
        )
    if start_at > now + timedelta(days=config.booking_max_advance_days):
        raise ValidationFailed(
            f"Bookings can be made at most {config.booking_max_advance_days} days in advance",
            code="TOO_FAR_AHEAD",
        )
    assert_window_bounded(start_at, end_at, config)


def assert_window_bounded(start_at: datetime, end_at: datetime, config: PlatformConfig) -> None:
    """Refuse a window longer than the platform allows.

    Bounding the far end matters as much as bounding the near one. An unbounded
    window is a lever on how much work a single request costs the server, and on
    how large a total the money columns are asked to hold — so it is checked
    before anything is priced or searched, not after.
    """
    if end_at - start_at > timedelta(days=config.booking_max_window_days):
        raise ValidationFailed(
            f"A booking can run for at most {config.booking_max_window_days} days",
            code="WINDOW_TOO_LONG",
        )


async def _provider_share_for(db: AsyncSession, space: ParkingSpace) -> Decimal | None:
    """A society's negotiated revenue share replaces the default commission."""
    from app.modules.providers.models import Society

    provider = await db.get(Provider, space.provider_id)
    if provider is None or provider.provider_type != ProviderType.SOCIETY:
        return None
    society = await db.scalar(select(Society).where(Society.provider_id == provider.id))
    if society is None:
        return None
    agreement = await provider_service.active_agreement(db, society.id)
    return Decimal(agreement.revenue_share_percent) if agreement else None


async def quote(
    db: AsyncSession,
    space: ParkingSpace,
    unit: PricingUnit,
    start_at: datetime,
    end_at: datetime,
    config: PlatformConfig,
) -> tuple[PriceBreakdown, bool, str | None]:
    """Price a window and report whether it can actually be booked."""
    # An over-long window is a malformed request rather than a priced-but-
    # unavailable one, so it is refused outright instead of coming back with a
    # breakdown nobody could act on.
    assert_window_bounded(start_at, end_at, config)
    try:
        breakdown = pricing.calculate(
            space,
            unit,
            start_at,
            end_at,
            config,
            provider_share_percent=await _provider_share_for(db, space),
        )
    except InvalidDuration as exc:
        raise ValidationFailed(exc.message, code=exc.code)

    try:
        validate_timing(start_at, end_at, config)
        await availability_service.assert_available(db, space, start_at, end_at, unit)
    except Unavailable as exc:
        return breakdown, False, exc.reason
    except ValidationFailed as exc:
        return breakdown, False, exc.message
    return breakdown, True, None


# --------------------------------------------------------------------------- #
# Creation
# --------------------------------------------------------------------------- #
@dataclass
class CreatedBooking:
    booking: Booking
    breakdown: PriceBreakdown


async def create(
    db: AsyncSession, renter: User, data: BookingCreate, config: PlatformConfig
) -> CreatedBooking:
    space = await parking_service.get_public(db, data.parking_space_id)
    provider = await db.get(Provider, space.provider_id)
    if provider is not None and provider.user_id == renter.id:
        raise Forbidden("You cannot book your own parking space", code="OWN_LISTING")

    vehicle = await db.get(Vehicle, data.vehicle_id)
    if vehicle is None or vehicle.user_id != renter.id:
        raise NotFound("Vehicle not found")
    if vehicle.vehicle_type.value not in space.vehicle_types:
        raise ValidationFailed(
            f"This space does not accept a {vehicle.vehicle_type.value.lower()}", code="VEHICLE_NOT_SUPPORTED"
        )

    start_at, end_at = resolve_window(data.unit, data.start_at, data.end_at, data.quantity)
    validate_timing(start_at, end_at, config)

    try:
        breakdown = pricing.calculate(
            space,
            data.unit,
            start_at,
            end_at,
            config,
            provider_share_percent=await _provider_share_for(db, space),
        )
    except InvalidDuration as exc:
        raise ValidationFailed(exc.message, code=exc.code)

    needs_approval = space.requires_approval
    status = BookingStatus.PENDING_APPROVAL if needs_approval else BookingStatus.PENDING_PAYMENT
    hold = (
        timedelta(hours=config.approval_window_hours)
        if needs_approval
        else timedelta(minutes=config.payment_hold_minutes)
    )

    # A renter who named a bay gets that bay or nothing. Retrying onto a
    # different one would move somebody who chose the spot by the lift, and they
    # would only discover it on arrival.
    chosen = data.slot_index
    if chosen is not None:
        await bays.assert_bookable(db, space, chosen)

    # Retry loop: a lost race against a concurrent booking may free a different
    # slot, so re-read and try again rather than failing a still-bookable space.
    # It does not apply to a named bay — there is nowhere else to go.
    attempts = 1 if chosen is not None else MAX_SLOT_RETRIES
    for attempt in range(attempts):
        try:
            slot_index = await availability_service.assert_available(
                db, space, start_at, end_at, data.unit, want_slot=chosen
            )
        except Unavailable as exc:
            raise Conflict(exc.reason, code=exc.code)

        booking = Booking(
            reference=generate_reference(),
            renter_id=renter.id,
            parking_space_id=space.id,
            provider_id=space.provider_id,
            vehicle_id=vehicle.id,
            vehicle_number=vehicle.registration_number,
            vehicle_type=vehicle.vehicle_type.value,
            slot_index=slot_index,
            start_at=start_at,
            end_at=end_at,
            unit=data.unit,
            quantity=breakdown.quantity,
            unit_price=breakdown.unit_price,
            base_amount=breakdown.base_amount,
            platform_fee=breakdown.platform_fee,
            tax_amount=breakdown.tax_amount,
            total_amount=breakdown.total_amount,
            commission_amount=breakdown.commission_amount,
            provider_earning=breakdown.provider_earning,
            currency=breakdown.currency,
            status=status,
            hold_expires_at=utcnow() + hold,
            renter_notes=data.renter_notes,
        )
        try:
            # A SAVEPOINT keeps a rejected insert from tearing down the caller's
            # transaction, so a retry costs one round trip rather than the request.
            async with db.begin_nested():
                db.add(booking)
                # Force the constraint to be evaluated now, while we can still react.
                await db.flush()
            # Attach the already-loaded space: under asyncio a lazy load on a
            # freshly inserted row would raise rather than quietly fetch.
            booking.parking_space = space
            booking.vehicle = vehicle
        except IntegrityError as exc:
            if _is_reference_violation(exc):
                continue
            if not _is_overlap_violation(exc):
                raise
            logger.info(
                "Booking race on space %s slot %s (attempt %s)", space.id, slot_index, attempt + 1
            )
            continue
        return CreatedBooking(booking=booking, breakdown=breakdown)

    raise Conflict("This space was just booked for those times", code="ALREADY_BOOKED")


# --------------------------------------------------------------------------- #
# State transitions
# --------------------------------------------------------------------------- #
async def mark_paid(db: AsyncSession, booking: Booking) -> Booking:
    """Called by the payments module once a payment is captured."""
    if booking.status == BookingStatus.PENDING_PAYMENT:
        booking.status = BookingStatus.CONFIRMED
        booking.confirmed_at = utcnow()
        booking.hold_expires_at = None
        await db.flush()
    return booking


async def approve(db: AsyncSession, booking: Booking, config: PlatformConfig) -> Booking:
    if booking.status != BookingStatus.PENDING_APPROVAL:
        raise Conflict("This booking is not awaiting approval", code="INVALID_STATE")
    booking.status = BookingStatus.PENDING_PAYMENT
    booking.hold_expires_at = utcnow() + timedelta(minutes=config.payment_hold_minutes)
    await db.flush()
    return booking


async def reject(db: AsyncSession, booking: Booking, reason: str) -> Booking:
    if booking.status != BookingStatus.PENDING_APPROVAL:
        raise Conflict("This booking is not awaiting approval", code="INVALID_STATE")
    booking.status = BookingStatus.REJECTED
    booking.cancellation_reason = reason
    booking.cancelled_at = utcnow()
    booking.hold_expires_at = None
    await db.flush()
    return booking


def hours_until_start(booking: Booking, now: datetime | None = None) -> float:
    return (booking.start_at - (now or utcnow())).total_seconds() / 3600


def refund_if_cancelled_now(booking: Booking, config: PlatformConfig) -> Decimal:
    """What the renter would get back right now. Mirrors `cancel` exactly, so the
    figure shown before confirming is the figure they actually receive."""
    if booking.status in UNPAID_STATUSES:
        return Decimal("0.00")
    return pricing.refund_for(Decimal(booking.total_amount), hours_until_start(booking), config)


def can_cancel(booking: Booking, config: PlatformConfig) -> bool:
    if booking.status not in CANCELLABLE_STATUSES:
        return False
    if hours_until_start(booking) <= 0 and not config.cancellation_policy.allow_after_start:
        return False
    return True


async def cancel(
    db: AsyncSession, booking: Booking, actor: User, config: PlatformConfig, reason: str | None = None
) -> tuple[Booking, Decimal]:
    """Cancel a booking and compute the refund owed. The actual gateway refund is
    initiated by the caller through the payments module."""
    if booking.status not in CANCELLABLE_STATUSES:
        raise Conflict(f"A {booking.status.value.lower()} booking cannot be cancelled", code="INVALID_STATE")

    started = hours_until_start(booking) <= 0
    is_provider_side = actor.is_admin or await _is_provider_of(db, booking, actor)
    if started and not config.cancellation_policy.allow_after_start and not is_provider_side:
        raise Conflict("This booking has already started and can no longer be cancelled", code="TOO_LATE")

    # Nothing has been taken from the renter until the booking is paid for, so
    # an unpaid cancellation refunds nothing no matter who triggered it —
    # recording a refund here would promise money that was never charged.
    if booking.status in UNPAID_STATUSES:
        refund = Decimal("0.00")
    elif is_provider_side:
        # A provider or admin cancelling is not the renter's fault, so the
        # tiered policy does not apply: they get everything back.
        refund = Decimal(booking.total_amount)
    else:
        refund = pricing.refund_for(Decimal(booking.total_amount), hours_until_start(booking), config)

    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = utcnow()
    booking.cancelled_by_id = actor.id
    booking.cancellation_reason = reason
    booking.refund_amount = refund
    booking.hold_expires_at = None
    # A cancelled booking earns nobody anything.
    booking.provider_earning = Decimal("0.00")
    booking.commission_amount = Decimal("0.00")
    await db.flush()
    return booking, refund


async def _is_provider_of(db: AsyncSession, booking: Booking, user: User) -> bool:
    provider = await provider_service.get_by_user(db, user.id)
    return provider is not None and provider.id == booking.provider_id


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
async def get_for_user(db: AsyncSession, booking_id: uuid.UUID, user: User) -> Booking:
    """A booking is visible to its renter, its provider, and admins."""
    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise NotFound("Booking not found")
    if booking.renter_id == user.id or user.is_admin:
        return booking
    if await _is_provider_of(db, booking, user):
        return booking
    raise NotFound("Booking not found")


async def get_by_reference(db: AsyncSession, reference: str, user: User) -> Booking:
    booking = await db.scalar(select(Booking).where(Booking.reference == reference.upper()))
    if booking is None:
        raise NotFound("Booking not found")
    return await get_for_user(db, booking.id, user)


async def list_for_renter(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    scope: str = "all",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Booking], int]:
    return await _list(db, [Booking.renter_id == user_id], scope, limit, offset)


async def list_for_provider(
    db: AsyncSession,
    provider_id: uuid.UUID,
    *,
    scope: str = "all",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Booking], int]:
    return await _list(db, [Booking.provider_id == provider_id], scope, limit, offset)


async def _list(db: AsyncSession, conditions: list, scope: str, limit: int, offset: int):
    now = utcnow()
    if scope == "upcoming":
        conditions.append(Booking.end_at > now)
        conditions.append(Booking.status.in_(BLOCKING_STATUSES))
    elif scope == "active":
        conditions.append(Booking.status == BookingStatus.ACTIVE)
    elif scope == "past":
        conditions.append(
            or_(
                Booking.end_at <= now,
                Booking.status.in_(
                    [
                        BookingStatus.COMPLETED,
                        BookingStatus.CANCELLED,
                        BookingStatus.EXPIRED,
                        BookingStatus.REJECTED,
                    ]
                ),
            )
        )
    total = await db.scalar(select(func.count()).select_from(Booking).where(*conditions)) or 0
    rows = await db.scalars(
        select(Booking).where(*conditions).order_by(Booking.start_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.all()), int(total)


async def end_parking(db: AsyncSession, booking: Booking, config: PlatformConfig) -> Booking:
    """Renter says they are leaving. Closes the booking if nothing is owed.

    A booking inside its window can be ended early — people leave early — and
    that costs nothing extra. Past the grace period the meter is settled first,
    because releasing the bay is the renter's side of the bargain and paying is
    theirs too.
    """
    from app.modules.bookings import overstay

    if booking.status == BookingStatus.COMPLETED:
        return booking  # idempotent: tapping twice is not an error
    if booking.status not in (BookingStatus.ACTIVE, BookingStatus.OVERSTAYING):
        raise Conflict(
            f"A {booking.status.value.lower()} booking cannot be ended", code="INVALID_STATE"
        )

    now = utcnow()
    owed = overstay.freeze(booking, config, now)
    if owed > 0 and booking.overstay_paid_at is None:
        raise Conflict(
            "Pay for the extra time before you finish", code="OVERSTAY_UNPAID"
        )

    booking.status = BookingStatus.COMPLETED
    booking.completed_at = now
    await db.flush()
    return booking

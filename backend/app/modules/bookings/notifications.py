"""Booking-event notifications for both sides of a booking."""
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import local_tz
from app.modules.bookings.models import Booking
from app.modules.notifications.models import Notification
from app.modules.notifications.service import notify
from app.modules.providers.models import Provider
from app.modules.users.models import User


def format_window(booking: Booking) -> str:
    tz = local_tz()
    start = booking.start_at.astimezone(tz)
    end = booking.end_at.astimezone(tz)
    if start.date() == end.date():
        return f"{start:%d %b %Y, %I:%M %p} - {end:%I:%M %p}"
    return f"{start:%d %b %Y, %I:%M %p} - {end:%d %b %Y, %I:%M %p}"


async def _provider_user(db: AsyncSession, booking: Booking) -> User | None:
    provider = await db.get(Provider, booking.provider_id)
    return await db.get(User, provider.user_id) if provider else None


async def _both(
    db: AsyncSession,
    background: BackgroundTasks | None,
    booking: Booking,
    event: str,
    renter_title: str,
    renter_body: str,
    provider_title: str,
    provider_body: str,
) -> None:
    data = {"booking_id": str(booking.id), "reference": booking.reference}
    renter = await db.get(User, booking.renter_id)
    if renter is not None:
        await notify(db, background, renter, event, renter_title, renter_body, data)
    provider_user = await _provider_user(db, booking)
    if provider_user is not None:
        await notify(db, background, provider_user, event, provider_title, provider_body, data)


async def booking_created(db: AsyncSession, background: BackgroundTasks | None, booking: Booking) -> None:
    space = booking.parking_space
    window = format_window(booking)
    await _both(
        db,
        background,
        booking,
        "BOOKING_CREATED",
        "Complete your payment",
        f"Your booking {booking.reference} for {space.title} ({window}) is held until you pay "
        f"{booking.currency} {booking.total_amount}.",
        "New booking request",
        f"{space.title} has a booking request for {window} (ref {booking.reference}).",
    )


async def booking_confirmed(db: AsyncSession, background: BackgroundTasks | None, booking: Booking) -> None:
    space = booking.parking_space
    window = format_window(booking)
    await _both(
        db,
        background,
        booking,
        "BOOKING_CONFIRMED",
        "Booking confirmed",
        f"Your parking at {space.title} is confirmed for {window}. Reference {booking.reference}. "
        f"Vehicle {booking.vehicle_number}.",
        "Booking confirmed",
        f"{space.title} is booked for {window}. Vehicle {booking.vehicle_number}, "
        f"reference {booking.reference}.",
    )


async def booking_cancelled(
    db: AsyncSession, background: BackgroundTasks | None, booking: Booking, by_renter: bool
) -> None:
    space = booking.parking_space
    window = format_window(booking)
    refund_line = (
        f" A refund of {booking.currency} {booking.refund_amount} is on its way."
        if booking.refund_amount and booking.refund_amount > 0
        else ""
    )
    await _both(
        db,
        background,
        booking,
        "BOOKING_CANCELLED",
        "Booking cancelled",
        f"Your booking {booking.reference} at {space.title} ({window}) was cancelled.{refund_line}",
        "Booking cancelled",
        f"The booking {booking.reference} at {space.title} ({window}) was cancelled"
        f"{' by the renter' if by_renter else ''}. The slot is free again.",
    )


async def booking_approved(db: AsyncSession, background: BackgroundTasks | None, booking: Booking) -> None:
    renter = await db.get(User, booking.renter_id)
    if renter is not None:
        await notify(
            db,
            background,
            renter,
            "BOOKING_APPROVED",
            "Booking accepted - pay to confirm",
            f"The provider accepted booking {booking.reference} for {booking.parking_space.title}. "
            f"Pay {booking.currency} {booking.total_amount} to confirm it.",
            {"booking_id": str(booking.id), "reference": booking.reference},
        )


async def booking_rejected(db: AsyncSession, background: BackgroundTasks | None, booking: Booking) -> None:
    renter = await db.get(User, booking.renter_id)
    if renter is not None:
        await notify(
            db,
            background,
            renter,
            "BOOKING_REJECTED",
            "Booking declined",
            f"The provider could not accept booking {booking.reference}. "
            f"Reason: {booking.cancellation_reason or 'not given'}. You have not been charged.",
            {"booking_id": str(booking.id), "reference": booking.reference},
        )


async def booking_reminder(
    db: AsyncSession, background: BackgroundTasks | None, booking: Booking
) -> tuple[Notification, str] | None:
    renter = await db.get(User, booking.renter_id)
    if renter is None:
        return None
    space = booking.parking_space
    instructions = f" Instructions: {space.access_instructions}" if space.access_instructions else ""
    note = await notify(
        db,
        background,
        renter,
        "BOOKING_REMINDER",
        "Your parking starts soon",
        f"{space.title}, {format_window(booking)}. Reference {booking.reference}, "
        f"vehicle {booking.vehicle_number}.{instructions}",
        {"booking_id": str(booking.id), "reference": booking.reference},
    )
    return note, renter.email


async def booking_completed(
    db: AsyncSession, background: BackgroundTasks | None, booking: Booking
) -> tuple[Notification, str] | None:
    renter = await db.get(User, booking.renter_id)
    if renter is None:
        return None
    note = await notify(
        db,
        background,
        renter,
        "BOOKING_COMPLETED",
        "How was your parking?",
        f"Your booking {booking.reference} at {booking.parking_space.title} is complete. "
        "Leave a rating to help other renters.",
        {"booking_id": str(booking.id), "reference": booking.reference},
    )
    return note, renter.email


async def arrival_announced(
    db: AsyncSession,
    background: BackgroundTasks | None,
    booking: Booking,
    code: str,
    ttl_minutes: int,
) -> None:
    """Tell the provider a renter is at the gate, and give them the code.

    Only the provider is sent the code — the whole mechanism rests on the renter
    not being able to produce it themselves.
    """
    space = booking.parking_space
    data = {"booking_id": str(booking.id), "reference": booking.reference}
    provider_user = await _provider_user(db, booking)
    if provider_user is not None:
        await notify(
            db,
            background,
            provider_user,
            "ARRIVAL_CODE",
            f"Arrival code {code}",
            f"A renter has arrived at {space.title} for booking {booking.reference} "
            f"(vehicle {booking.vehicle_number}). Share this code with them to let them in: "
            f"{code}. It expires in {ttl_minutes} minutes.",
            {**data, "code": code},
        )
    renter = await db.get(User, booking.renter_id)
    if renter is not None:
        await notify(
            db,
            background,
            renter,
            "ARRIVAL_ANNOUNCED",
            "We've told the provider you're here",
            f"Ask them for your {6}-digit code and enter it to start parking at {space.title}.",
            data,
            email=False,  # they are standing at a gate holding their phone
        )


async def arrival_verified(
    db: AsyncSession, background: BackgroundTasks | None, booking: Booking
) -> None:
    space = booking.parking_space
    await _both(
        db,
        background,
        booking,
        "ARRIVAL_VERIFIED",
        "You're checked in",
        f"Your parking at {space.title} has started. Reference {booking.reference}.",
        "Renter checked in",
        f"{booking.vehicle_number} has checked in at {space.title} "
        f"(booking {booking.reference}).",
    )


async def overstay_started(
    db: AsyncSession, background: BackgroundTasks | None, booking: Booking
) -> None:
    """The meter has started. Said plainly, with the number, and without scolding."""
    space = booking.parking_space
    await _both(
        db,
        background,
        booking,
        "OVERSTAY_STARTED",
        "Your parking has run over",
        f"Your booking at {space.title} ended and the extra time is now being charged. "
        f"Open the booking to see what is owed and finish up.",
        "A renter has run over",
        f"{booking.vehicle_number} is still at {space.title} past the end of booking "
        f"{booking.reference}. The extra time is being charged.",
    )

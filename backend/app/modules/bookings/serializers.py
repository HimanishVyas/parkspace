"""Turn a Booking into the right shape for whoever is asking.

Two rules drive this module (PRD §22, Principle 2):
  * access instructions are released only once a booking is confirmed;
  * a renter never sees the provider's personal details, and the provider sees
    the renter's contact details only for a booking that is going ahead.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bookings import service as booking_service
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.bookings.schemas import (
    BookingConfirmation,
    BookingOut,
    BookingPartyOut,
    BookingSpaceSummary,
)
from app.modules.parking.models import VehicleType
from app.modules.providers.models import Provider
from app.modules.settings.schemas import PlatformConfig
from app.modules.users.models import User

# Statuses where the renter is entitled to the instructions for getting in.
_INSTRUCTIONS_VISIBLE = (BookingStatus.CONFIRMED, BookingStatus.ACTIVE, BookingStatus.COMPLETED)
# ...and where the provider is entitled to know who is coming.
_RENTER_DETAILS_VISIBLE = (
    BookingStatus.PENDING_APPROVAL,
    BookingStatus.CONFIRMED,
    BookingStatus.ACTIVE,
    BookingStatus.COMPLETED,
    BookingStatus.DISPUTED,
)


def _space_summary(booking: Booking) -> BookingSpaceSummary:
    space = booking.parking_space
    return BookingSpaceSummary(
        id=space.id,
        title=space.title,
        parking_type=space.parking_type,
        address_line=space.address_line,
        landmark=space.landmark,
        city=space.city,
        latitude=float(space.latitude),
        longitude=float(space.longitude),
        photo_url=space.photos[0].url if space.photos else None,
        requires_arrival_code=bool(space.requires_arrival_code),
    )


async def _bay_label(db: AsyncSession, booking: Booking) -> str | None:
    """The name painted on the floor for the slot this booking holds."""
    from app.modules.parking.models import ParkingBay

    return await db.scalar(
        select(ParkingBay.label).where(
            ParkingBay.parking_space_id == booking.parking_space_id,
            ParkingBay.slot_index == booking.slot_index,
        )
    )


async def to_out(
    db: AsyncSession, booking: Booking, viewer: User, config: PlatformConfig
) -> BookingOut:
    provider = await db.get(Provider, booking.provider_id)
    is_renter = booking.renter_id == viewer.id
    is_provider_side = provider is not None and provider.user_id == viewer.id
    privileged = is_provider_side or viewer.is_admin

    out = BookingOut(
        id=booking.id,
        reference=booking.reference,
        status=booking.status,
        parking_space=_space_summary(booking),
        provider_name=provider.display_name if provider else "",
        unit=booking.unit,
        start_at=booking.start_at,
        end_at=booking.end_at,
        quantity=booking.quantity,
        unit_price=booking.unit_price,
        base_amount=booking.base_amount,
        platform_fee=booking.platform_fee,
        tax_amount=booking.tax_amount,
        total_amount=booking.total_amount,
        refund_amount=booking.refund_amount,
        currency=booking.currency,
        vehicle_number=booking.vehicle_number,
        vehicle_type=VehicleType(booking.vehicle_type),
        bay_label=await _bay_label(db, booking),
        overstay_minutes=booking.overstay_minutes or 0,
        overstay_amount=booking.overstay_amount or 0,
        overstay_paid_at=booking.overstay_paid_at,
        renter_notes=booking.renter_notes,
        hold_expires_at=booking.hold_expires_at,
        confirmed_at=booking.confirmed_at,
        cancelled_at=booking.cancelled_at,
        cancellation_reason=booking.cancellation_reason,
        created_at=booking.created_at,
    )

    if booking.status in _INSTRUCTIONS_VISIBLE and (is_renter or privileged):
        out.access_instructions = booking.parking_space.access_instructions

    if privileged and booking.status in _RENTER_DETAILS_VISIBLE:
        renter = await db.get(User, booking.renter_id)
        if renter is not None:
            out.renter = BookingPartyOut(full_name=renter.full_name, phone=renter.phone)

    if privileged:
        out.provider_earning = booking.provider_earning

    if is_renter:
        out.can_cancel = booking_service.can_cancel(booking, config)
        if out.can_cancel:
            out.refund_if_cancelled_now = booking_service.refund_if_cancelled_now(booking, config)
    elif privileged:
        out.can_cancel = booking.status in booking_service.CANCELLABLE_STATUSES

    return out


async def to_confirmation(db: AsyncSession, booking: Booking) -> BookingConfirmation:
    space = booking.parking_space
    provider = await db.get(Provider, booking.provider_id)
    renter = await db.get(User, booking.renter_id)
    show_instructions = booking.status in _INSTRUCTIONS_VISIBLE
    address = ", ".join(filter(None, [space.title, space.address_line, space.landmark, space.city]))
    return BookingConfirmation(
        booking_id=booking.id,
        reference=booking.reference,
        status=booking.status,
        parking_location=address,
        latitude=float(space.latitude),
        longitude=float(space.longitude),
        provider_name=provider.display_name if provider else "",
        renter_name=renter.full_name if renter else "",
        vehicle_number=booking.vehicle_number,
        start_at=booking.start_at,
        end_at=booking.end_at,
        total_amount=booking.total_amount,
        currency=booking.currency,
        parking_instructions=space.access_instructions if show_instructions else None,
        # V1: an identifier the client renders as a QR code. It opens nothing and
        # controls no barrier — a guard scans it to look the booking up.
        qr_payload=f"PARKSPACE:{booking.reference}",
    )

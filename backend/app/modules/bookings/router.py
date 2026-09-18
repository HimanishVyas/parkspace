import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from app.core.deps import DB, CurrentUser, client_ip
from app.core.errors import Forbidden, NotFound
from app.core.ratelimit import rate_limit
from app.modules.bookings import notifications, serializers, service
from app.modules.bookings.schemas import (
    BookingCancel,
    BookingConfirmation,
    BookingCreate,
    BookingList,
    BookingOut,
    BookingReject,
    QuoteRequest,
    QuoteResponse,
)
from app.modules.parking import service as parking_service
from app.modules.providers import service as provider_service
from app.modules.settings.service import get_config

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/quote", response_model=QuoteResponse)
async def quote_booking(data: QuoteRequest, db: DB):
    """Price a window and say whether it is bookable, without reserving anything.

    The listing page calls this as the renter picks dates, so the price and the
    availability they see come from the same server-side rules the booking will
    be validated against.
    """
    space = await parking_service.get_public(db, data.parking_space_id)
    config = await get_config(db)
    start_at, end_at = service.resolve_window(data.unit, data.start_at, data.end_at, data.quantity)
    breakdown, available, reason = await service.quote(db, space, data.unit, start_at, end_at, config)
    return QuoteResponse(
        parking_space_id=space.id,
        unit=breakdown.unit,
        start_at=start_at,
        end_at=end_at,
        quantity=breakdown.quantity,
        unit_price=breakdown.unit_price,
        base_amount=breakdown.base_amount,
        platform_fee=breakdown.platform_fee,
        tax_amount=breakdown.tax_amount,
        total_amount=breakdown.total_amount,
        currency=breakdown.currency,
        available=available,
        unavailable_reason=reason,
    )


@router.post(
    "",
    response_model=BookingOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("booking_create", 20, 60))],
)
async def create_booking(
    data: BookingCreate, user: CurrentUser, db: DB, background: BackgroundTasks, request: Request
):
    config = await get_config(db)
    created = await service.create(db, user, data, config)
    booking = created.booking
    await notifications.booking_created(db, background, booking)
    from app.modules.audit.service import record

    await record(
        db,
        actor_id=user.id,
        action="booking.create",
        entity_type="booking",
        entity_id=booking.id,
        data={"reference": booking.reference, "total": str(booking.total_amount)},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(booking)
    return await serializers.to_out(db, booking, user, config)


@router.get("", response_model=BookingList)
async def list_bookings(
    user: CurrentUser,
    db: DB,
    role: str = Query(default="renter", pattern="^(renter|provider)$"),
    scope: str = Query(default="all", pattern="^(all|upcoming|active|past)$"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
):
    config = await get_config(db)
    if role == "provider":
        provider = await provider_service.require_provider(db, user)
        bookings, total = await service.list_for_provider(
            db, provider.id, scope=scope, limit=limit, offset=offset
        )
    else:
        bookings, total = await service.list_for_renter(
            db, user.id, scope=scope, limit=limit, offset=offset
        )
    items = [await serializers.to_out(db, booking, user, config) for booking in bookings]
    return BookingList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(booking_id: uuid.UUID, user: CurrentUser, db: DB):
    booking = await service.get_for_user(db, booking_id, user)
    config = await get_config(db)
    return await serializers.to_out(db, booking, user, config)


@router.get("/{booking_id}/confirmation", response_model=BookingConfirmation)
async def get_confirmation(booking_id: uuid.UUID, user: CurrentUser, db: DB):
    """The booking confirmation a renter shows on arrival (PRD §19)."""
    booking = await service.get_for_user(db, booking_id, user)
    return await serializers.to_confirmation(db, booking)


@router.post("/{booking_id}/cancel", response_model=BookingOut)
async def cancel_booking(
    booking_id: uuid.UUID,
    data: BookingCancel,
    user: CurrentUser,
    db: DB,
    background: BackgroundTasks,
    request: Request,
):
    from app.modules.audit.service import record
    from app.modules.payments.service import refund_booking

    booking = await service.get_for_user(db, booking_id, user)
    config = await get_config(db)
    by_renter = booking.renter_id == user.id
    booking, refund_due = await service.cancel(db, booking, user, config, data.reason)
    # The refund goes out only after the cancellation itself is settled in the
    # transaction, so we never refund a booking that failed to cancel.
    await refund_booking(db, booking, refund_due, data.reason or "Booking cancelled")
    await notifications.booking_cancelled(db, background, booking, by_renter)
    await record(
        db,
        actor_id=user.id,
        action="booking.cancel",
        entity_type="booking",
        entity_id=booking.id,
        data={"reference": booking.reference, "refund": str(refund_due)},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(booking)
    return await serializers.to_out(db, booking, user, config)


async def _require_provider_booking(db, user, booking_id: uuid.UUID):
    provider = await provider_service.require_provider(db, user)
    booking = await service.get_for_user(db, booking_id, user)
    if booking.provider_id != provider.id:
        raise NotFound("Booking not found")
    return booking


@router.post("/{booking_id}/approve", response_model=BookingOut)
async def approve_booking(
    booking_id: uuid.UUID, user: CurrentUser, db: DB, background: BackgroundTasks
):
    """Accept a request on a manual-approval listing; the renter then pays."""
    booking = await _require_provider_booking(db, user, booking_id)
    config = await get_config(db)
    await service.approve(db, booking, config)
    await notifications.booking_approved(db, background, booking)
    await db.commit()
    await db.refresh(booking)
    return await serializers.to_out(db, booking, user, config)


@router.post("/{booking_id}/reject", response_model=BookingOut)
async def reject_booking(
    booking_id: uuid.UUID, data: BookingReject, user: CurrentUser, db: DB, background: BackgroundTasks
):
    booking = await _require_provider_booking(db, user, booking_id)
    config = await get_config(db)
    await service.reject(db, booking, data.reason)
    await notifications.booking_rejected(db, background, booking)
    await db.commit()
    await db.refresh(booking)
    return await serializers.to_out(db, booking, user, config)

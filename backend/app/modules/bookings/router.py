import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from app.core.deps import DB, CurrentUser, client_ip
from app.core.errors import Forbidden, NotFound
from app.core.time import utcnow
from app.core.ratelimit import rate_limit
from app.modules.bookings import arrival, notifications, overstay, serializers, service
from app.modules.bookings.schemas import (
    ArrivalAnnounce,
    OverstayQuote,
    WaitingArrival,
    ArrivalState,
    ArrivalVerify,
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


@router.post(
    "/quote",
    response_model=QuoteResponse,
    dependencies=[Depends(rate_limit("quote", 60, 60))],
)
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


@router.get("/arrivals/waiting", response_model=list[WaitingArrival])
async def waiting_arrivals(user: CurrentUser, db: DB):
    """Renters of mine who are at a gate right now, waiting on a code."""
    provider = await provider_service.get_by_user(db, user.id)
    if provider is None:
        return []
    config = await get_config(db)
    waiting = await arrival.waiting_for_provider(db, provider.id, config)
    from app.modules.users.models import User as UserModel

    out = []
    for booking, code in waiting:
        renter = await db.get(UserModel, booking.renter_id)
        out.append(
            WaitingArrival(
                booking_id=booking.id,
                reference=booking.reference,
                space_title=booking.parking_space.title,
                renter_name=renter.full_name if renter else "Renter",
                renter_phone=renter.phone if renter else None,
                vehicle_number=booking.vehicle_number,
                code=code.code,
                waiting_minutes=round((utcnow() - code.requested_at).total_seconds() / 60, 1),
                expires_at=code.expires_at,
            )
        )
    return out


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


# --------------------------------------------------------------------------- #
# Arrival verification
# --------------------------------------------------------------------------- #


async def _arrival_view(db, booking_id: uuid.UUID, user) -> tuple:
    """Load a booking plus its arrival state, from either side of the deal."""
    booking = await service.get_for_user(db, booking_id, user)
    config = await get_config(db)
    code = await arrival.get_code(db, booking.id)
    provider = await provider_service.get_by_user(db, user.id)
    is_provider = provider is not None and provider.id == booking.provider_id
    return booking, config, code, is_provider


@router.get("/{booking_id}/arrival", response_model=ArrivalState)
async def get_arrival(booking_id: uuid.UUID, user: CurrentUser, db: DB):
    """Current check-in state. The code is only included for the provider."""
    booking, config, code, is_provider = await _arrival_view(db, booking_id, user)
    return arrival.state(booking, code, config, for_provider=is_provider)


@router.post(
    "/{booking_id}/arrival",
    response_model=ArrivalState,
    dependencies=[Depends(rate_limit("arrival_announce", 10, 300))],
)
async def announce_arrival(
    booking_id: uuid.UUID,
    data: ArrivalAnnounce,
    user: CurrentUser,
    db: DB,
    background: BackgroundTasks,
):
    """Renter: "I've reached". Issues a code and sends it to the provider."""
    booking = await service.get_for_user(db, booking_id, user)
    config = await get_config(db)
    code = await arrival.announce(db, booking, user, config, data.latitude, data.longitude)
    await notifications.arrival_announced(
        db, background, booking, code.code, config.arrival_code_ttl_minutes
    )
    await db.commit()
    await db.refresh(code)
    await db.refresh(booking)
    return arrival.state(booking, code, config, for_provider=False)


@router.post(
    "/{booking_id}/arrival/verify",
    response_model=BookingOut,
    dependencies=[Depends(rate_limit("arrival_verify", 20, 300))],
)
async def verify_arrival(
    booking_id: uuid.UUID,
    data: ArrivalVerify,
    user: CurrentUser,
    db: DB,
    background: BackgroundTasks,
):
    """Renter enters the code the provider gave them; booking becomes ACTIVE."""
    booking = await service.get_for_user(db, booking_id, user)
    config = await get_config(db)
    was_active = booking.status.value == "ACTIVE"
    booking = await arrival.verify(db, booking, user, data.code, config)
    if not was_active:
        await notifications.arrival_verified(db, background, booking)
    await db.commit()
    await db.refresh(booking)
    return await serializers.to_out(db, booking, user, config)


# --------------------------------------------------------------------------- #
# Overstay
# --------------------------------------------------------------------------- #
@router.get("/{booking_id}/overstay", response_model=OverstayQuote)
async def get_overstay(booking_id: uuid.UUID, user: CurrentUser, db: DB):
    """The live meter: what is owed right now for running over."""
    booking = await service.get_for_user(db, booking_id, user)
    config = await get_config(db)
    return overstay.quote(booking, config)


@router.post("/{booking_id}/end", response_model=BookingOut)
async def end_booking(booking_id: uuid.UUID, user: CurrentUser, db: DB, background: BackgroundTasks):
    """Finish parking and leave.

    Refuses while money is owed — the top-up is paid through the payments module
    first, which is what marks `overstay_paid_at`. Keeping the charge out of this
    endpoint keeps payment handling in one place.
    """
    booking = await service.get_for_user(db, booking_id, user)
    if booking.renter_id != user.id:
        raise Forbidden("This booking belongs to another account")
    config = await get_config(db)
    booking = await service.end_parking(db, booking, config)
    await notifications.booking_completed(db, background, booking)
    await db.commit()
    await db.refresh(booking)
    return await serializers.to_out(db, booking, user, config)


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

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status

from app.core.deps import DB, CurrentUser
from app.core.ratelimit import rate_limit
from app.modules.bookings import notifications, serializers, service as booking_service
from app.modules.bookings.schemas import BookingOut
from app.modules.payments import service
from app.modules.payments.schemas import PaymentConfirm, PaymentCreate, PaymentOut, PaymentSession
from app.modules.settings.service import get_config

router = APIRouter(prefix="/payments", tags=["payments"])

# Webhook bodies above this are never legitimate and shouldn't be buffered.
MAX_WEBHOOK_BYTES = 256 * 1024


@router.post(
    "/create",
    response_model=PaymentSession,
    dependencies=[Depends(rate_limit("payment_create", 20, 60))],
)
async def create_payment(data: PaymentCreate, user: CurrentUser, db: DB):
    """Open a gateway order for a booking that is awaiting payment."""
    booking = await booking_service.get_for_user(db, data.booking_id, user)
    payment, client_payload = await service.start_payment(db, booking, user)
    await db.commit()
    await db.refresh(payment)
    return PaymentSession(
        payment_id=payment.id,
        booking_id=booking.id,
        gateway=payment.gateway,
        order_id=payment.gateway_order_id,
        amount=payment.amount,
        currency=payment.currency,
        client_payload=client_payload,
    )


@router.post(
    "/confirm",
    response_model=BookingOut,
    dependencies=[Depends(rate_limit("payment_confirm", 30, 60))],
)
async def confirm_payment(data: PaymentConfirm, user: CurrentUser, db: DB, background: BackgroundTasks):
    """Verify a completed checkout and confirm the booking.

    The webhook does the same job independently, so a renter who loses their
    connection here still ends up with a confirmed booking.
    """
    payment, booking = await service.confirm_payment(db, data.order_id, data.payment_id, data.signature)
    if booking.renter_id != user.id:
        # The signature proved the payment, but this caller isn't its owner.
        from app.core.errors import Forbidden

        raise Forbidden("This payment belongs to another account")
    config = await get_config(db)
    await notifications.booking_confirmed(db, background, booking)
    await db.commit()
    await db.refresh(booking)
    return await serializers.to_out(db, booking, user, config)


@router.get("/booking/{booking_id}", response_model=PaymentOut | None)
async def get_booking_payment(booking_id: uuid.UUID, user: CurrentUser, db: DB):
    await booking_service.get_for_user(db, booking_id, user)
    return await service.payment_for_booking(db, booking_id)


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def payment_webhook(request: Request, db: DB, background: BackgroundTasks):
    """Gateway callback. Unauthenticated by design — the signature in the headers
    is the authentication, and it is verified before anything is read from the body.
    """
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        return Response(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    headers = {key.lower(): value for key, value in request.headers.items()}
    result = await service.handle_webhook(db, body, headers)
    if result.get("status") == "captured" and result.get("booking_id"):
        from app.modules.bookings.models import Booking

        booking = await db.get(Booking, uuid.UUID(result["booking_id"]))
        if booking is not None:
            await notifications.booking_confirmed(db, background, booking)
    await db.commit()
    return result

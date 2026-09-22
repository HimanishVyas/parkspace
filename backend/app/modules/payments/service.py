"""Payment orchestration.

Kept deliberately separate from booking rules (PRD rule 9): this module knows
how to take money and give it back, and calls into `bookings.service` for the
single state transition it is allowed to trigger.
"""
import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.time import utcnow
from app.modules.bookings import service as booking_service
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.payments.gateway import (
    GatewayWebhook,
    PaymentError,
    PaymentIntent,
    SignatureError,
    get_gateway,
)
from app.modules.payments.models import Payment, PaymentStatus, Refund, RefundStatus, WebhookEvent
from app.modules.users.models import User

logger = logging.getLogger(__name__)

# Payment attempts that can still be completed by the client.
_OPEN_STATUSES = (PaymentStatus.CREATED, PaymentStatus.PENDING)


async def start_overstay_payment(
    db: AsyncSession, booking: Booking, user: User, config
) -> tuple[Payment, dict]:
    """Open a gateway order for the extra time a renter owes.

    Kept separate from `start_payment` because the booking is past its window
    and in a state that function rightly refuses; the amount comes from the
    meter, not the original quote.
    """
    from app.modules.bookings import overstay as overstay_calc

    if booking.renter_id != user.id:
        raise Forbidden("This booking belongs to another account")
    if booking.overstay_paid_at is not None:
        raise Conflict("The extra time is already paid for", code="ALREADY_PAID")

    owed = overstay_calc.freeze(booking, config)
    if owed <= 0:
        raise Conflict("There is nothing extra to pay", code="NOTHING_DUE")

    gateway = get_gateway()
    existing = await db.scalar(
        select(Payment)
        .where(
            Payment.booking_id == booking.id,
            Payment.purpose == "OVERSTAY",
            Payment.gateway == gateway.name,
            Payment.status.in_(_OPEN_STATUSES),
        )
        .order_by(Payment.created_at.desc())
    )
    if existing is not None and existing.gateway_payload:
        client_payload = existing.gateway_payload.get("client_payload")
        if client_payload and Decimal(existing.amount) == owed:
            return existing, client_payload

    order = await gateway.create_payment(
        PaymentIntent(
            amount=owed,
            currency=booking.currency,
            reference=f"{booking.reference}-OS",
            description=f"Extra parking time {booking.reference}",
            customer_email=user.email,
            customer_name=user.full_name,
            notes={"booking_id": str(booking.id), "purpose": "OVERSTAY"},
        )
    )
    payment = Payment(
        booking_id=booking.id,
        purpose="OVERSTAY",
        gateway=gateway.name,
        gateway_order_id=order.order_id,
        amount=owed,
        currency=booking.currency,
        gateway_payload={"client_payload": order.client_payload, "order": order.raw},
    )
    db.add(payment)
    await db.flush()
    return payment, order.client_payload


async def sandbox_complete(db: AsyncSession, booking: Booking, user: User):
    """Complete a sandbox payment entirely server-side.

    The mock gateway's "signature" is an HMAC with a secret the browser would
    have to hold anyway, so signing in the browser adds no security — and it
    forced the checkout page to use SubtleCrypto, which browsers only expose on
    a secure context. That made paying impossible over plain http on a LAN
    address. Signing here instead keeps the real verification path under test
    while letting the client just say "the sandbox payment succeeded".

    Refuses to run outside the mock gateway, and never in production.
    """
    gateway = get_gateway()
    if (
        gateway.name != "mock"
        or not settings.allow_sandbox_payments
        or settings.environment == "production"
    ):
        raise Conflict(
            "Sandbox completion is only available with the mock gateway",
            code="NOT_SANDBOX",
        )
    from app.modules.bookings.models import BookingStatus as _Status
    from app.modules.settings.service import get_config as _get_config

    if booking.status in (_Status.ACTIVE, _Status.OVERSTAYING, _Status.COMPLETED):
        config = await _get_config(db)
        payment, client_payload = await start_overstay_payment(db, booking, user, config)
    else:
        payment, client_payload = await start_payment(db, booking, user)
    payment_id = (client_payload or {}).get("mock_payment_id")
    if not payment_id:
        raise Conflict("This payment session cannot be completed", code="INVALID_STATE")
    signature = gateway._sign(f"{payment.gateway_order_id}|{payment_id}")
    return await confirm_payment(db, payment.gateway_order_id, payment_id, signature)


async def start_payment(db: AsyncSession, booking: Booking, user: User) -> tuple[Payment, dict]:
    """Create (or reuse) a gateway order for a booking awaiting payment."""
    if booking.renter_id != user.id:
        raise Forbidden("This booking belongs to another account")
    if booking.status == BookingStatus.PENDING_APPROVAL:
        raise Conflict("The provider has not accepted this booking yet", code="AWAITING_APPROVAL")
    if booking.status != BookingStatus.PENDING_PAYMENT:
        raise Conflict(
            f"A {booking.status.value.lower()} booking cannot be paid for", code="INVALID_STATE"
        )
    if booking.hold_expires_at is not None and booking.hold_expires_at <= utcnow():
        raise Conflict("This booking has expired. Please book again.", code="HOLD_EXPIRED")

    gateway = get_gateway()
    existing = await db.scalar(
        select(Payment)
        .where(
            Payment.booking_id == booking.id,
            Payment.gateway == gateway.name,
            Payment.status.in_(_OPEN_STATUSES),
        )
        .order_by(Payment.created_at.desc())
    )
    if existing is not None and existing.gateway_payload:
        # Reuse the open order so a refreshed checkout page doesn't orphan orders.
        client_payload = existing.gateway_payload.get("client_payload")
        if client_payload:
            return existing, client_payload

    order = await gateway.create_payment(
        PaymentIntent(
            amount=Decimal(booking.total_amount),
            currency=booking.currency,
            reference=booking.reference,
            description=f"Parking booking {booking.reference}",
            customer_email=user.email,
            customer_name=user.full_name,
            notes={"booking_id": str(booking.id)},
        )
    )
    payment = Payment(
        booking_id=booking.id,
        gateway=gateway.name,
        gateway_order_id=order.order_id,
        amount=Decimal(booking.total_amount),
        currency=booking.currency,
        status=PaymentStatus.CREATED,
        gateway_payload={"client_payload": order.client_payload, "order": order.raw},
    )
    db.add(payment)
    await db.flush()
    return payment, order.client_payload


async def confirm_payment(
    db: AsyncSession, order_id: str, gateway_payment_id: str, signature: str
) -> tuple[Payment, Booking]:
    """Verify a client-reported payment and confirm the booking.

    The signature check is what makes this safe to expose: a client cannot mark
    its own booking paid without the gateway's secret.
    """
    payment = await db.scalar(select(Payment).where(Payment.gateway_order_id == order_id))
    if payment is None:
        raise NotFound("Payment not found")
    booking = await db.get(Booking, payment.booking_id)
    if booking is None:
        raise NotFound("Booking not found")

    if payment.status == PaymentStatus.CAPTURED:
        # Idempotent: a double submit from the checkout page is not an error.
        return payment, booking

    gateway = get_gateway(payment.gateway)
    try:
        result = await gateway.verify_payment(order_id, gateway_payment_id, signature)
    except SignatureError:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "Signature verification failed"
        await db.flush()
        raise ValidationFailed("Payment could not be verified", code="INVALID_SIGNATURE")

    await _capture(db, payment, booking, result.payment_id, result.method, result.raw)
    return payment, booking


async def _capture(
    db: AsyncSession,
    payment: Payment,
    booking: Booking,
    gateway_payment_id: str,
    method: str | None,
    raw: dict | None,
) -> None:
    payment.status = PaymentStatus.CAPTURED
    payment.gateway_payment_id = gateway_payment_id
    payment.method = method
    payment.captured_at = utcnow()
    payment.gateway_payload = {**(payment.gateway_payload or {}), "capture": raw or {}}
    if payment.purpose == "OVERSTAY":
        # An overstay top-up settles the meter; it must not re-run the booking
        # confirmation, which would drag a completed booking back to CONFIRMED.
        booking.overstay_paid_at = utcnow()
    else:
        await booking_service.mark_paid(db, booking)
    await db.flush()


async def handle_webhook(
    db: AsyncSession, body: bytes, headers: dict[str, str], gateway_name: str | None = None
) -> dict:
    """Process a gateway webhook: verify the signature, de-duplicate, then act.

    Webhooks are the authoritative confirmation — a renter who closes the tab
    mid-redirect still gets a confirmed booking.
    """
    gateway = get_gateway(gateway_name)
    try:
        event: GatewayWebhook = gateway.parse_webhook(body, headers)
    except SignatureError:
        raise ValidationFailed("Invalid webhook signature", code="INVALID_SIGNATURE")
    except (ValueError, PaymentError):
        raise ValidationFailed("Malformed webhook payload", code="INVALID_PAYLOAD")

    # Recording the event id first makes replay a no-op. The insert lives inside
    # a SAVEPOINT (with its `add`, which is what makes the rollback recoverable)
    # so a duplicate doesn't poison the surrounding transaction.
    try:
        async with db.begin_nested():
            db.add(
                WebhookEvent(
                    gateway=gateway.name,
                    event_id=event.event_id,
                    event_type=event.event_type,
                    payload=event.raw,
                )
            )
            await db.flush()
    except IntegrityError:
        logger.info("Ignoring duplicate webhook %s/%s", gateway.name, event.event_id)
        return {"status": "duplicate"}

    if not event.order_id:
        return {"status": "ignored"}
    payment = await db.scalar(select(Payment).where(Payment.gateway_order_id == event.order_id))
    if payment is None:
        logger.warning("Webhook for unknown order %s", event.order_id)
        return {"status": "unknown_order"}
    booking = await db.get(Booking, payment.booking_id)
    if booking is None:
        return {"status": "unknown_booking"}

    if event.status in ("captured", "authorized", "paid") and payment.status != PaymentStatus.CAPTURED:
        await _capture(db, payment, booking, event.payment_id or "", None, event.raw)
        return {"status": "captured", "booking_id": str(booking.id)}
    if event.status == "failed" and payment.status in _OPEN_STATUSES:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "Reported failed by gateway"
        await db.flush()
        return {"status": "failed"}
    return {"status": "ignored"}


async def refund_booking(
    db: AsyncSession, booking: Booking, amount: Decimal, reason: str | None = None
) -> Refund | None:
    """Refund up to `amount` against the booking's captured payment.

    Returns None when there is nothing to refund (an unpaid booking, or a
    zero-refund cancellation under the policy).
    """
    if amount <= 0:
        return None
    payment = await db.scalar(
        select(Payment).where(Payment.booking_id == booking.id, Payment.status == PaymentStatus.CAPTURED)
    )
    if payment is None or not payment.gateway_payment_id:
        return None

    already = payment.refunded_amount
    refundable = Decimal(payment.amount) - already
    amount = min(amount, refundable)
    if amount <= 0:
        return None

    gateway = get_gateway(payment.gateway)
    refund = Refund(payment_id=payment.id, amount=amount, reason=reason, status=RefundStatus.PENDING)
    db.add(refund)
    await db.flush()
    try:
        result = await gateway.refund_payment(payment.gateway_payment_id, amount, reason)
    except PaymentError as exc:
        # Keep the row: a failed refund is a support case, not something to lose.
        refund.status = RefundStatus.FAILED
        refund.gateway_payload = {"error": exc.message}
        await db.flush()
        logger.error("Refund failed for booking %s: %s", booking.reference, exc.message)
        return refund

    refund.status = RefundStatus.PROCESSED
    refund.gateway_refund_id = result.refund_id
    refund.gateway_payload = result.raw
    total_refunded = already + amount
    payment.status = (
        PaymentStatus.REFUNDED
        if total_refunded >= Decimal(payment.amount)
        else PaymentStatus.PARTIALLY_REFUNDED
    )
    await db.flush()
    return refund


async def payment_for_booking(db: AsyncSession, booking_id: uuid.UUID) -> Payment | None:
    return await db.scalar(
        select(Payment)
        .where(Payment.booking_id == booking_id)
        .order_by(Payment.created_at.desc())
        .limit(1)
    )

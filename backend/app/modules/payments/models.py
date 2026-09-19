import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin, str_enum


class PaymentStatus(str, enum.Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


class RefundStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class Payment(UUIDPkMixin, TimestampMixin, Base):
    """One payment attempt against a booking.

    Only gateway references are stored — never card numbers, CVV or any other
    cardholder data. `gateway_payload` holds the gateway's own non-sensitive
    response for support and reconciliation.
    """

    __tablename__ = "payments"
    __table_args__ = (
        Index("uq_payments_gateway_order", "gateway", "gateway_order_id", unique=True),
        Index("ix_payments_booking_status", "booking_id", "status"),
    )

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    # A booking can be paid for twice: once up front, and again for an overstay
    # top-up. Without this the two would be indistinguishable in reconciliation.
    purpose: Mapped[str] = mapped_column(String(20), default="BOOKING", index=True)
    gateway: Mapped[str] = mapped_column(String(30))
    # The gateway's order/intent id the client uses to complete the payment.
    gateway_order_id: Mapped[str] = mapped_column(String(120))
    # Set once the gateway reports an actual payment against that order.
    gateway_payment_id: Mapped[str | None] = mapped_column(String(120), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[PaymentStatus] = mapped_column(str_enum(PaymentStatus), default=PaymentStatus.CREATED, index=True)
    method: Mapped[str | None] = mapped_column(String(40))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    gateway_payload: Mapped[dict | None] = mapped_column(JSONB)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    refunds: Mapped[list["Refund"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def refunded_amount(self) -> Decimal:
        return sum(
            (r.amount for r in self.refunds if r.status == RefundStatus.PROCESSED), start=Decimal("0.00")
        )


class Refund(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "refunds"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"), index=True
    )
    gateway_refund_id: Mapped[str | None] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[RefundStatus] = mapped_column(str_enum(RefundStatus), default=RefundStatus.PENDING)
    reason: Mapped[str | None] = mapped_column(String(300))
    gateway_payload: Mapped[dict | None] = mapped_column(JSONB)

    payment: Mapped[Payment] = relationship(back_populates="refunds")


class WebhookEvent(UUIDPkMixin, Base):
    """Gateway webhook de-duplication. A gateway may deliver the same event many
    times; recording the id makes handling idempotent."""

    __tablename__ = "webhook_events"
    __table_args__ = (Index("uq_webhook_events_gateway_event", "gateway", "event_id", unique=True),)

    gateway: Mapped[str] = mapped_column(String(30))
    event_id: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str | None] = mapped_column(String(80))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PayoutStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PAID = "PAID"
    FAILED = "FAILED"


class Payout(UUIDPkMixin, TimestampMixin, Base):
    """Money owed to a provider for a set of completed bookings.

    V1 records payouts and marks them paid manually from the admin dashboard; the
    shape is ready for an automated transfer API later.
    """

    __tablename__ = "payouts"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[PayoutStatus] = mapped_column(str_enum(PayoutStatus), default=PayoutStatus.PENDING, index=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PayoutBooking(Base):
    """Which bookings a payout settled (keeps a booking from being paid twice)."""

    __tablename__ = "payout_bookings"

    payout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payouts.id", ondelete="CASCADE"), primary_key=True
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True, unique=True
    )

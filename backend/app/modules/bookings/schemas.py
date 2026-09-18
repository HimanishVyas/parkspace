import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.bookings.models import BookingStatus
from app.modules.parking.models import ParkingType, PricingUnit, VehicleType


class QuoteRequest(BaseModel):
    parking_space_id: uuid.UUID
    unit: PricingUnit
    start_at: datetime
    # Either end_at, or quantity (hours/days/months) for the server to derive it.
    end_at: datetime | None = None
    quantity: int | None = Field(default=None, ge=1, le=365)


class QuoteResponse(BaseModel):
    parking_space_id: uuid.UUID
    unit: PricingUnit
    start_at: datetime
    end_at: datetime
    quantity: Decimal
    unit_price: Decimal
    base_amount: Decimal
    platform_fee: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str
    available: bool
    # Why the window can't be booked, when `available` is false.
    unavailable_reason: str | None = None


class BookingCreate(BaseModel):
    parking_space_id: uuid.UUID
    vehicle_id: uuid.UUID
    unit: PricingUnit
    start_at: datetime
    end_at: datetime | None = None
    quantity: int | None = Field(default=None, ge=1, le=365)
    renter_notes: str | None = Field(default=None, max_length=1000)


class BookingCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class BookingReject(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class BookingSpaceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    parking_type: ParkingType
    address_line: str
    landmark: str | None
    city: str
    latitude: float
    longitude: float
    photo_url: str | None = None


class BookingPartyOut(BaseModel):
    """Counterparty details. Shown to the provider once a booking is confirmed so
    they know who is arriving; renters only ever see the provider's display name."""

    model_config = ConfigDict(from_attributes=True)

    full_name: str
    phone: str | None = None


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    status: BookingStatus
    parking_space: BookingSpaceSummary
    provider_name: str
    unit: PricingUnit
    start_at: datetime
    end_at: datetime
    quantity: Decimal
    unit_price: Decimal
    base_amount: Decimal
    platform_fee: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    refund_amount: Decimal
    currency: str
    vehicle_number: str
    vehicle_type: VehicleType
    renter_notes: str | None
    hold_expires_at: datetime | None
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime
    # Released only once the booking is confirmed (PRD §18).
    access_instructions: str | None = None
    # Present on the provider's copy of the booking.
    renter: BookingPartyOut | None = None
    # What the provider actually earns; omitted from the renter's view.
    provider_earning: Decimal | None = None
    can_cancel: bool = False
    refund_if_cancelled_now: Decimal | None = None


class BookingList(BaseModel):
    items: list[BookingOut]
    total: int
    limit: int
    offset: int


class BookingConfirmation(BaseModel):
    """PRD §19 — the confirmation the renter shows at the gate.

    `qr_payload` is the string the client renders as a QR code; in V1 it is a
    digital identifier only and controls no physical access.
    """

    booking_id: uuid.UUID
    reference: str
    status: BookingStatus
    parking_location: str
    latitude: float
    longitude: float
    provider_name: str
    renter_name: str
    vehicle_number: str
    start_at: datetime
    end_at: datetime
    total_amount: Decimal
    currency: str
    parking_instructions: str | None
    qr_payload: str

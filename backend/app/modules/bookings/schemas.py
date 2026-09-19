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
    # The bay the renter picked. Omitted means "any" and the server assigns the
    # lowest free one, exactly as before. A named bay that is taken FAILS rather
    # than silently moving them somewhere else.
    slot_index: int | None = Field(default=None, ge=0, le=499)


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
    # Drives the check-in panel on the booking page.
    requires_arrival_code: bool = False


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
    # What is painted on the floor, when the space has named bays.
    bay_label: str | None = None
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
    overstay_minutes: int = 0
    overstay_amount: Decimal = Decimal("0")
    overstay_paid_at: datetime | None = None
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


class ArrivalAnnounce(BaseModel):
    """Optionally carries the renter's position, so the server can check they
    are actually at the space. Omitted when the browser denies geolocation —
    which it always does on a non-secure origin — and the check is then skipped.
    """

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class ArrivalVerify(BaseModel):
    code: str = Field(min_length=4, max_length=10)


class ArrivalState(BaseModel):
    booking_id: uuid.UUID
    status: BookingStatus
    announced: bool
    verified: bool
    expired: bool
    expires_at: datetime | None
    attempts_left: int | None
    waiting_minutes: float | None
    escalate: bool
    # Populated only on the provider's view of this booking.
    code: str | None


class WaitingArrival(BaseModel):
    """A renter at a gate, from the provider's side. Carries the code, because
    reading it out is the entire job of this screen."""

    booking_id: uuid.UUID
    reference: str
    space_title: str
    renter_name: str
    renter_phone: str | None
    vehicle_number: str
    code: str
    waiting_minutes: float
    expires_at: datetime


class OverstayQuote(BaseModel):
    booking_id: uuid.UUID
    status: BookingStatus
    overstaying: bool
    grace_ends_at: datetime
    overstay_minutes: int
    overstay_amount: Decimal
    amount_due: Decimal
    paid: bool
    # The meter has hit its cap and stopped accruing.
    meter_capped: bool
    meter_stops_at: datetime
    hourly_rate: Decimal
    currency: str

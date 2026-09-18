import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.bookings.models import BookingStatus
from app.modules.parking.models import ListingStatus
from app.modules.payments.models import PayoutStatus
from app.modules.providers.models import ProviderStatus, ProviderType, VerificationStatus
from app.modules.users.models import UserRole, UserStatus


class AdminDashboardOut(BaseModel):
    total_users: int
    total_renters: int
    total_providers: int
    verified_providers: int
    total_listings: int
    active_listings: int
    pending_listings: int
    total_bookings: int
    todays_bookings: int
    active_bookings: int
    monthly_booking_value: Decimal
    monthly_platform_revenue: Decimal
    lifetime_booking_value: Decimal
    lifetime_platform_revenue: Decimal
    open_reports: int
    currency: str = "INR"


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    phone: str | None
    full_name: str
    role: UserRole
    status: UserStatus
    email_verified: bool
    created_at: datetime


class UserStatusChange(BaseModel):
    status: UserStatus
    reason: str | None = Field(default=None, max_length=500)


class AdminProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    provider_type: ProviderType
    display_name: str
    contact_phone: str | None
    address: str | None
    verification_status: VerificationStatus
    verification_notes: str | None
    status: ProviderStatus
    authority_declared_at: datetime | None
    created_at: datetime
    listing_count: int = 0
    total_earnings: Decimal = Decimal("0.00")


class ProviderStatusChange(BaseModel):
    status: ProviderStatus
    reason: str | None = Field(default=None, max_length=500)


class AdminListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    provider_name: str | None = None
    title: str
    city: str
    status: ListingStatus
    rejection_reason: str | None
    authority_confirmed: bool
    total_slots: int
    rating_average: Decimal | None
    rating_count: int
    created_at: datetime


class ListingDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class AdminBookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    status: BookingStatus
    renter_name: str | None = None
    provider_name: str | None = None
    parking_title: str | None = None
    vehicle_number: str
    start_at: datetime
    end_at: datetime
    total_amount: Decimal
    commission_amount: Decimal
    provider_earning: Decimal
    refund_amount: Decimal
    currency: str
    created_at: datetime


class PaginatedResponse(BaseModel):
    total: int
    limit: int
    offset: int


class AdminUserList(PaginatedResponse):
    items: list[AdminUserOut]


class AdminProviderList(PaginatedResponse):
    items: list[AdminProviderOut]


class AdminListingList(PaginatedResponse):
    items: list[AdminListingOut]


class AdminBookingList(PaginatedResponse):
    items: list[AdminBookingOut]


class PayoutCreate(BaseModel):
    provider_id: uuid.UUID
    # Settles every eligible completed booking up to this moment.
    up_to: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)


class PayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    amount: Decimal
    currency: str
    status: PayoutStatus
    period_start: datetime | None
    period_end: datetime | None
    reference: str | None
    notes: str | None
    paid_at: datetime | None
    created_at: datetime
    booking_count: int = 0


class PayoutMarkPaid(BaseModel):
    reference: str | None = Field(default=None, max_length=120)


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    data: dict | None
    ip_address: str | None
    created_at: datetime

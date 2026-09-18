import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.providers.models import (
    AgreementStatus,
    ProviderStatus,
    ProviderType,
    VerificationStatus,
)
from app.modules.users.schemas import normalize_phone


class SocietyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    registration_number: str | None
    address: str | None
    city: str | None
    contact_name: str | None
    contact_phone: str | None
    contact_email: str | None
    description: str | None


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_type: ProviderType
    display_name: str
    contact_phone: str | None
    address: str | None
    verification_status: VerificationStatus
    status: ProviderStatus
    authority_declared_at: datetime | None
    society: SocietyOut | None = None
    created_at: datetime


class ProviderPublic(BaseModel):
    """Provider information safe to show on a public listing — Trust principle:
    enough to feel comfortable, nothing personal."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    provider_type: ProviderType
    verification_status: VerificationStatus
    member_since: datetime = Field(validation_alias="created_at")


class ProviderUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=200)
    contact_phone: str | None = None
    address: str | None = Field(default=None, max_length=500)

    _phone = field_validator("contact_phone")(normalize_phone)


class SocietyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    registration_number: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=100)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = None
    contact_email: EmailStr | None = None
    description: str | None = Field(default=None, max_length=2000)

    _phone = field_validator("contact_phone")(normalize_phone)


class VerificationSubmit(BaseModel):
    """Basic V1 verification: the provider supplies contact/address details and
    declares they are authorised to rent out their spaces."""

    contact_phone: str
    address: str = Field(min_length=5, max_length=500)
    authority_declaration: bool

    _phone = field_validator("contact_phone")(normalize_phone)

    @field_validator("authority_declaration")
    @classmethod
    def _must_declare(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must confirm you are authorised to offer these parking spaces")
        return v


class VerificationDecision(BaseModel):
    status: Literal["VERIFIED", "REJECTED", "PENDING_VERIFICATION", "UNVERIFIED"]
    notes: str | None = Field(default=None, max_length=2000)


class AgreementCreate(BaseModel):
    start_date: date
    end_date: date | None = None
    revenue_share_percent: Decimal = Field(ge=0, le=100)
    parking_space_count: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class AgreementUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    revenue_share_percent: Decimal | None = Field(default=None, ge=0, le=100)
    parking_space_count: int | None = Field(default=None, ge=0)
    status: AgreementStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)


class AgreementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    start_date: date
    end_date: date | None
    revenue_share_percent: Decimal
    parking_space_count: int | None
    status: AgreementStatus
    notes: str | None
    created_at: datetime


class EarningsSummaryOut(BaseModel):
    gross_booking_value: Decimal
    platform_fee: Decimal
    provider_earnings: Decimal
    booking_count: int


class MonthlyEarningsOut(EarningsSummaryOut):
    month: str


class ProviderDashboardOut(BaseModel):
    total_earnings: Decimal
    pending_payout: Decimal
    completed_payout: Decimal
    upcoming_earnings: Decimal
    current_month: EarningsSummaryOut
    total_listings: int
    active_listings: int
    upcoming_bookings: int
    todays_bookings: int
    total_bookings: int


class EarningsOut(BaseModel):
    total_earnings: Decimal
    pending_payout: Decimal
    completed_payout: Decimal
    upcoming_earnings: Decimal
    currency: str = "INR"
    months: list[MonthlyEarningsOut]

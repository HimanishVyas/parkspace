import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.parking.models import ListingStatus, ParkingType, PricingUnit, VehicleType
from app.modules.providers.schemas import ProviderPublic


class PriceIn(BaseModel):
    unit: PricingUnit
    amount: Decimal = Field(gt=0, le=Decimal("1000000"))


class PriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unit: PricingUnit
    amount: Decimal


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    caption: str | None
    sort_order: int


class ParkingSpaceBase(BaseModel):
    title: str = Field(min_length=4, max_length=150)
    description: str | None = Field(default=None, max_length=4000)
    parking_type: ParkingType
    vehicle_types: list[VehicleType] = Field(min_length=1)
    address_line: str = Field(min_length=5, max_length=300)
    landmark: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=2, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=12)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    access_instructions: str | None = Field(default=None, max_length=2000)
    total_slots: int = Field(default=1, ge=1, le=500)
    requires_approval: bool = False
    # Renter must enter a code from the provider before parking (unattended spaces).
    requires_arrival_code: bool = False

    @field_validator("vehicle_types")
    @classmethod
    def _unique(cls, value: list[VehicleType]) -> list[VehicleType]:
        return list(dict.fromkeys(value))


class ParkingSpaceCreate(ParkingSpaceBase):
    prices: list[PriceIn] = Field(min_length=1)
    # PRD §32: the provider must confirm they may rent this space out.
    authority_confirmed: bool

    @field_validator("authority_confirmed")
    @classmethod
    def _must_confirm(cls, value: bool) -> bool:
        if not value:
            raise ValueError(
                "You must confirm that you have the rights or authorization to offer this parking space"
            )
        return value

    @model_validator(mode="after")
    def _unique_units(self):
        units = [p.unit for p in self.prices]
        if len(units) != len(set(units)):
            raise ValueError("Only one price per duration type")
        return self


class ParkingSpaceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=4, max_length=150)
    description: str | None = Field(default=None, max_length=4000)
    parking_type: ParkingType | None = None
    vehicle_types: list[VehicleType] | None = Field(default=None, min_length=1)
    address_line: str | None = Field(default=None, min_length=5, max_length=300)
    landmark: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=12)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    access_instructions: str | None = Field(default=None, max_length=2000)
    total_slots: int | None = Field(default=None, ge=1, le=500)
    requires_approval: bool | None = None
    requires_arrival_code: bool | None = None
    prices: list[PriceIn] | None = Field(default=None, min_length=1)


class ParkingSpaceOut(ParkingSpaceBase):
    """Full listing as its own provider (and admins) see it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    status: ListingStatus
    rejection_reason: str | None
    authority_confirmed: bool
    rating_average: Decimal | None
    rating_count: int
    prices: list[PriceOut]
    photos: list[PhotoOut]
    created_at: datetime
    updated_at: datetime


class ParkingSpacePublic(BaseModel):
    """Renter-facing listing. Access instructions are withheld until a booking
    is confirmed, and the provider appears only as a limited profile."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    parking_type: ParkingType
    vehicle_types: list[VehicleType]
    address_line: str
    landmark: str | None
    city: str
    state: str | None
    pincode: str | None
    latitude: float
    longitude: float
    total_slots: int
    requires_approval: bool
    requires_arrival_code: bool
    rating_average: Decimal | None
    rating_count: int
    prices: list[PriceOut]
    photos: list[PhotoOut]
    provider: ProviderPublic
    created_at: datetime
    # Populated by search; distance from the searched point in kilometres.
    distance_km: float | None = None


class SearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    parking_type: ParkingType
    vehicle_types: list[VehicleType]
    city: str
    latitude: float
    longitude: float
    rating_average: Decimal | None
    rating_count: int
    prices: list[PriceOut]
    photo_url: str | None
    distance_km: float | None
    # True when the listing was checked against the searched dates and is free.
    available: bool = True


class SearchResponse(BaseModel):
    items: list[SearchResult]
    total: int
    limit: int
    offset: int


class StatusChange(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class PhotoReorder(BaseModel):
    photo_ids: list[uuid.UUID] = Field(min_length=1)


class GeocodeOut(BaseModel):
    latitude: float
    longitude: float
    display_name: str


class BayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slot_index: int
    label: str
    row_index: int
    col_index: int
    is_active: bool
    # Whether this bay is free for the window that was asked about. None when no
    # window was given, because then the question has no answer.
    taken: bool | None = None


class BayLayout(BaseModel):
    parking_space_id: uuid.UUID
    total_slots: int
    row_width: int
    bays: list[BayOut]


class BayRename(BaseModel):
    """Provider-supplied labels, keyed by slot index."""

    labels: dict[int, str] = Field(min_length=1)


class BayActive(BaseModel):
    is_active: bool

import enum
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin, str_enum
from app.modules.providers.models import Provider


class ParkingType(str, enum.Enum):
    OPEN = "OPEN"
    COVERED = "COVERED"
    BASEMENT = "BASEMENT"
    GARAGE = "GARAGE"


class VehicleType(str, enum.Enum):
    BIKE = "BIKE"
    CAR = "CAR"
    SUV = "SUV"


class PricingUnit(str, enum.Enum):
    """Booking duration types. New units can be added without a schema change —
    prices live in their own table keyed by unit."""

    HOURLY = "HOURLY"
    DAILY = "DAILY"
    MONTHLY = "MONTHLY"


class ListingStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    PUBLISHED = "PUBLISHED"
    PAUSED = "PAUSED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"


# Statuses in which a listing may be booked by a renter.
BOOKABLE_STATUSES = (ListingStatus.PUBLISHED,)


class ParkingSpace(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "parking_spaces"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        # Bounding-box prefilter for radius search hits this index first.
        Index("ix_parking_spaces_lat_lon", "latitude", "longitude"),
        Index("ix_parking_spaces_status_city", "status", "city"),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    parking_type: Mapped[ParkingType] = mapped_column(str_enum(ParkingType), index=True)
    # Which vehicle types fit. An array keeps "add a new vehicle type" a code change.
    vehicle_types: Mapped[list[str]] = mapped_column(ARRAY(String(20)))

    address_line: Mapped[str] = mapped_column(String(300))
    landmark: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100), index=True)
    state: Mapped[str | None] = mapped_column(String(100))
    pincode: Mapped[str | None] = mapped_column(String(12))
    latitude: Mapped[float] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float] = mapped_column(Numeric(9, 6))

    # Shown to the renter only after a booking is confirmed.
    access_instructions: Mapped[str | None] = mapped_column(Text)
    # How many vehicles can park here at once; each booking consumes one slot.
    total_slots: Mapped[int] = mapped_column(Integer, default=1)
    # When true the provider must approve each booking before payment is captured.
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    # When true a confirmed booking only becomes ACTIVE once the renter enters a
    # code the provider gives them on arrival. For spaces with nobody at the gate.
    requires_arrival_code: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[ListingStatus] = mapped_column(str_enum(ListingStatus), default=ListingStatus.DRAFT, index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    # The provider's confirmation that they may rent this space out (PRD §32).
    authority_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Denormalised review aggregates, refreshed when a review is written.
    rating_average: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    rating_count: Mapped[int] = mapped_column(Integer, default=0)

    provider: Mapped[Provider] = relationship(lazy="joined")
    photos: Mapped[list["ParkingPhoto"]] = relationship(
        back_populates="parking_space",
        cascade="all, delete-orphan",
        order_by="ParkingPhoto.sort_order",
        lazy="selectin",
    )
    prices: Mapped[list["ParkingPrice"]] = relationship(
        back_populates="parking_space", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def is_bookable(self) -> bool:
        return self.status in BOOKABLE_STATUSES


class ParkingPrice(UUIDPkMixin, TimestampMixin, Base):
    """One row per duration type the provider offers. A missing row means the
    space cannot be booked for that duration."""

    __tablename__ = "parking_prices"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("uq_parking_prices_space_unit", "parking_space_id", "unit", unique=True),
    )

    parking_space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parking_spaces.id", ondelete="CASCADE"), index=True
    )
    unit: Mapped[PricingUnit] = mapped_column(str_enum(PricingUnit))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    parking_space: Mapped[ParkingSpace] = relationship(back_populates="prices")


class ParkingPhoto(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "parking_photos"

    parking_space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parking_spaces.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(500))
    caption: Mapped[str | None] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    parking_space: Mapped[ParkingSpace] = relationship(back_populates="photos")


class ParkingBay(UUIDPkMixin, TimestampMixin, Base):
    """One named, placed parking bay.

    This is a label and a grid position for a `slot_index` that already exists:
    bookings have always occupied a numbered slot, and the exclusion constraint
    `(parking_space_id, slot_index, period)` has always kept two cars out of one
    bay. Nothing about the concurrency guarantee changes here — the renter simply
    gets to choose the number instead of the server picking the lowest free one.

    `slot_index` is therefore the join to `bookings.slot_index` and must stay
    within the space's `total_slots`.
    """

    __tablename__ = "parking_bays"
    __table_args__ = (
        CheckConstraint("slot_index >= 0", name="bay_slot_index_non_negative"),
        Index("uq_parking_bays_space_slot", "parking_space_id", "slot_index", unique=True),
    )

    parking_space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parking_spaces.id", ondelete="CASCADE"), index=True
    )
    slot_index: Mapped[int] = mapped_column(Integer)
    # What is painted on the floor, e.g. "A-12". Renters and guards say this out
    # loud to each other, so it is the provider's words, not ours.
    label: Mapped[str] = mapped_column(String(20))
    # Where it sits on the picker grid.
    row_index: Mapped[int] = mapped_column(Integer, default=0)
    col_index: Mapped[int] = mapped_column(Integer, default=0)
    # A bay out of service stays in the layout but cannot be booked.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    parking_space: Mapped[ParkingSpace] = relationship()

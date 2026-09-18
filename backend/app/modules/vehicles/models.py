import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin, str_enum
from app.modules.parking.models import VehicleType


class Vehicle(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        # The same plate can't be saved twice by one renter, but two users may
        # both register a shared family vehicle.
        Index("uq_vehicles_user_registration", "user_id", "registration_number", unique=True),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    vehicle_type: Mapped[VehicleType] = mapped_column(str_enum(VehicleType))
    # Stored normalised (uppercase, no spaces/hyphens), e.g. GJ01AB1234.
    registration_number: Mapped[str] = mapped_column(String(20))
    make_model: Mapped[str | None] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(40))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

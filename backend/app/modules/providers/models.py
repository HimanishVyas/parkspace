import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin, str_enum
from app.modules.users.models import User


class ProviderType(str, enum.Enum):
    INDIVIDUAL = "INDIVIDUAL"
    SOCIETY = "SOCIETY"


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class ProviderStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class Provider(UUIDPkMixin, TimestampMixin, Base):
    """A parking supplier: an individual owner or a society/organisation.

    One user owns at most one provider profile. For societies, that user is
    the "society admin".
    """

    __tablename__ = "providers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    provider_type: Mapped[ProviderType] = mapped_column(str_enum(ProviderType))
    display_name: Mapped[str] = mapped_column(String(200))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(String(500))
    verification_status: Mapped[VerificationStatus] = mapped_column(
        str_enum(VerificationStatus), default=VerificationStatus.UNVERIFIED, index=True
    )
    verification_notes: Mapped[str | None] = mapped_column(Text)
    # Timestamp of the provider's declaration that they have authority to rent their spaces.
    authority_declared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ProviderStatus] = mapped_column(str_enum(ProviderStatus), default=ProviderStatus.ACTIVE)

    user: Mapped[User] = relationship(lazy="joined")
    society: Mapped["Society | None"] = relationship(back_populates="provider", uselist=False, lazy="selectin")


class Society(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "societies"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), unique=True
    )
    name: Mapped[str] = mapped_column(String(200))
    registration_number: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(100))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    provider: Mapped[Provider] = relationship(back_populates="society")


class AgreementStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"


class SocietyAgreement(UUIDPkMixin, TimestampMixin, Base):
    """Record of a society's commercial agreement (the legal document lives elsewhere)."""

    __tablename__ = "society_agreements"

    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), index=True
    )
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    # Percent of the base parking price the society receives. The platform keeps the rest
    # (this replaces the default commission while the agreement is ACTIVE).
    revenue_share_percent: Mapped[float] = mapped_column(Numeric(5, 2))
    parking_space_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[AgreementStatus] = mapped_column(str_enum(AgreementStatus), default=AgreementStatus.DRAFT)
    notes: Mapped[str | None] = mapped_column(Text)

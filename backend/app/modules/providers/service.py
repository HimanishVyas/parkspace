import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import Conflict, Forbidden, NotFound
from app.core.time import utcnow
from app.modules.providers.models import (
    AgreementStatus,
    Provider,
    ProviderStatus,
    ProviderType,
    Society,
    SocietyAgreement,
    VerificationStatus,
)
from app.modules.providers.schemas import VerificationSubmit
from app.modules.users.models import User, UserRole


async def create_provider_profile(
    db: AsyncSession, user: User, provider_type: str, organization_name: str | None = None
) -> Provider:
    """Create the provider profile for a user. Called at registration and when a
    renter upgrades to a provider account."""
    existing = await db.scalar(select(Provider).where(Provider.user_id == user.id))
    if existing:
        raise Conflict("This account already has a provider profile", code="PROVIDER_EXISTS")
    ptype = ProviderType(provider_type)
    display_name = (organization_name or "").strip() if ptype == ProviderType.SOCIETY else user.full_name.strip()
    provider = Provider(
        user_id=user.id,
        provider_type=ptype,
        display_name=display_name or user.full_name.strip(),
        contact_phone=user.phone,
    )
    db.add(provider)
    await db.flush()
    if ptype == ProviderType.SOCIETY:
        db.add(Society(provider_id=provider.id, name=display_name, contact_email=user.email))
    if user.role == UserRole.RENTER:
        user.role = UserRole.PROVIDER
    await db.flush()
    await db.refresh(provider)
    return provider


async def get_by_user(db: AsyncSession, user_id: uuid.UUID) -> Provider | None:
    return await db.scalar(
        select(Provider).where(Provider.user_id == user_id).options(selectinload(Provider.society))
    )


async def require_provider(db: AsyncSession, user: User) -> Provider:
    """The provider profile of the current user, refusing suspended providers."""
    provider = await get_by_user(db, user.id)
    if provider is None:
        raise Forbidden("You do not have a provider profile", code="NO_PROVIDER_PROFILE")
    if provider.status != ProviderStatus.ACTIVE:
        raise Forbidden("Your provider account is suspended", code="PROVIDER_SUSPENDED")
    return provider


async def require_society(db: AsyncSession, provider: Provider) -> Society:
    if provider.provider_type != ProviderType.SOCIETY:
        raise Forbidden("This account is not a society provider", code="NOT_A_SOCIETY")
    society = await db.scalar(select(Society).where(Society.provider_id == provider.id))
    if society is None:
        raise NotFound("Society profile not found")
    return society


async def get_by_id(db: AsyncSession, provider_id: uuid.UUID) -> Provider:
    provider = await db.scalar(
        select(Provider).where(Provider.id == provider_id).options(selectinload(Provider.society))
    )
    if provider is None:
        raise NotFound("Provider not found")
    return provider


async def submit_verification(db: AsyncSession, provider: Provider, data: VerificationSubmit) -> Provider:
    if provider.verification_status == VerificationStatus.VERIFIED:
        raise Conflict("This provider is already verified", code="ALREADY_VERIFIED")
    provider.contact_phone = data.contact_phone
    provider.address = data.address
    provider.authority_declared_at = utcnow()
    provider.verification_status = VerificationStatus.PENDING_VERIFICATION
    provider.verification_notes = None
    await db.flush()
    return provider


async def active_agreement(db: AsyncSession, society_id: uuid.UUID, on: date | None = None) -> SocietyAgreement | None:
    """The society's agreement in force on `on` (today by default). Its revenue
    share overrides the platform's default commission for that society's spaces."""
    when = on or utcnow().date()
    return await db.scalar(
        select(SocietyAgreement)
        .where(
            SocietyAgreement.society_id == society_id,
            SocietyAgreement.status == AgreementStatus.ACTIVE,
            SocietyAgreement.start_date <= when,
            (SocietyAgreement.end_date.is_(None)) | (SocietyAgreement.end_date >= when),
        )
        .order_by(SocietyAgreement.start_date.desc())
    )

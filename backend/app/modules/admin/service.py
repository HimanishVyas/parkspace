"""Admin marketplace operations.

Every state-changing action here writes an audit entry (PRD rule 15) — the
admin surface is the one place where a single account can change other people's
money and listings, so it needs a trail.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.time import utcnow
from app.modules.audit.service import record
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.parking.models import ListingStatus, ParkingSpace
from app.modules.payments.models import Payout, PayoutBooking, PayoutStatus
from app.modules.providers.dashboard import EARNED_STATUSES, month_bounds
from app.modules.providers.models import Provider, ProviderStatus, VerificationStatus
from app.modules.reports.models import Report, ReportStatus
from app.modules.users.models import User, UserRole, UserStatus

# Bookings whose money is real: what the platform actually earned.
REVENUE_STATUSES = (BookingStatus.CONFIRMED, BookingStatus.ACTIVE, BookingStatus.COMPLETED)


async def dashboard(db: AsyncSession) -> dict:
    now = utcnow()
    month_start, month_end = month_bounds(now)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async def count(model, *conditions) -> int:
        return int(await db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)

    async def money(column, *conditions) -> Decimal:
        value = await db.scalar(select(func.coalesce(func.sum(column), 0)).where(*conditions))
        return Decimal(value or 0).quantize(Decimal("0.01"))

    revenue_filter = Booking.status.in_(REVENUE_STATUSES)
    month_filter = (Booking.start_at >= month_start, Booking.start_at < month_end)

    return {
        "total_users": await count(User),
        "total_renters": await count(User, User.role == UserRole.RENTER),
        "total_providers": await count(Provider),
        "verified_providers": await count(
            Provider, Provider.verification_status == VerificationStatus.VERIFIED
        ),
        "total_listings": await count(ParkingSpace),
        "active_listings": await count(ParkingSpace, ParkingSpace.status == ListingStatus.PUBLISHED),
        "pending_listings": await count(
            ParkingSpace, ParkingSpace.status == ListingStatus.PENDING_APPROVAL
        ),
        "total_bookings": await count(Booking),
        "todays_bookings": await count(Booking, Booking.created_at >= today_start),
        "active_bookings": await count(Booking, Booking.status == BookingStatus.ACTIVE),
        "monthly_booking_value": await money(Booking.total_amount, revenue_filter, *month_filter),
        "monthly_platform_revenue": await money(
            Booking.commission_amount + Booking.platform_fee, revenue_filter, *month_filter
        ),
        "lifetime_booking_value": await money(Booking.total_amount, revenue_filter),
        "lifetime_platform_revenue": await money(
            Booking.commission_amount + Booking.platform_fee, revenue_filter
        ),
        "open_reports": await count(
            Report, Report.status.in_([ReportStatus.OPEN, ReportStatus.UNDER_REVIEW])
        ),
    }


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
async def list_users(
    db: AsyncSession,
    *,
    q: str | None = None,
    role: UserRole | None = None,
    status: UserStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[User], int]:
    conditions = []
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(User.email.ilike(pattern), User.full_name.ilike(pattern), User.phone.ilike(pattern))
        )
    if role is not None:
        conditions.append(User.role == role)
    if status is not None:
        conditions.append(User.status == status)
    total = int(await db.scalar(select(func.count()).select_from(User).where(*conditions)) or 0)
    rows = await db.scalars(
        select(User).where(*conditions).order_by(User.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.all()), total


async def set_user_status(
    db: AsyncSession, admin: User, user_id: uuid.UUID, status: UserStatus, reason: str | None, ip: str | None
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFound("User not found")
    if user.id == admin.id:
        raise Conflict("You cannot change your own account status", code="SELF_ACTION")
    user.status = status
    if status == UserStatus.SUSPENDED:
        # Suspension must take effect immediately, not when the token expires.
        user.token_version += 1
    await record(
        db,
        actor_id=admin.id,
        action="user.status",
        entity_type="user",
        entity_id=user.id,
        data={"status": status.value, "reason": reason},
        ip_address=ip,
    )
    await db.flush()
    return user


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #
async def list_providers(
    db: AsyncSession,
    *,
    q: str | None = None,
    verification: VerificationStatus | None = None,
    status: ProviderStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[tuple[Provider, int, Decimal]], int]:
    conditions = []
    if q:
        conditions.append(Provider.display_name.ilike(f"%{q.strip()}%"))
    if verification is not None:
        conditions.append(Provider.verification_status == verification)
    if status is not None:
        conditions.append(Provider.status == status)

    total = int(await db.scalar(select(func.count()).select_from(Provider).where(*conditions)) or 0)
    listing_count = (
        select(func.count())
        .select_from(ParkingSpace)
        .where(ParkingSpace.provider_id == Provider.id)
        .scalar_subquery()
    )
    earnings = (
        select(func.coalesce(func.sum(Booking.provider_earning), 0))
        .where(Booking.provider_id == Provider.id, Booking.status.in_(EARNED_STATUSES))
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(Provider, listing_count, earnings)
            .where(*conditions)
            .order_by(Provider.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [(row[0], int(row[1] or 0), Decimal(row[2] or 0).quantize(Decimal("0.01"))) for row in rows], total


async def decide_verification(
    db: AsyncSession,
    admin: User,
    provider_id: uuid.UUID,
    status: VerificationStatus,
    notes: str | None,
    ip: str | None,
) -> Provider:
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise NotFound("Provider not found")
    provider.verification_status = status
    provider.verification_notes = notes
    await record(
        db,
        actor_id=admin.id,
        action="provider.verification",
        entity_type="provider",
        entity_id=provider.id,
        data={"status": status.value, "notes": notes},
        ip_address=ip,
    )
    await db.flush()
    return provider


async def set_provider_status(
    db: AsyncSession,
    admin: User,
    provider_id: uuid.UUID,
    status: ProviderStatus,
    reason: str | None,
    ip: str | None,
) -> Provider:
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise NotFound("Provider not found")
    provider.status = status
    if status == ProviderStatus.SUSPENDED:
        # Suspending a provider takes their listings out of search immediately.
        await db.execute(
            ParkingSpace.__table__.update()
            .where(
                ParkingSpace.provider_id == provider.id,
                ParkingSpace.status == ListingStatus.PUBLISHED,
            )
            .values(status=ListingStatus.SUSPENDED)
        )
    await record(
        db,
        actor_id=admin.id,
        action="provider.status",
        entity_type="provider",
        entity_id=provider.id,
        data={"status": status.value, "reason": reason},
        ip_address=ip,
    )
    await db.flush()
    return provider


# --------------------------------------------------------------------------- #
# Listings
# --------------------------------------------------------------------------- #
async def list_listings(
    db: AsyncSession,
    *,
    q: str | None = None,
    status: ListingStatus | None = None,
    city: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[tuple[ParkingSpace, str]], int]:
    conditions = []
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(or_(ParkingSpace.title.ilike(pattern), ParkingSpace.address_line.ilike(pattern)))
    if status is not None:
        conditions.append(ParkingSpace.status == status)
    if city:
        conditions.append(ParkingSpace.city.ilike(f"%{city.strip()}%"))
    total = int(await db.scalar(select(func.count()).select_from(ParkingSpace).where(*conditions)) or 0)
    rows = (
        await db.execute(
            select(ParkingSpace, Provider.display_name)
            .join(Provider, Provider.id == ParkingSpace.provider_id)
            .where(*conditions)
            .order_by(ParkingSpace.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [(row[0], row[1]) for row in rows], total


async def decide_listing(
    db: AsyncSession,
    admin: User,
    space_id: uuid.UUID,
    status: ListingStatus,
    reason: str | None,
    ip: str | None,
) -> ParkingSpace:
    space = await db.get(ParkingSpace, space_id)
    if space is None:
        raise NotFound("Parking space not found")
    space.status = status
    space.rejection_reason = reason if status == ListingStatus.REJECTED else None
    await record(
        db,
        actor_id=admin.id,
        action="listing.status",
        entity_type="parking_space",
        entity_id=space.id,
        data={"status": status.value, "reason": reason},
        ip_address=ip,
    )
    await db.flush()
    return space


# --------------------------------------------------------------------------- #
# Bookings
# --------------------------------------------------------------------------- #
async def list_bookings(
    db: AsyncSession,
    *,
    q: str | None = None,
    status: BookingStatus | None = None,
    provider_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[tuple[Booking, str, str, str]], int]:
    conditions = []
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(Booking.reference.ilike(pattern), Booking.vehicle_number.ilike(pattern.upper()))
        )
    if status is not None:
        conditions.append(Booking.status == status)
    if provider_id is not None:
        conditions.append(Booking.provider_id == provider_id)
    if date_from is not None:
        conditions.append(Booking.start_at >= date_from)
    if date_to is not None:
        conditions.append(Booking.start_at < date_to)

    total = int(await db.scalar(select(func.count()).select_from(Booking).where(*conditions)) or 0)
    rows = (
        await db.execute(
            select(Booking, User.full_name, Provider.display_name, ParkingSpace.title)
            .join(User, User.id == Booking.renter_id)
            .join(Provider, Provider.id == Booking.provider_id)
            .join(ParkingSpace, ParkingSpace.id == Booking.parking_space_id)
            .where(*conditions)
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [(row[0], row[1], row[2], row[3]) for row in rows], total


# --------------------------------------------------------------------------- #
# Payouts
# --------------------------------------------------------------------------- #
async def create_payout(
    db: AsyncSession, admin: User, provider_id: uuid.UUID, up_to: datetime | None, notes: str | None
) -> tuple[Payout, int]:
    """Bundle every unsettled completed booking for a provider into one payout."""
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise NotFound("Provider not found")
    cutoff = up_to or utcnow()

    settled = select(PayoutBooking.booking_id).scalar_subquery()
    rows = await db.scalars(
        select(Booking).where(
            Booking.provider_id == provider_id,
            Booking.status.in_(EARNED_STATUSES),
            Booking.end_at <= cutoff,
            Booking.id.not_in(settled),
        )
    )
    bookings = list(rows.all())
    if not bookings:
        raise ValidationFailed("No unsettled bookings for this provider", code="NOTHING_TO_PAY")

    amount = sum((Decimal(b.provider_earning) for b in bookings), start=Decimal("0.00"))
    payout = Payout(
        provider_id=provider_id,
        amount=amount.quantize(Decimal("0.01")),
        status=PayoutStatus.PENDING,
        period_start=min(b.start_at for b in bookings),
        period_end=max(b.end_at for b in bookings),
        notes=notes,
    )
    db.add(payout)
    await db.flush()
    for booking in bookings:
        db.add(PayoutBooking(payout_id=payout.id, booking_id=booking.id))
    await record(
        db,
        actor_id=admin.id,
        action="payout.create",
        entity_type="payout",
        entity_id=payout.id,
        data={"provider_id": str(provider_id), "amount": str(payout.amount), "bookings": len(bookings)},
    )
    await db.flush()
    return payout, len(bookings)


async def mark_payout_paid(
    db: AsyncSession, admin: User, payout_id: uuid.UUID, reference: str | None
) -> Payout:
    payout = await db.get(Payout, payout_id)
    if payout is None:
        raise NotFound("Payout not found")
    if payout.status == PayoutStatus.PAID:
        raise Conflict("This payout is already marked paid", code="ALREADY_PAID")
    payout.status = PayoutStatus.PAID
    payout.paid_at = utcnow()
    payout.reference = reference
    await record(
        db,
        actor_id=admin.id,
        action="payout.paid",
        entity_type="payout",
        entity_id=payout.id,
        data={"reference": reference, "amount": str(payout.amount)},
    )
    await db.flush()
    return payout


async def list_payouts(
    db: AsyncSession,
    *,
    provider_id: uuid.UUID | None = None,
    status: PayoutStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[tuple[Payout, int]], int]:
    conditions = []
    if provider_id is not None:
        conditions.append(Payout.provider_id == provider_id)
    if status is not None:
        conditions.append(Payout.status == status)
    total = int(await db.scalar(select(func.count()).select_from(Payout).where(*conditions)) or 0)
    booking_count = (
        select(func.count())
        .select_from(PayoutBooking)
        .where(PayoutBooking.payout_id == Payout.id)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(Payout, booking_count)
            .where(*conditions)
            .order_by(Payout.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [(row[0], int(row[1] or 0)) for row in rows], total

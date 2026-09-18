import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Query, Request, status
from sqlalchemy import select

from app.core.deps import DB, AdminUser, client_ip
from app.core.errors import NotFound
from app.modules.admin import service
from app.modules.admin.schemas import (
    AdminBookingList,
    AdminBookingOut,
    AdminDashboardOut,
    AdminListingList,
    AdminListingOut,
    AdminProviderList,
    AdminProviderOut,
    AdminUserList,
    AdminUserOut,
    AuditLogOut,
    ListingDecision,
    PayoutCreate,
    PayoutMarkPaid,
    PayoutOut,
    ProviderStatusChange,
    UserStatusChange,
)
from app.modules.audit.models import AuditLog
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.parking.models import ListingStatus
from app.modules.payments.models import PayoutStatus
from app.modules.providers.models import ProviderStatus, VerificationStatus
from app.modules.providers.schemas import (
    AgreementCreate,
    AgreementOut,
    AgreementUpdate,
    VerificationDecision,
)
from app.modules.reports.models import IssueType, ReportStatus
from app.modules.reports.schemas import ReportList, ReportOut, ReportUpdate
from app.modules.settings.schemas import PlatformConfig, PlatformConfigUpdate
from app.modules.users.models import UserRole, UserStatus

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard", response_model=AdminDashboardOut)
async def admin_dashboard(admin: AdminUser, db: DB):
    return await service.dashboard(db)


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
@router.get("/users", response_model=AdminUserList)
async def list_users(
    admin: AdminUser,
    db: DB,
    q: str | None = None,
    role: UserRole | None = None,
    user_status: UserStatus | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    items, total = await service.list_users(
        db, q=q, role=role, status=user_status, limit=limit, offset=offset
    )
    return AdminUserList(items=items, total=total, limit=limit, offset=offset)


@router.post("/users/{user_id}/status", response_model=AdminUserOut)
async def set_user_status(
    user_id: uuid.UUID, data: UserStatusChange, admin: AdminUser, db: DB, request: Request
):
    """Suspend or reactivate an account. Suspension invalidates live sessions."""
    user = await service.set_user_status(db, admin, user_id, data.status, data.reason, client_ip(request))
    await db.commit()
    await db.refresh(user)
    return user


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #
@router.get("/providers", response_model=AdminProviderList)
async def list_providers(
    admin: AdminUser,
    db: DB,
    q: str | None = None,
    verification: VerificationStatus | None = None,
    provider_status: ProviderStatus | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await service.list_providers(
        db, q=q, verification=verification, status=provider_status, limit=limit, offset=offset
    )
    items = []
    for provider, listing_count, earnings in rows:
        item = AdminProviderOut.model_validate(provider)
        item.listing_count = listing_count
        item.total_earnings = earnings
        items.append(item)
    return AdminProviderList(items=items, total=total, limit=limit, offset=offset)


@router.post("/providers/{provider_id}/verification", response_model=AdminProviderOut)
async def decide_verification(
    provider_id: uuid.UUID,
    data: VerificationDecision,
    admin: AdminUser,
    db: DB,
    request: Request,
    background: BackgroundTasks,
):
    provider = await service.decide_verification(
        db, admin, provider_id, VerificationStatus(data.status), data.notes, client_ip(request)
    )
    from app.modules.notifications.service import notify
    from app.modules.users.models import User

    owner = await db.get(User, provider.user_id)
    if owner is not None:
        outcome = "approved" if data.status == "VERIFIED" else data.status.lower().replace("_", " ")
        await notify(
            db,
            background,
            owner,
            "PROVIDER_VERIFICATION",
            f"Your provider account was {outcome}",
            f"Verification status: {data.status}." + (f" Note: {data.notes}" if data.notes else ""),
            {"provider_id": str(provider.id)},
        )
    await db.commit()
    await db.refresh(provider)
    return provider


@router.post("/providers/{provider_id}/status", response_model=AdminProviderOut)
async def set_provider_status(
    provider_id: uuid.UUID, data: ProviderStatusChange, admin: AdminUser, db: DB, request: Request
):
    """Suspending a provider also takes their published listings out of search."""
    provider = await service.set_provider_status(
        db, admin, provider_id, data.status, data.reason, client_ip(request)
    )
    await db.commit()
    await db.refresh(provider)
    return provider


# --------------------------------------------------------------------------- #
# Listings
# --------------------------------------------------------------------------- #
@router.get("/listings", response_model=AdminListingList)
async def list_listings(
    admin: AdminUser,
    db: DB,
    q: str | None = None,
    listing_status: ListingStatus | None = None,
    city: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await service.list_listings(
        db, q=q, status=listing_status, city=city, limit=limit, offset=offset
    )
    items = []
    for space, provider_name in rows:
        item = AdminListingOut.model_validate(space)
        item.provider_name = provider_name
        items.append(item)
    return AdminListingList(items=items, total=total, limit=limit, offset=offset)


@router.post("/listings/{space_id}/approve", response_model=AdminListingOut)
async def approve_listing(space_id: uuid.UUID, admin: AdminUser, db: DB, request: Request):
    space = await service.decide_listing(
        db, admin, space_id, ListingStatus.PUBLISHED, None, client_ip(request)
    )
    await db.commit()
    await db.refresh(space)
    return space


@router.post("/listings/{space_id}/reject", response_model=AdminListingOut)
async def reject_listing(
    space_id: uuid.UUID, data: ListingDecision, admin: AdminUser, db: DB, request: Request
):
    space = await service.decide_listing(
        db, admin, space_id, ListingStatus.REJECTED, data.reason, client_ip(request)
    )
    await db.commit()
    await db.refresh(space)
    return space


@router.post("/listings/{space_id}/suspend", response_model=AdminListingOut)
async def suspend_listing(
    space_id: uuid.UUID, data: ListingDecision, admin: AdminUser, db: DB, request: Request
):
    space = await service.decide_listing(
        db, admin, space_id, ListingStatus.SUSPENDED, data.reason, client_ip(request)
    )
    await db.commit()
    await db.refresh(space)
    return space


# --------------------------------------------------------------------------- #
# Bookings
# --------------------------------------------------------------------------- #
@router.get("/bookings", response_model=AdminBookingList)
async def list_bookings(
    admin: AdminUser,
    db: DB,
    q: str | None = None,
    booking_status: BookingStatus | None = None,
    provider_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await service.list_bookings(
        db,
        q=q,
        status=booking_status,
        provider_id=provider_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    items = []
    for booking, renter_name, provider_name, parking_title in rows:
        item = AdminBookingOut.model_validate(booking)
        item.renter_name = renter_name
        item.provider_name = provider_name
        item.parking_title = parking_title
        items.append(item)
    return AdminBookingList(items=items, total=total, limit=limit, offset=offset)


@router.post("/bookings/{booking_id}/cancel", response_model=AdminBookingOut)
async def admin_cancel_booking(
    booking_id: uuid.UUID,
    data: ListingDecision,
    admin: AdminUser,
    db: DB,
    request: Request,
    background: BackgroundTasks,
):
    """Cancel on a user's behalf. An admin cancellation always refunds in full."""
    from app.modules.audit.service import record
    from app.modules.bookings import notifications, service as booking_service
    from app.modules.payments.service import refund_booking
    from app.modules.settings.service import get_config

    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise NotFound("Booking not found")
    config = await get_config(db)
    booking, refund_due = await booking_service.cancel(db, booking, admin, config, data.reason)
    await refund_booking(db, booking, refund_due, data.reason or "Cancelled by support")
    await notifications.booking_cancelled(db, background, booking, by_renter=False)
    await record(
        db,
        actor_id=admin.id,
        action="booking.admin_cancel",
        entity_type="booking",
        entity_id=booking.id,
        data={"reference": booking.reference, "refund": str(refund_due), "reason": data.reason},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(booking)
    return AdminBookingOut.model_validate(booking)


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
@router.get("/reports", response_model=ReportList)
async def list_reports(
    admin: AdminUser,
    db: DB,
    report_status: ReportStatus | None = None,
    issue_type: IssueType | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    from app.modules.reports import service as report_service

    items, total = await report_service.list_for_admin(
        db, status=report_status, issue_type=issue_type, limit=limit, offset=offset
    )
    return ReportList(items=items, total=total, limit=limit, offset=offset)


@router.patch("/reports/{report_id}", response_model=ReportOut)
async def update_report(
    report_id: uuid.UUID,
    data: ReportUpdate,
    admin: AdminUser,
    db: DB,
    request: Request,
    background: BackgroundTasks,
):
    from app.modules.audit.service import record
    from app.modules.notifications.service import notify
    from app.modules.reports import service as report_service
    from app.modules.users.models import User

    report = await report_service.get_for_user(db, report_id, admin)
    await report_service.resolve(db, report, admin, data.status, data.admin_notes)
    reporter = await db.get(User, report.reporter_id)
    if reporter is not None:
        await notify(
            db,
            background,
            reporter,
            "REPORT_UPDATED",
            f"Your report is {data.status.value.lower().replace('_', ' ')}",
            data.admin_notes or "Our team has updated the status of your report.",
            {"report_id": str(report.id)},
        )
    await record(
        db,
        actor_id=admin.id,
        action="report.update",
        entity_type="report",
        entity_id=report.id,
        data={"status": data.status.value},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(report)
    return report


# --------------------------------------------------------------------------- #
# Society agreements
# --------------------------------------------------------------------------- #
@router.get("/societies/{society_id}/agreements", response_model=list[AgreementOut])
async def list_agreements(society_id: uuid.UUID, admin: AdminUser, db: DB):
    from app.modules.providers.models import SocietyAgreement

    rows = await db.scalars(
        select(SocietyAgreement)
        .where(SocietyAgreement.society_id == society_id)
        .order_by(SocietyAgreement.start_date.desc())
    )
    return list(rows.all())


@router.post(
    "/societies/{society_id}/agreements",
    response_model=AgreementOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_agreement(
    society_id: uuid.UUID, data: AgreementCreate, admin: AdminUser, db: DB, request: Request
):
    """Record a society's commercial terms (PRD §30). The legal document itself
    lives outside this system."""
    from app.modules.audit.service import record
    from app.modules.providers.models import Society, SocietyAgreement

    society = await db.get(Society, society_id)
    if society is None:
        raise NotFound("Society not found")
    agreement = SocietyAgreement(society_id=society_id, **data.model_dump())
    db.add(agreement)
    await db.flush()
    await record(
        db,
        actor_id=admin.id,
        action="agreement.create",
        entity_type="society_agreement",
        entity_id=agreement.id,
        data={"society_id": str(society_id), "revenue_share": str(data.revenue_share_percent)},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(agreement)
    return agreement


@router.patch("/agreements/{agreement_id}", response_model=AgreementOut)
async def update_agreement(
    agreement_id: uuid.UUID, data: AgreementUpdate, admin: AdminUser, db: DB, request: Request
):
    from app.modules.audit.service import record
    from app.modules.providers.models import SocietyAgreement

    agreement = await db.get(SocietyAgreement, agreement_id)
    if agreement is None:
        raise NotFound("Agreement not found")
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changes.items():
        setattr(agreement, key, value)
    await record(
        db,
        actor_id=admin.id,
        action="agreement.update",
        entity_type="society_agreement",
        entity_id=agreement.id,
        data={key: str(value) for key, value in changes.items()},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(agreement)
    return agreement


# --------------------------------------------------------------------------- #
# Payouts
# --------------------------------------------------------------------------- #
@router.get("/payouts", response_model=list[PayoutOut])
async def list_payouts(
    admin: AdminUser,
    db: DB,
    provider_id: uuid.UUID | None = None,
    payout_status: PayoutStatus | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    rows, _ = await service.list_payouts(
        db, provider_id=provider_id, status=payout_status, limit=limit, offset=offset
    )
    items = []
    for payout, booking_count in rows:
        item = PayoutOut.model_validate(payout)
        item.booking_count = booking_count
        items.append(item)
    return items


@router.post("/payouts", response_model=PayoutOut, status_code=status.HTTP_201_CREATED)
async def create_payout(data: PayoutCreate, admin: AdminUser, db: DB):
    payout, booking_count = await service.create_payout(
        db, admin, data.provider_id, data.up_to, data.notes
    )
    await db.commit()
    await db.refresh(payout)
    item = PayoutOut.model_validate(payout)
    item.booking_count = booking_count
    return item


@router.post("/payouts/{payout_id}/paid", response_model=PayoutOut)
async def mark_payout_paid(payout_id: uuid.UUID, data: PayoutMarkPaid, admin: AdminUser, db: DB):
    payout = await service.mark_payout_paid(db, admin, payout_id, data.reference)
    await db.commit()
    await db.refresh(payout)
    return payout


# --------------------------------------------------------------------------- #
# Platform settings & audit trail
# --------------------------------------------------------------------------- #
@router.get("/settings", response_model=PlatformConfig)
async def get_settings(admin: AdminUser, db: DB):
    """The business rules — fees, commission, cancellation policy, booking limits."""
    from app.modules.settings.service import get_config

    return await get_config(db)


@router.patch("/settings", response_model=PlatformConfig)
async def update_settings(
    data: PlatformConfigUpdate, admin: AdminUser, db: DB, request: Request
):
    from app.modules.audit.service import record
    from app.modules.settings.service import update_config

    config = await update_config(db, data, admin.id)
    await record(
        db,
        actor_id=admin.id,
        action="settings.update",
        entity_type="platform_settings",
        data=data.model_dump(exclude_unset=True, exclude_none=True, mode="json"),
        ip_address=client_ip(request),
    )
    await db.commit()
    return config


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    admin: AdminUser,
    db: DB,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if entity_id:
        conditions.append(AuditLog.entity_id == entity_id)
    rows = await db.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.all())

"""Issue reporting (PRD §24).

V1 records and routes issues to an admin. It makes no compensation promise: the
platform is not an insurer, and liability follows the terms and the agreement
between the parties.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import Conflict, Forbidden, NotFound
from app.core.time import utcnow
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.providers.models import Provider
from app.modules.reports.models import IssueType, Report, ReportPhoto, ReportStatus
from app.modules.reports.schemas import ReportCreate
from app.modules.users.models import User

MAX_PHOTOS_PER_REPORT = 6
# Issue types serious enough to flag the booking itself for admin attention.
_DISPUTE_TYPES = (IssueType.PROPERTY_DAMAGE, IssueType.SPACE_UNAVAILABLE, IssueType.SPACE_OCCUPIED)


async def create(db: AsyncSession, reporter: User, data: ReportCreate) -> Report:
    booking = await db.get(Booking, data.booking_id)
    if booking is None:
        raise NotFound("Booking not found")

    provider = await db.get(Provider, booking.provider_id)
    is_party = booking.renter_id == reporter.id or (provider is not None and provider.user_id == reporter.id)
    if not is_party and not reporter.is_admin:
        raise Forbidden("You were not part of this booking")

    open_report = await db.scalar(
        select(Report.id).where(
            Report.booking_id == booking.id,
            Report.reporter_id == reporter.id,
            Report.status.in_([ReportStatus.OPEN, ReportStatus.UNDER_REVIEW]),
        )
    )
    if open_report:
        raise Conflict("You already have an open report for this booking", code="REPORT_OPEN")

    report = Report(
        booking_id=booking.id,
        reporter_id=reporter.id,
        issue_type=data.issue_type,
        description=data.description.strip(),
        photos=[],
    )
    db.add(report)
    # A serious complaint marks the booking disputed, which keeps it out of
    # payouts until an admin has looked at it.
    if data.issue_type in _DISPUTE_TYPES and booking.status in (
        BookingStatus.CONFIRMED,
        BookingStatus.ACTIVE,
        BookingStatus.COMPLETED,
    ):
        booking.status = BookingStatus.DISPUTED
    await db.flush()
    return report


async def add_photo(db: AsyncSession, report: Report, storage_key: str, url: str) -> ReportPhoto:
    if len(report.photos) >= MAX_PHOTOS_PER_REPORT:
        raise Conflict(f"At most {MAX_PHOTOS_PER_REPORT} photos per report", code="TOO_MANY_PHOTOS")
    photo = ReportPhoto(report_id=report.id, storage_key=storage_key, url=url)
    db.add(photo)
    await db.flush()
    return photo


async def get_for_user(db: AsyncSession, report_id: uuid.UUID, user: User) -> Report:
    report = await db.scalar(
        select(Report).where(Report.id == report_id).options(selectinload(Report.photos))
    )
    if report is None:
        raise NotFound("Report not found")
    if report.reporter_id == user.id or user.is_admin:
        return report
    booking = await db.get(Booking, report.booking_id)
    provider = await db.get(Provider, booking.provider_id) if booking else None
    if provider is not None and provider.user_id == user.id:
        return report
    raise NotFound("Report not found")


async def list_for_user(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 20, offset: int = 0
) -> tuple[list[Report], int]:
    conditions = [Report.reporter_id == user_id]
    total = await db.scalar(select(func.count()).select_from(Report).where(*conditions)) or 0
    rows = await db.scalars(
        select(Report)
        .where(*conditions)
        .options(selectinload(Report.photos))
        .order_by(Report.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.all()), int(total)


async def list_for_admin(
    db: AsyncSession,
    *,
    status: ReportStatus | None = None,
    issue_type: IssueType | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Report], int]:
    conditions = []
    if status is not None:
        conditions.append(Report.status == status)
    if issue_type is not None:
        conditions.append(Report.issue_type == issue_type)
    total = await db.scalar(select(func.count()).select_from(Report).where(*conditions)) or 0
    rows = await db.scalars(
        select(Report)
        .where(*conditions)
        .options(selectinload(Report.photos))
        .order_by(Report.status, Report.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.all()), int(total)


async def resolve(
    db: AsyncSession, report: Report, admin: User, status: ReportStatus, notes: str | None
) -> Report:
    report.status = status
    report.admin_notes = notes
    if status in (ReportStatus.RESOLVED, ReportStatus.DISMISSED):
        report.resolved_by_id = admin.id
        report.resolved_at = utcnow()
        booking = await db.get(Booking, report.booking_id)
        # Lift the dispute flag once nothing is left open on the booking.
        if booking is not None and booking.status == BookingStatus.DISPUTED:
            still_open = await db.scalar(
                select(Report.id).where(
                    Report.booking_id == booking.id,
                    Report.id != report.id,
                    Report.status.in_([ReportStatus.OPEN, ReportStatus.UNDER_REVIEW]),
                )
            )
            if not still_open:
                booking.status = (
                    BookingStatus.COMPLETED if booking.end_at <= utcnow() else BookingStatus.CONFIRMED
                )
    await db.flush()
    return report

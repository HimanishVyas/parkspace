import uuid

from fastapi import APIRouter, Query, UploadFile, status

from app.core.deps import DB, CurrentUser
from app.modules.reports import service
from app.modules.reports.schemas import ReportCreate, ReportList, ReportOut, ReportPhotoOut

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def create_report(data: ReportCreate, user: CurrentUser, db: DB):
    """Raise an issue against a booking. Either party may report."""
    report = await service.create(db, user, data)
    await db.commit()
    await db.refresh(report)
    return report


@router.get("", response_model=ReportList)
async def list_my_reports(
    user: CurrentUser,
    db: DB,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
):
    items, total = await service.list_for_user(db, user.id, limit, offset)
    return ReportList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: uuid.UUID, user: CurrentUser, db: DB):
    return await service.get_for_user(db, report_id, user)


@router.post("/{report_id}/photos", response_model=ReportPhotoOut, status_code=status.HTTP_201_CREATED)
async def upload_report_photo(report_id: uuid.UUID, file: UploadFile, user: CurrentUser, db: DB):
    """Attach photo evidence to a report (PRD §25)."""
    from app.modules.storage.service import get_storage, read_validated_image

    report = await service.get_for_user(db, report_id, user)
    if report.reporter_id != user.id and not user.is_admin:
        from app.core.errors import Forbidden

        raise Forbidden("Only the reporter can add photos")
    content, ext = await read_validated_image(file)
    stored = await get_storage().save(content, folder="reports", extension=ext)
    photo = await service.add_photo(db, report, stored.key, stored.url)
    await db.commit()
    await db.refresh(photo)
    return photo

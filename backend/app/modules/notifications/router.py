import uuid

from fastapi import APIRouter, Query, status

from app.core.deps import DB, CurrentUser
from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationList, NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationList)
async def list_notifications(
    user: CurrentUser,
    db: DB,
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    items, total, unread = await service.list_for_user(
        db, user.id, unread_only=unread_only, limit=limit, offset=offset
    )
    return NotificationList(items=items, total=total, unread=unread)


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(notification_id: uuid.UUID, user: CurrentUser, db: DB):
    notification = await service.mark_read(db, user.id, notification_id)
    await db.commit()
    await db.refresh(notification)
    return notification


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(user: CurrentUser, db: DB):
    await service.mark_all_read(db, user.id)
    await db.commit()

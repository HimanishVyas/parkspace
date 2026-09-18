"""Notification fan-out: one call writes an in-app record and queues an email."""
import logging
import uuid

from fastapi import BackgroundTasks
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.core.errors import NotFound
from app.core.time import utcnow
from app.modules.notifications.email import send_email
from app.modules.notifications.models import Notification
from app.modules.users.models import User

logger = logging.getLogger(__name__)


async def notify(
    db: AsyncSession,
    background: BackgroundTasks | None,
    user: User,
    event: str,
    title: str,
    body: str,
    data: dict | None = None,
    *,
    email: bool = True,
) -> Notification:
    """Queue a notification for `user`.

    The in-app row joins the caller's transaction (so it is rolled back with it);
    the email is sent after the response, and only if the transaction committed.
    """
    notification = Notification(user_id=user.id, event=event, title=title, body=body, data=data)
    db.add(notification)
    await db.flush()
    if email and background is not None:
        background.add_task(deliver_email, notification.id, user.email, title, body)
    return notification


async def deliver_email(notification_id: uuid.UUID, to: str, subject: str, body: str) -> None:
    """Background task: confirm the notification survived the commit, then send."""
    async with SessionLocal() as session:
        exists = await session.scalar(select(Notification.id).where(Notification.id == notification_id))
        if exists is None:
            return
        await send_email(to, subject, body)
        await session.execute(
            update(Notification).where(Notification.id == notification_id).values(emailed_at=utcnow())
        )
        await session.commit()


async def list_for_user(
    db: AsyncSession, user_id: uuid.UUID, *, unread_only: bool = False, limit: int = 50, offset: int = 0
) -> tuple[list[Notification], int, int]:
    conditions = [Notification.user_id == user_id]
    if unread_only:
        conditions.append(Notification.read_at.is_(None))
    total = await db.scalar(select(func.count()).select_from(Notification).where(*conditions)) or 0
    unread = (
        await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        or 0
    )
    rows = (
        await db.scalars(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return list(rows), total, unread


async def mark_read(db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        raise NotFound("Notification not found")
    if notification.read_at is None:
        notification.read_at = utcnow()
    return notification


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    return result.rowcount or 0

"""Write operations on a space's availability rules and blocks."""
import uuid
from datetime import datetime

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.modules.availability.models import AvailabilityBlock, AvailabilityRule
from app.modules.availability.schemas import BlockIn, RulesReplace
from app.modules.parking.models import ParkingSpace


async def replace_rules(db: AsyncSession, space: ParkingSpace, data: RulesReplace) -> list[AvailabilityRule]:
    await db.execute(sql_delete(AvailabilityRule).where(AvailabilityRule.parking_space_id == space.id))
    for rule in data.rules:
        db.add(AvailabilityRule(parking_space_id=space.id, **rule.model_dump()))
    await db.flush()
    rows = await db.scalars(
        select(AvailabilityRule)
        .where(AvailabilityRule.parking_space_id == space.id)
        .order_by(AvailabilityRule.day_of_week, AvailabilityRule.start_minute)
    )
    return list(rows.all())


async def create_block(db: AsyncSession, space: ParkingSpace, data: BlockIn) -> AvailabilityBlock:
    """Block a period. Existing bookings win: a provider cannot block a slot they
    have already sold — they have to cancel that booking first."""
    conflicting = await _bookings_in(db, space.id, data.start_at, data.end_at)
    if conflicting:
        raise Conflict(
            f"{conflicting} booking(s) already exist in that period. Cancel them before blocking it.",
            code="BOOKINGS_IN_PERIOD",
        )
    block = AvailabilityBlock(parking_space_id=space.id, **data.model_dump())
    db.add(block)
    await db.flush()
    return block


async def _bookings_in(db: AsyncSession, space_id: uuid.UUID, start_at: datetime, end_at: datetime) -> int:
    from sqlalchemy import func

    from app.modules.bookings.models import BLOCKING_STATUSES, Booking

    count = await db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.parking_space_id == space_id,
            Booking.status.in_(BLOCKING_STATUSES),
            Booking.start_at < end_at,
            Booking.end_at > start_at,
        )
    )
    return int(count or 0)


async def list_blocks(
    db: AsyncSession, space_id: uuid.UUID, from_at: datetime | None = None, to_at: datetime | None = None
) -> list[AvailabilityBlock]:
    conditions = [AvailabilityBlock.parking_space_id == space_id]
    if from_at is not None:
        conditions.append(AvailabilityBlock.end_at > from_at)
    if to_at is not None:
        conditions.append(AvailabilityBlock.start_at < to_at)
    rows = await db.scalars(
        select(AvailabilityBlock).where(*conditions).order_by(AvailabilityBlock.start_at)
    )
    return list(rows.all())


async def delete_block(db: AsyncSession, space: ParkingSpace, block_id: uuid.UUID) -> None:
    block = await db.get(AvailabilityBlock, block_id)
    if block is None or block.parking_space_id != space.id:
        raise NotFound("Block not found")
    await db.delete(block)
    await db.flush()

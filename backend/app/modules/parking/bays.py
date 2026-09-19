"""Named parking bays, and which of them are free for a given window.

A space has always had `total_slots` interchangeable slots, and a booking has
always occupied one of them by index. This module puts a name and a position on
each index so a renter can pick the bay by the lift instead of being assigned
whatever was lowest.

The concurrency guarantee is untouched: the authority on "is this bay free" is
still the exclusion constraint on `bookings`, and everything here is an
optimistic read used to draw the picker.
"""
import string
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.modules.parking.models import ParkingBay, ParkingSpace

# Bays are laid out in rows of this many, which reads well on a phone and keeps
# the labels short. A 12-bay space becomes A-1..A-6, B-1..B-6.
ROW_WIDTH = 6
_ROW_NAMES = string.ascii_uppercase


def default_label(slot_index: int) -> str:
    row = slot_index // ROW_WIDTH
    col = slot_index % ROW_WIDTH
    # Past Z (156 bays) fall back to a plain number rather than inventing "AA".
    prefix = _ROW_NAMES[row] if row < len(_ROW_NAMES) else str(row + 1)
    return f"{prefix}-{col + 1}"


async def list_for_space(db: AsyncSession, space_id: uuid.UUID) -> list[ParkingBay]:
    rows = await db.scalars(
        select(ParkingBay)
        .where(ParkingBay.parking_space_id == space_id)
        .order_by(ParkingBay.slot_index)
    )
    return list(rows.all())


async def sync_for_space(db: AsyncSession, space: ParkingSpace) -> list[ParkingBay]:
    """Make the bay rows match the space's `total_slots`.

    Called whenever a listing is created or its slot count changes. Existing
    bays keep their labels — a provider who renamed a bay to match the paint on
    the floor does not want that undone because they added two more.
    """
    existing = {bay.slot_index: bay for bay in await list_for_space(db, space.id)}
    total = max(space.total_slots, 1)

    for index in range(total):
        bay = existing.pop(index, None)
        if bay is None:
            db.add(
                ParkingBay(
                    parking_space_id=space.id,
                    slot_index=index,
                    label=default_label(index),
                    row_index=index // ROW_WIDTH,
                    col_index=index % ROW_WIDTH,
                )
            )

    # Anything above the new total is gone. `_assert_slot_reduction_safe` has
    # already refused the change if a live booking sits up there.
    for bay in existing.values():
        await db.delete(bay)

    await db.flush()
    return await list_for_space(db, space.id)


async def rename(db: AsyncSession, space: ParkingSpace, labels: dict[int, str]) -> list[ParkingBay]:
    """Set the provider's own labels, keyed by slot index."""
    bays = {bay.slot_index: bay for bay in await list_for_space(db, space.id)}
    unknown = sorted(set(labels) - set(bays))
    if unknown:
        raise ValidationFailed(
            "That bay does not exist on this space",
            details=[{"code": "UNKNOWN_BAY", "slot_index": i} for i in unknown],
        )
    seen: dict[str, int] = {}
    for index, label in labels.items():
        cleaned = label.strip()
        if not cleaned:
            raise ValidationFailed("A bay needs a name", details=[{"slot_index": index}])
        if cleaned.casefold() in seen:
            raise ValidationFailed(
                "Two bays cannot share a name",
                details=[{"code": "DUPLICATE_LABEL", "label": cleaned}],
            )
        seen[cleaned.casefold()] = index
        bays[index].label = cleaned
    await db.flush()
    return await list_for_space(db, space.id)


async def set_active(db: AsyncSession, space: ParkingSpace, slot_index: int, active: bool) -> ParkingBay:
    bay = await db.scalar(
        select(ParkingBay).where(
            ParkingBay.parking_space_id == space.id, ParkingBay.slot_index == slot_index
        )
    )
    if bay is None:
        raise NotFound("Bay not found")
    bay.is_active = active
    await db.flush()
    return bay


async def assert_bookable(db: AsyncSession, space: ParkingSpace, slot_index: int) -> ParkingBay:
    """The renter asked for a specific bay; check it is one they may have.

    Deliberately raises rather than falling back to another bay. Somebody who
    chose the bay by the lift will not accept being quietly moved to the far
    corner — and would only find out on arrival.
    """
    if slot_index < 0 or slot_index >= max(space.total_slots, 1):
        raise ValidationFailed(
            "That bay does not exist on this space",
            details=[{"code": "UNKNOWN_BAY", "slot_index": slot_index}],
        )
    bay = await db.scalar(
        select(ParkingBay).where(
            ParkingBay.parking_space_id == space.id, ParkingBay.slot_index == slot_index
        )
    )
    if bay is not None and not bay.is_active:
        raise Conflict("That bay is out of service", code="BAY_INACTIVE")
    return bay

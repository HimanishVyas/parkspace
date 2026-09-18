import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.modules.vehicles.models import Vehicle
from app.modules.vehicles.schemas import VehicleCreate, VehicleUpdate


async def list_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[Vehicle]:
    rows = await db.scalars(
        select(Vehicle)
        .where(Vehicle.user_id == user_id)
        .order_by(Vehicle.is_default.desc(), Vehicle.created_at.desc())
    )
    return list(rows.all())


async def get_owned(db: AsyncSession, user_id: uuid.UUID, vehicle_id: uuid.UUID) -> Vehicle:
    vehicle = await db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.user_id != user_id:
        raise NotFound("Vehicle not found")
    return vehicle


async def _clear_other_defaults(db: AsyncSession, user_id: uuid.UUID, keep_id: uuid.UUID) -> None:
    await db.execute(
        update(Vehicle)
        .where(Vehicle.user_id == user_id, Vehicle.id != keep_id, Vehicle.is_default.is_(True))
        .values(is_default=False)
    )


async def create(db: AsyncSession, user_id: uuid.UUID, data: VehicleCreate) -> Vehicle:
    duplicate = await db.scalar(
        select(Vehicle.id).where(
            Vehicle.user_id == user_id, Vehicle.registration_number == data.registration_number
        )
    )
    if duplicate:
        raise Conflict("You have already saved this vehicle", code="VEHICLE_EXISTS")
    has_any = await db.scalar(select(Vehicle.id).where(Vehicle.user_id == user_id).limit(1))
    vehicle = Vehicle(user_id=user_id, **data.model_dump())
    # The first vehicle saved becomes the default, so booking has a sensible preselection.
    if not has_any:
        vehicle.is_default = True
    db.add(vehicle)
    await db.flush()
    if vehicle.is_default:
        await _clear_other_defaults(db, user_id, vehicle.id)
    return vehicle


async def update_vehicle(
    db: AsyncSession, user_id: uuid.UUID, vehicle_id: uuid.UUID, data: VehicleUpdate
) -> Vehicle:
    vehicle = await get_owned(db, user_id, vehicle_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    registration = changes.get("registration_number")
    if registration and registration != vehicle.registration_number:
        duplicate = await db.scalar(
            select(Vehicle.id).where(
                Vehicle.user_id == user_id,
                Vehicle.registration_number == registration,
                Vehicle.id != vehicle_id,
            )
        )
        if duplicate:
            raise Conflict("You have already saved this vehicle", code="VEHICLE_EXISTS")
    for key, value in changes.items():
        setattr(vehicle, key, value)
    await db.flush()
    if vehicle.is_default:
        await _clear_other_defaults(db, user_id, vehicle.id)
    return vehicle


async def delete(db: AsyncSession, user_id: uuid.UUID, vehicle_id: uuid.UUID) -> None:
    """Vehicles referenced by a booking are kept (the booking stores its own plate
    snapshot, but the link is useful) — deleting is allowed and nulls that link."""
    from app.modules.bookings.models import Booking

    vehicle = await get_owned(db, user_id, vehicle_id)
    await db.execute(update(Booking).where(Booking.vehicle_id == vehicle.id).values(vehicle_id=None))
    was_default = vehicle.is_default
    await db.delete(vehicle)
    await db.flush()
    if was_default:
        replacement = await db.scalar(
            select(Vehicle).where(Vehicle.user_id == user_id).order_by(Vehicle.created_at).limit(1)
        )
        if replacement:
            replacement.is_default = True

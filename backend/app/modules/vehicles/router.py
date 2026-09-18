import uuid

from fastapi import APIRouter, status

from app.core.deps import DB, CurrentUser
from app.modules.vehicles import service
from app.modules.vehicles.schemas import VehicleCreate, VehicleOut, VehicleUpdate

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("", response_model=list[VehicleOut])
async def list_vehicles(user: CurrentUser, db: DB):
    return await service.list_for_user(db, user.id)


@router.post("", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
async def create_vehicle(data: VehicleCreate, user: CurrentUser, db: DB):
    vehicle = await service.create(db, user.id, data)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


@router.get("/{vehicle_id}", response_model=VehicleOut)
async def get_vehicle(vehicle_id: uuid.UUID, user: CurrentUser, db: DB):
    return await service.get_owned(db, user.id, vehicle_id)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
async def update_vehicle(vehicle_id: uuid.UUID, data: VehicleUpdate, user: CurrentUser, db: DB):
    vehicle = await service.update_vehicle(db, user.id, vehicle_id, data)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle(vehicle_id: uuid.UUID, user: CurrentUser, db: DB):
    await service.delete(db, user.id, vehicle_id)
    await db.commit()

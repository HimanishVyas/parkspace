import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request, UploadFile, status

from app.core.deps import DB, CurrentUser, client_ip
from app.core.errors import Forbidden
from app.core.ratelimit import rate_limit
from app.modules.parking import bays
from app.modules.availability import crud as availability_crud
from app.modules.availability import service as availability_service
from app.modules.parking.schemas import BayActive, BayLayout, BayOut, BayRename
from app.modules.availability.schemas import (
    AvailabilityOut,
    BlockIn,
    BlockOut,
    CalendarDay,
    CalendarOut,
    RuleOut,
    RulesReplace,
)
from app.modules.parking import service
from app.modules.parking.models import ListingStatus, ParkingType, PricingUnit, VehicleType
from app.modules.parking.schemas import (
    GeocodeOut,
    ParkingSpaceCreate,
    ParkingSpaceOut,
    ParkingSpacePublic,
    ParkingSpaceUpdate,
    PhotoOut,
    PhotoReorder,
    SearchResponse,
    SearchResult,
)
from app.modules.providers import service as provider_service
from app.modules.settings.service import get_config

router = APIRouter(prefix="/parking", tags=["parking"])


def _to_result(hit: service.SearchHit) -> SearchResult:
    space = hit.space
    return SearchResult(
        id=space.id,
        title=space.title,
        parking_type=space.parking_type,
        vehicle_types=[VehicleType(v) for v in space.vehicle_types],
        city=space.city,
        latitude=float(space.latitude),
        longitude=float(space.longitude),
        rating_average=space.rating_average,
        rating_count=space.rating_count,
        prices=space.prices,
        photo_url=space.photos[0].url if space.photos else None,
        distance_km=hit.distance_km,
    )


# --------------------------------------------------------------------------- #
# Public search & discovery
# --------------------------------------------------------------------------- #
@router.get("", response_model=SearchResponse, dependencies=[Depends(rate_limit("search", 60, 60))])
async def search_parking(
    db: DB,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=5.0, gt=0, le=50),
    q: str | None = Query(default=None, max_length=200),
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    unit: PricingUnit | None = None,
    vehicle_type: VehicleType | None = None,
    parking_type: ParkingType | None = None,
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    sort: str = Query(default="distance", pattern="^(distance|price_asc|price_desc|rating|newest)$"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
):
    """Search published listings. Supply `start_at`/`end_at` to see only spaces
    that are actually free then — Principle 4: never show unavailable parking as
    available."""
    if start_at is not None and end_at is not None:
        # This endpoint is public, so the window it accepts is the window an
        # anonymous caller can make the server reason about. Hold it to the same
        # bound a booking gets.
        from app.modules.bookings.service import assert_window_bounded

        assert_window_bounded(start_at, end_at, await get_config(db))
    params = service.SearchParams(
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        query=q,
        start_at=start_at,
        end_at=end_at,
        unit=unit,
        vehicle_type=vehicle_type,
        parking_type=parking_type,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    hits, total = await service.search(db, params)
    return SearchResponse(
        items=[_to_result(hit) for hit in hits], total=total, limit=limit, offset=offset
    )


@router.get("/geocode", response_model=list[GeocodeOut], dependencies=[Depends(rate_limit("geocode", 30, 60))])
async def geocode_address(q: str = Query(min_length=3, max_length=200)):
    """Address lookup helper for the listing form and the search box."""
    from app.modules.parking.geocoding import geocode

    return [GeocodeOut(**vars(result)) for result in await geocode(q)]


# --------------------------------------------------------------------------- #
# Provider's own listings (declared before /{space_id} so `mine` isn't a UUID)
# --------------------------------------------------------------------------- #
@router.get("/mine", response_model=list[ParkingSpaceOut])
async def list_my_parking(user: CurrentUser, db: DB, listing_status: ListingStatus | None = None):
    provider = await provider_service.require_provider(db, user)
    return await service.list_for_provider(db, provider, listing_status)


@router.get("/mine/{space_id}", response_model=ParkingSpaceOut)
async def get_my_parking(space_id: uuid.UUID, user: CurrentUser, db: DB):
    provider = await provider_service.require_provider(db, user)
    return await service.get_owned(db, provider, space_id)


@router.post("", response_model=ParkingSpaceOut, status_code=status.HTTP_201_CREATED)
async def create_parking(data: ParkingSpaceCreate, user: CurrentUser, db: DB, request: Request):
    provider = await provider_service.require_provider(db, user)
    space = await service.create(db, provider, data)
    from app.modules.audit.service import record

    await record(
        db,
        actor_id=user.id,
        action="listing.create",
        entity_type="parking_space",
        entity_id=space.id,
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(space)
    return space


@router.patch("/{space_id}", response_model=ParkingSpaceOut)
async def update_parking(space_id: uuid.UUID, data: ParkingSpaceUpdate, user: CurrentUser, db: DB):
    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    space = await service.update(db, space, data)
    await db.commit()
    await db.refresh(space)
    return space


@router.delete("/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_parking(space_id: uuid.UUID, user: CurrentUser, db: DB):
    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    await service.delete(db, space)
    await db.commit()


@router.post("/{space_id}/publish", response_model=ParkingSpaceOut)
async def publish_parking(space_id: uuid.UUID, user: CurrentUser, db: DB):
    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    config = await get_config(db)
    await service.publish(db, space, config)
    await db.commit()
    await db.refresh(space)
    return space


@router.post("/{space_id}/pause", response_model=ParkingSpaceOut)
async def pause_parking(space_id: uuid.UUID, user: CurrentUser, db: DB):
    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    await service.pause(db, space)
    await db.commit()
    await db.refresh(space)
    return space


# --------------------------------------------------------------------------- #
# Photos
# --------------------------------------------------------------------------- #
@router.post("/{space_id}/photos", response_model=PhotoOut, status_code=status.HTTP_201_CREATED)
async def upload_photo(space_id: uuid.UUID, file: UploadFile, user: CurrentUser, db: DB):
    from app.modules.storage.service import get_storage, read_validated_image

    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    content, ext = await read_validated_image(file)
    stored = await get_storage().save(content, folder="parking", extension=ext)
    photo = await service.add_photo(db, space, stored.key, stored.url)
    await db.commit()
    await db.refresh(photo)
    return photo


@router.delete("/{space_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(space_id: uuid.UUID, photo_id: uuid.UUID, user: CurrentUser, db: DB):
    from app.modules.storage.service import get_storage

    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    storage_key = await service.delete_photo(db, space, photo_id)
    await db.commit()
    # Only unlink the file once the row is gone for good.
    await get_storage().delete(storage_key)


@router.post("/{space_id}/photos/reorder", response_model=list[PhotoOut])
async def reorder_photos(space_id: uuid.UUID, data: PhotoReorder, user: CurrentUser, db: DB):
    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    await service.reorder_photos(db, space, data.photo_ids)
    await db.commit()
    await db.refresh(space)
    return space.photos


# --------------------------------------------------------------------------- #
# Bays
# --------------------------------------------------------------------------- #
@router.get("/{space_id}/bays", response_model=BayLayout)
async def get_bays(
    space_id: uuid.UUID,
    db: DB,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
):
    """The bay layout, and which bays are taken for a window if one is given.

    This is an optimistic read used to draw the picker. The authority remains
    the exclusion constraint, so a bay shown free can still lose a race — the
    booking call is where that is settled.
    """
    space = await service.get_public(db, space_id)
    layout = await bays.list_for_space(db, space.id)
    taken: set[int] = set()
    if start_at and end_at:
        taken = await availability_service.taken_slots(db, space.id, start_at, end_at)
    return BayLayout(
        parking_space_id=space.id,
        total_slots=max(space.total_slots, 1),
        row_width=bays.ROW_WIDTH,
        bays=[
            BayOut(
                slot_index=bay.slot_index,
                label=bay.label,
                row_index=bay.row_index,
                col_index=bay.col_index,
                is_active=bay.is_active,
                taken=(bay.slot_index in taken) if (start_at and end_at) else None,
            )
            for bay in layout
        ],
    )


@router.put("/{space_id}/bays", response_model=list[BayOut])
async def rename_bays(space_id: uuid.UUID, data: BayRename, user: CurrentUser, db: DB):
    """Set the names painted on the floor."""
    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    updated = await bays.rename(db, space, data.labels)
    await db.commit()
    return updated


@router.post("/{space_id}/bays/{slot_index}/active", response_model=BayOut)
async def set_bay_active(
    space_id: uuid.UUID, slot_index: int, data: BayActive, user: CurrentUser, db: DB
):
    """Take a bay out of service without changing the layout."""
    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    bay = await bays.set_active(db, space, slot_index, data.is_active)
    await db.commit()
    await db.refresh(bay)
    return bay


# --------------------------------------------------------------------------- #
# Availability
# --------------------------------------------------------------------------- #
@router.get("/{space_id}/availability", response_model=AvailabilityOut)
async def get_availability(
    space_id: uuid.UUID,
    db: DB,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
):
    space = await service.get_public(db, space_id)
    return AvailabilityOut(
        rules=await availability_service.get_rules(db, space.id),
        blocks=await availability_crud.list_blocks(db, space.id, from_at, to_at),
    )


@router.put("/{space_id}/availability", response_model=list[RuleOut])
async def replace_availability(space_id: uuid.UUID, data: RulesReplace, user: CurrentUser, db: DB):
    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    rules = await availability_crud.replace_rules(db, space, data)
    await db.commit()
    return rules


@router.post("/{space_id}/blocks", response_model=BlockOut, status_code=status.HTTP_201_CREATED)
async def create_block(space_id: uuid.UUID, data: BlockIn, user: CurrentUser, db: DB):
    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    block = await availability_crud.create_block(db, space, data)
    await db.commit()
    await db.refresh(block)
    return block


@router.get("/{space_id}/blocks", response_model=list[BlockOut])
async def list_blocks(
    space_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
):
    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    return await availability_crud.list_blocks(db, space.id, from_at, to_at)


@router.delete("/{space_id}/blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_block(space_id: uuid.UUID, block_id: uuid.UUID, user: CurrentUser, db: DB):
    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    await availability_crud.delete_block(db, space, block_id)
    await db.commit()


@router.get("/{space_id}/calendar", response_model=CalendarOut)
async def get_calendar(
    space_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    from_date: date | None = None,
    to_date: date | None = None,
):
    """Month-at-a-glance view backing the provider's availability calendar."""
    provider = await provider_service.require_provider(db, user)
    space = await service.get_owned(db, provider, space_id)
    start = from_date or date.today()
    end = to_date or (start + timedelta(days=30))
    if end < start:
        raise Forbidden("to_date must be on or after from_date")
    end = min(end, start + timedelta(days=180))
    days = await availability_service.build_calendar(db, space, start, end)
    return CalendarOut(
        parking_space_id=space.id,
        days=[
            CalendarDay(
                day=d.day,
                windows=d.windows,
                blocked=d.blocked,
                booked_slots=d.booked_slots,
                total_slots=d.total_slots,
                is_open=d.is_open,
            )
            for d in days
        ],
    )


# --------------------------------------------------------------------------- #
# Public listing detail — last, so it doesn't shadow the routes above
# --------------------------------------------------------------------------- #
@router.get("/{space_id}", response_model=ParkingSpacePublic)
async def get_parking(space_id: uuid.UUID, db: DB):
    return await service.get_public(db, space_id)

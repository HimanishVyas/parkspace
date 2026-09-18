"""Parking listing management and renter-facing search."""
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Float, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import Conflict, Forbidden, NotFound
from app.modules.availability import service as availability_service
from app.modules.parking.location import MAX_RADIUS_KM, distance_km_expression, within_bounding_box
from app.modules.parking.models import (
    ListingStatus,
    ParkingPhoto,
    ParkingPrice,
    ParkingSpace,
    ParkingType,
    PricingUnit,
    VehicleType,
)
from app.modules.parking.schemas import ParkingSpaceCreate, ParkingSpaceUpdate, PriceIn
from app.modules.providers.models import Provider, ProviderStatus
from app.modules.settings.schemas import PlatformConfig

# Upper bound on rows the availability filter post-processes in one search.
# Comfortably above a pilot city's inventory; keeps the query bounded regardless.
SEARCH_CANDIDATE_CAP = 500
MAX_PHOTOS_PER_SPACE = 10


@dataclass
class SearchParams:
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float = 5.0
    query: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    unit: PricingUnit | None = None
    vehicle_type: VehicleType | None = None
    parking_type: ParkingType | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    sort: str = "distance"
    limit: int = 20
    offset: int = 0


@dataclass
class SearchHit:
    space: ParkingSpace
    distance_km: float | None


# --------------------------------------------------------------------------- #
# Listing management
# --------------------------------------------------------------------------- #
async def create(db: AsyncSession, provider: Provider, data: ParkingSpaceCreate) -> ParkingSpace:
    payload = data.model_dump(exclude={"prices", "vehicle_types"})
    space = ParkingSpace(
        provider_id=provider.id,
        vehicle_types=[v.value for v in data.vehicle_types],
        status=ListingStatus.DRAFT,
        # Populating the collections here keeps them loaded: reading an unloaded
        # relationship on a just-flushed row would emit IO outside the greenlet.
        prices=[ParkingPrice(unit=price.unit, amount=price.amount) for price in data.prices],
        photos=[],
        **payload,
    )
    db.add(space)
    await db.flush()
    await db.refresh(space)
    return space


async def _replace_prices(db: AsyncSession, space: ParkingSpace, prices: list[PriceIn]) -> None:
    existing = {p.unit: p for p in space.prices}
    wanted = {p.unit: p.amount for p in prices}
    for unit, amount in wanted.items():
        if unit in existing:
            existing[unit].amount = amount
        else:
            db.add(ParkingPrice(parking_space_id=space.id, unit=unit, amount=amount))
    for unit, row in existing.items():
        if unit not in wanted:
            await db.delete(row)
    await db.flush()


async def get_owned(db: AsyncSession, provider: Provider, space_id: uuid.UUID) -> ParkingSpace:
    space = await db.get(ParkingSpace, space_id)
    if space is None:
        raise NotFound("Parking space not found")
    if space.provider_id != provider.id:
        raise Forbidden("This parking space belongs to another provider")
    return space


async def get_for_admin(db: AsyncSession, space_id: uuid.UUID) -> ParkingSpace:
    space = await db.get(ParkingSpace, space_id)
    if space is None:
        raise NotFound("Parking space not found")
    return space


async def get_public(db: AsyncSession, space_id: uuid.UUID) -> ParkingSpace:
    """A listing as a renter may see it — published, from an active provider."""
    space = await db.scalar(
        select(ParkingSpace)
        .join(Provider, Provider.id == ParkingSpace.provider_id)
        .where(
            ParkingSpace.id == space_id,
            ParkingSpace.status == ListingStatus.PUBLISHED,
            Provider.status == ProviderStatus.ACTIVE,
        )
        .options(selectinload(ParkingSpace.photos), selectinload(ParkingSpace.prices))
    )
    if space is None:
        raise NotFound("Parking space not found")
    return space


async def list_for_provider(
    db: AsyncSession, provider: Provider, status: ListingStatus | None = None
) -> list[ParkingSpace]:
    conditions = [ParkingSpace.provider_id == provider.id]
    if status is not None:
        conditions.append(ParkingSpace.status == status)
    rows = await db.scalars(
        select(ParkingSpace).where(*conditions).order_by(ParkingSpace.created_at.desc())
    )
    return list(rows.all())


async def update(db: AsyncSession, space: ParkingSpace, data: ParkingSpaceUpdate) -> ParkingSpace:
    changes = data.model_dump(exclude_unset=True, exclude={"prices"})
    if "vehicle_types" in changes and changes["vehicle_types"] is not None:
        changes["vehicle_types"] = [VehicleType(v).value for v in changes["vehicle_types"]]
    if "total_slots" in changes and changes["total_slots"] is not None:
        await _assert_slot_reduction_safe(db, space, changes["total_slots"])
    for key, value in changes.items():
        if value is not None:
            setattr(space, key, value)
    if data.prices is not None:
        await _replace_prices(db, space, data.prices)
    await db.flush()
    await db.refresh(space)
    return space


async def _assert_slot_reduction_safe(db: AsyncSession, space: ParkingSpace, new_total: int) -> None:
    """Refuse a capacity cut that would strand an existing booking's slot."""
    from app.modules.bookings.models import BLOCKING_STATUSES, Booking

    if new_total >= space.total_slots:
        return
    highest = await db.scalar(
        select(func.max(Booking.slot_index)).where(
            Booking.parking_space_id == space.id, Booking.status.in_(BLOCKING_STATUSES)
        )
    )
    if highest is not None and highest >= new_total:
        raise Conflict(
            "Existing bookings use more slots than that. Cancel or wait for them to finish first.",
            code="SLOTS_IN_USE",
        )


async def publish(db: AsyncSession, space: ParkingSpace, config: PlatformConfig) -> ParkingSpace:
    """Move a listing live, or into the approval queue when admins require it."""
    if space.status in (ListingStatus.SUSPENDED, ListingStatus.REJECTED):
        raise Forbidden("This listing cannot be published; contact support", code="LISTING_BLOCKED")
    if not space.authority_confirmed:
        raise Conflict("Confirm your authority to rent this space before publishing", code="AUTHORITY_REQUIRED")
    if not space.prices:
        raise Conflict("Set at least one price before publishing", code="PRICE_REQUIRED")
    rules = await availability_service.get_rules(db, space.id)
    if not any(rule.is_active for rule in rules):
        raise Conflict("Set your availability before publishing", code="AVAILABILITY_REQUIRED")
    space.status = (
        ListingStatus.PENDING_APPROVAL if config.listing_requires_approval else ListingStatus.PUBLISHED
    )
    space.rejection_reason = None
    await db.flush()
    return space


async def pause(db: AsyncSession, space: ParkingSpace) -> ParkingSpace:
    if space.status not in (ListingStatus.PUBLISHED, ListingStatus.PENDING_APPROVAL):
        raise Conflict("Only a live listing can be paused", code="INVALID_STATE")
    space.status = ListingStatus.PAUSED
    await db.flush()
    return space


async def delete(db: AsyncSession, space: ParkingSpace) -> None:
    """Listings with bookings are never destroyed — booking history must survive."""
    from app.modules.bookings.models import Booking

    has_bookings = await db.scalar(select(Booking.id).where(Booking.parking_space_id == space.id).limit(1))
    if has_bookings:
        raise Conflict(
            "This listing has bookings and cannot be deleted. Pause it instead.", code="HAS_BOOKINGS"
        )
    await db.delete(space)
    await db.flush()


# --------------------------------------------------------------------------- #
# Photos
# --------------------------------------------------------------------------- #
async def add_photo(
    db: AsyncSession, space: ParkingSpace, storage_key: str, url: str, caption: str | None = None
) -> ParkingPhoto:
    count = await db.scalar(
        select(func.count()).select_from(ParkingPhoto).where(ParkingPhoto.parking_space_id == space.id)
    )
    if (count or 0) >= MAX_PHOTOS_PER_SPACE:
        raise Conflict(f"A listing can have at most {MAX_PHOTOS_PER_SPACE} photos", code="TOO_MANY_PHOTOS")
    photo = ParkingPhoto(
        parking_space_id=space.id, storage_key=storage_key, url=url, caption=caption, sort_order=count or 0
    )
    db.add(photo)
    await db.flush()
    return photo


async def delete_photo(db: AsyncSession, space: ParkingSpace, photo_id: uuid.UUID) -> str:
    photo = await db.get(ParkingPhoto, photo_id)
    if photo is None or photo.parking_space_id != space.id:
        raise NotFound("Photo not found")
    storage_key = photo.storage_key
    await db.delete(photo)
    await db.flush()
    return storage_key


async def reorder_photos(db: AsyncSession, space: ParkingSpace, photo_ids: list[uuid.UUID]) -> None:
    photos = {p.id: p for p in space.photos}
    if set(photo_ids) != set(photos):
        raise Conflict("Provide every photo id for this listing exactly once", code="INVALID_ORDER")
    for index, photo_id in enumerate(photo_ids):
        photos[photo_id].sort_order = index
    await db.flush()


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
def _base_search_query(params: SearchParams):
    query = (
        select(ParkingSpace)
        .join(Provider, Provider.id == ParkingSpace.provider_id)
        .where(
            ParkingSpace.status == ListingStatus.PUBLISHED,
            Provider.status == ProviderStatus.ACTIVE,
        )
    )
    if params.vehicle_type is not None:
        query = query.where(ParkingSpace.vehicle_types.any(params.vehicle_type.value))
    if params.parking_type is not None:
        query = query.where(ParkingSpace.parking_type == params.parking_type)
    if params.query:
        pattern = f"%{params.query.strip()}%"
        query = query.where(
            or_(
                ParkingSpace.city.ilike(pattern),
                ParkingSpace.address_line.ilike(pattern),
                ParkingSpace.landmark.ilike(pattern),
                ParkingSpace.title.ilike(pattern),
            )
        )
    # Price filters apply to the duration the renter is shopping for; without a
    # unit they apply to any of the listing's prices.
    if params.unit is not None or params.min_price is not None or params.max_price is not None:
        price_conditions = [ParkingPrice.parking_space_id == ParkingSpace.id]
        if params.unit is not None:
            price_conditions.append(ParkingPrice.unit == params.unit)
        if params.min_price is not None:
            price_conditions.append(ParkingPrice.amount >= params.min_price)
        if params.max_price is not None:
            price_conditions.append(ParkingPrice.amount <= params.max_price)
        query = query.where(select(ParkingPrice.id).where(and_(*price_conditions)).exists())
    return query


async def search(db: AsyncSession, params: SearchParams) -> tuple[list[SearchHit], int]:
    """Radius/text search, then an availability pass over the candidates.

    Availability is filtered in Python because the weekly-rule semantics don't
    reduce to a single SQL predicate. The SQL side narrows candidates first
    (status, geography, vehicle, price), so the Python pass sees a small set.
    """
    query = _base_search_query(params)
    distance_column = None

    if params.latitude is not None and params.longitude is not None:
        radius = min(max(params.radius_km, 0.1), MAX_RADIUS_KM)
        distance_column = distance_km_expression(
            ParkingSpace.latitude, ParkingSpace.longitude, params.latitude, params.longitude
        ).label("distance_km")
        query = query.where(
            within_bounding_box(
                ParkingSpace.latitude.cast(Float),
                ParkingSpace.longitude.cast(Float),
                params.latitude,
                params.longitude,
                radius,
            ),
            distance_column <= radius,
        )

    if params.sort == "price_asc" or params.sort == "price_desc":
        unit = params.unit or PricingUnit.HOURLY
        price_scalar = (
            select(ParkingPrice.amount)
            .where(ParkingPrice.parking_space_id == ParkingSpace.id, ParkingPrice.unit == unit)
            .scalar_subquery()
        )
        query = query.order_by(price_scalar.asc() if params.sort == "price_asc" else price_scalar.desc())
    elif params.sort == "rating":
        query = query.order_by(ParkingSpace.rating_average.desc().nullslast())
    elif distance_column is not None:
        query = query.order_by(distance_column.asc())
    else:
        query = query.order_by(ParkingSpace.created_at.desc())

    if distance_column is not None:
        query = query.add_columns(distance_column)
    query = query.options(selectinload(ParkingSpace.photos), selectinload(ParkingSpace.prices))

    rows = (await db.execute(query.limit(SEARCH_CANDIDATE_CAP))).all()
    hits = [
        SearchHit(space=row[0], distance_km=round(float(row[1]), 3) if len(row) > 1 else None)
        for row in rows
    ]

    if params.start_at is not None and params.end_at is not None:
        hits = await _filter_by_availability(db, hits, params)

    total = len(hits)
    return hits[params.offset : params.offset + params.limit], total


async def _filter_by_availability(
    db: AsyncSession, hits: list[SearchHit], params: SearchParams
) -> list[SearchHit]:
    assert params.start_at is not None and params.end_at is not None
    space_ids = [hit.space.id for hit in hits]
    if not space_ids:
        return hits

    blocked = await availability_service.blocked_space_ids(db, space_ids, params.start_at, params.end_at)
    rules = await availability_service.rules_by_space(db, space_ids)
    full = await _fully_booked_space_ids(db, hits, params.start_at, params.end_at)
    unit = params.unit or PricingUnit.HOURLY

    available: list[SearchHit] = []
    for hit in hits:
        space_id = hit.space.id
        if space_id in blocked or space_id in full:
            continue
        space_rules = rules.get(space_id, [])
        if not space_rules:
            continue
        if not availability_service.rules_cover_window(
            space_rules, params.start_at, params.end_at, unit
        ):
            continue
        available.append(hit)
    return available


async def _fully_booked_space_ids(
    db: AsyncSession, hits: list[SearchHit], start_at: datetime, end_at: datetime
) -> set[uuid.UUID]:
    """Spaces whose every slot is taken across the requested window."""
    from app.modules.bookings.models import BLOCKING_STATUSES, Booking

    capacity = {hit.space.id: max(hit.space.total_slots, 1) for hit in hits}
    rows = await db.execute(
        select(Booking.parking_space_id, func.count(func.distinct(Booking.slot_index)))
        .where(
            Booking.parking_space_id.in_(list(capacity)),
            Booking.status.in_(BLOCKING_STATUSES),
            Booking.start_at < end_at,
            Booking.end_at > start_at,
        )
        .group_by(Booking.parking_space_id)
    )
    return {space_id for space_id, taken in rows.all() if taken >= capacity.get(space_id, 1)}

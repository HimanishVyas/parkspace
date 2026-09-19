"""Arrival verification.

The problem this solves: a renter has paid and is standing at a gate, and the
provider is not there. Rather than making the renter wait for someone to drive
over, the platform issues a short-lived code to the provider, who reads it out
over a phone call or WhatsApp. The renter types it in and the booking becomes
ACTIVE.

The hop where the code travels from provider to renter is deliberately outside
the platform — that is what makes it work without anyone being present, and also
what the platform cannot observe. So the design assumes that hop can fail:
`state()` reports when the provider has gone quiet for too long, and the renter
is offered support instead of a dead end.
"""
import math
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.time import utcnow
from app.modules.bookings.models import ArrivalCode, Booking, BookingStatus
from app.modules.parking.models import ParkingSpace
from app.modules.settings.schemas import PlatformConfig
from app.modules.users.models import User

# Digits only: this gets read aloud down a phone line, often in a second
# language and against traffic noise. Letters invite B/V and M/N mistakes.
_ALPHABET = "0123456789"
_LENGTH = 6

EARTH_RADIUS_M = 6_371_000


def _generate() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))


def distance_metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance. Same haversine the search module uses."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


async def _space(db: AsyncSession, booking: Booking) -> ParkingSpace:
    space = await db.get(ParkingSpace, booking.parking_space_id)
    if space is None:
        raise NotFound("Parking space not found")
    return space


async def get_code(db: AsyncSession, booking_id) -> ArrivalCode | None:
    return await db.scalar(select(ArrivalCode).where(ArrivalCode.booking_id == booking_id))


def required_for(space: ParkingSpace) -> bool:
    return bool(space.requires_arrival_code)


async def announce(
    db: AsyncSession,
    booking: Booking,
    user: User,
    config: PlatformConfig,
    latitude: float | None = None,
    longitude: float | None = None,
) -> ArrivalCode:
    """Renter says "I've reached". Issues a code for the provider to pass on.

    Re-announcing before the current code expires returns the same code, so a
    renter tapping twice does not invalidate the number the provider just read
    off their screen.
    """
    if booking.renter_id != user.id:
        raise Forbidden("This booking belongs to another account")
    if booking.status == BookingStatus.ACTIVE:
        raise Conflict("You have already been checked in", code="ALREADY_ACTIVE")
    if booking.status != BookingStatus.CONFIRMED:
        raise Conflict(
            f"A {booking.status.value.lower()} booking cannot be checked in", code="INVALID_STATE"
        )

    now = utcnow()
    if now < booking.start_at - timedelta(minutes=config.arrival_early_minutes):
        raise Conflict(
            "It is too early to check in for this booking", code="TOO_EARLY"
        )
    if now > booking.end_at:
        raise Conflict("This booking has already ended", code="TOO_LATE")

    space = await _space(db, booking)
    if latitude is not None and longitude is not None:
        away = distance_metres(latitude, longitude, float(space.latitude), float(space.longitude))
        if away > config.arrival_geofence_metres:
            raise ValidationFailed(
                "You look too far from the parking space to check in",
                details=[{"code": "TOO_FAR", "metres_away": round(away)}],
            )

    existing = await get_code(db, booking.id)
    if existing is not None:
        if existing.verified_at is not None:
            raise Conflict("You have already been checked in", code="ALREADY_ACTIVE")
        if existing.expires_at > now:
            return existing  # still live — don't move the goalposts on the provider
        await db.delete(existing)
        await db.flush()

    code = ArrivalCode(
        booking_id=booking.id,
        code=_generate(),
        expires_at=now + timedelta(minutes=config.arrival_code_ttl_minutes),
        latitude=latitude,
        longitude=longitude,
    )
    db.add(code)
    await db.flush()
    return code


async def verify(
    db: AsyncSession, booking: Booking, user: User, submitted: str, config: PlatformConfig
) -> Booking:
    """Renter enters the code. On success the booking becomes ACTIVE."""
    if booking.renter_id != user.id:
        raise Forbidden("This booking belongs to another account")
    if booking.status == BookingStatus.ACTIVE:
        return booking  # idempotent: a double submit is not an error
    if booking.status != BookingStatus.CONFIRMED:
        raise Conflict(
            f"A {booking.status.value.lower()} booking cannot be checked in", code="INVALID_STATE"
        )

    code = await get_code(db, booking.id)
    if code is None:
        raise Conflict("Tell the provider you have arrived first", code="NO_CODE")

    now = utcnow()
    if code.expires_at <= now:
        raise Conflict("That code has expired. Ask for a new one.", code="CODE_EXPIRED")
    if code.attempts >= config.arrival_code_max_attempts:
        raise Conflict("Too many incorrect attempts. Ask for a new code.", code="TOO_MANY_ATTEMPTS")

    # Count the attempt and COMMIT it before judging the code.
    #
    # A flush alone is not enough: rejecting a wrong code raises, the request
    # never reaches its commit, and the whole transaction — including the
    # increment — rolls back. That left the attempt counter permanently at zero,
    # so the lockout never triggered and a six-digit code could be tried
    # indefinitely. The attempt has to be durable whatever happens next.
    code.attempts += 1
    await db.commit()

    if not secrets.compare_digest(code.code, submitted.strip()):
        left = max(config.arrival_code_max_attempts - code.attempts, 0)
        raise ValidationFailed(
            "That code is not right",
            details=[{"code": "BAD_CODE", "attempts_left": left}],
        )

    code.verified_at = now
    booking.status = BookingStatus.ACTIVE
    await db.flush()
    return booking


def state(booking: Booking, code: ArrivalCode | None, config: PlatformConfig, *, for_provider: bool) -> dict:
    """What each side should see. Only the provider is ever shown the code."""
    now = utcnow()
    waiting_minutes = None
    if code is not None and code.verified_at is None:
        waiting_minutes = round((now - code.requested_at).total_seconds() / 60, 1)

    expired = bool(code and code.expires_at <= now and code.verified_at is None)
    payload: dict = {
        "booking_id": booking.id,
        "status": booking.status,
        "announced": code is not None,
        "verified": bool(code and code.verified_at),
        "expired": expired,
        "expires_at": code.expires_at if code and not expired else None,
        "attempts_left": (
            max(config.arrival_code_max_attempts - code.attempts, 0) if code and not expired else None
        ),
        "waiting_minutes": waiting_minutes,
        # The renter has waited long enough that the provider is probably not
        # coming; offer them a way out rather than leaving them at the gate.
        "escalate": bool(
            waiting_minutes is not None
            and not (code and code.verified_at)
            and waiting_minutes >= config.arrival_escalate_minutes
        ),
        "code": None,
    }
    if for_provider and code is not None and code.verified_at is None and not expired:
        payload["code"] = code.code
    return payload


async def waiting_for_provider(
    db: AsyncSession, provider_id, config: PlatformConfig
) -> list[tuple[Booking, ArrivalCode]]:
    """Every renter of this provider currently standing at a gate.

    One query rather than polling each booking, because this is checked often —
    it is the provider's alarm bell, and it has to stay cheap. Longest wait
    first: whoever has been standing there longest needs the code most.
    """
    now = utcnow()
    rows = await db.execute(
        select(Booking, ArrivalCode)
        .join(ArrivalCode, ArrivalCode.booking_id == Booking.id)
        .where(
            Booking.provider_id == provider_id,
            Booking.status == BookingStatus.CONFIRMED,
            ArrivalCode.verified_at.is_(None),
            ArrivalCode.expires_at > now,
            ArrivalCode.attempts < config.arrival_code_max_attempts,
        )
        .order_by(ArrivalCode.requested_at.asc())
    )
    return [(booking, code) for booking, code in rows.all()]

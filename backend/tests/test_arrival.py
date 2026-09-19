"""Arrival verification: the renter announces, the provider relays a code, the
renter proves they have it, and only then does the booking become ACTIVE."""
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.time import utcnow
from app.modules.bookings.models import ArrivalCode, Booking
from tests.conftest import ALL_WEEK_8_TO_20, add_vehicle, at, create_listing, pay_for, register


async def gated_booking(provider, renter, db, *, gated=True, hour=10, plate="GJ01AR0001"):
    """A confirmed booking, on a listing that does (or does not) gate arrival,
    whose window is happening right now.

    Bookings have to be made inside the listing's opening hours, which are in
    the future; arrival can only be announced once you are nearly there. So the
    booking is made normally and then its window is moved onto the clock.
    """
    space = await create_listing(
        provider,
        requires_arrival_code=gated,
        rules=ALL_WEEK_8_TO_20,
        title="Unattended driveway",
    )
    vehicle = await add_vehicle(renter, registration=plate)
    created = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "HOURLY",
            "start_at": at(7, hour).isoformat(),
            "end_at": at(7, hour + 2).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    booking = await pay_for(renter, created.json()["id"])
    assert booking["status"] == "CONFIRMED"

    row = await db.get(Booking, uuid.UUID(booking["id"]))
    row.start_at = utcnow() - timedelta(minutes=5)
    row.end_at = utcnow() + timedelta(hours=2)
    await db.commit()
    return space, booking


async def code_for(db, booking_id):
    return await db.scalar(select(ArrivalCode).where(ArrivalCode.booking_id == booking_id))


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #


async def test_full_arrival_flow(provider, renter, db):
    _, booking = await gated_booking(provider, renter, db)

    # The renter is told a code is needed, but never told what it is.
    announced = await renter.post(f"/bookings/{booking['id']}/arrival", json={})
    assert announced.status_code == 200, announced.text
    state = announced.json()
    assert state["announced"] is True
    assert state["verified"] is False
    assert state["code"] is None, "the renter must never be handed their own code"

    # The provider can see it — that is the whole point.
    provider_view = await provider.get(f"/bookings/{booking['id']}/arrival")
    assert provider_view.status_code == 200, provider_view.text
    code = provider_view.json()["code"]
    assert code and len(code) == 6 and code.isdigit()

    # The renter types in what the provider read out.
    verified = await renter.post(f"/bookings/{booking['id']}/arrival/verify", json={"code": code})
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "ACTIVE"


async def test_verifying_twice_is_idempotent(provider, renter, db):
    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0002")
    await renter.post(f"/bookings/{booking['id']}/arrival", json={})
    code = (await provider.get(f"/bookings/{booking['id']}/arrival")).json()["code"]
    first = await renter.post(f"/bookings/{booking['id']}/arrival/verify", json={"code": code})
    assert first.status_code == 200
    second = await renter.post(f"/bookings/{booking['id']}/arrival/verify", json={"code": code})
    assert second.status_code == 200
    assert second.json()["status"] == "ACTIVE"


async def test_announcing_twice_keeps_the_same_code(provider, renter, db):
    """The provider may already have read the number off their screen."""
    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0003")
    await renter.post(f"/bookings/{booking['id']}/arrival", json={})
    first = (await provider.get(f"/bookings/{booking['id']}/arrival")).json()["code"]
    await renter.post(f"/bookings/{booking['id']}/arrival", json={})
    second = (await provider.get(f"/bookings/{booking['id']}/arrival")).json()["code"]
    assert first == second


# --------------------------------------------------------------------------- #
# The code is the only thing standing between a renter and the bay
# --------------------------------------------------------------------------- #


async def test_wrong_code_is_rejected_and_counted(provider, renter, db):
    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0004")
    await renter.post(f"/bookings/{booking['id']}/arrival", json={})
    bad = await renter.post(f"/bookings/{booking['id']}/arrival/verify", json={"code": "000000"})
    assert bad.status_code == 422, bad.text
    state = (await renter.get(f"/bookings/{booking['id']}/arrival")).json()
    assert state["attempts_left"] == 4
    assert state["verified"] is False


async def test_code_burns_after_too_many_attempts(provider, renter, db):
    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0005")
    await renter.post(f"/bookings/{booking['id']}/arrival", json={})
    real = (await provider.get(f"/bookings/{booking['id']}/arrival")).json()["code"]
    wrong = "111111" if real != "111111" else "222222"
    for _ in range(5):
        await renter.post(f"/bookings/{booking['id']}/arrival/verify", json={"code": wrong})
    # Even the correct code no longer works once the budget is spent.
    blocked = await renter.post(f"/bookings/{booking['id']}/arrival/verify", json={"code": real})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"


async def test_expired_code_is_rejected(provider, renter, db):
    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0006")
    await renter.post(f"/bookings/{booking['id']}/arrival", json={})
    code_row = await code_for(db, booking["id"])
    real = code_row.code
    code_row.expires_at = utcnow() - timedelta(seconds=1)
    await db.commit()

    stale = await renter.post(f"/bookings/{booking['id']}/arrival/verify", json={"code": real})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CODE_EXPIRED"


async def test_cannot_verify_without_announcing(provider, renter, db):
    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0007")
    early = await renter.post(f"/bookings/{booking['id']}/arrival/verify", json={"code": "123456"})
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "NO_CODE"


async def test_another_renter_cannot_touch_the_arrival(client, provider, renter, db):
    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0008")
    await renter.post(f"/bookings/{booking['id']}/arrival", json={})
    intruder = await register(client, full_name="Chancer")
    assert (await intruder.get(f"/bookings/{booking['id']}/arrival")).status_code in (403, 404)
    assert (
        await intruder.post(f"/bookings/{booking['id']}/arrival", json={})
    ).status_code in (403, 404)


async def test_geofence_rejects_a_renter_who_is_nowhere_near(provider, renter, db):
    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0009")
    far = await renter.post(
        f"/bookings/{booking['id']}/arrival",
        json={"latitude": 19.0760, "longitude": 72.8777},  # Mumbai, ~450km away
    )
    assert far.status_code == 422, far.text
    assert far.json()["error"]["details"][0]["code"] == "TOO_FAR"


async def test_geofence_accepts_a_renter_at_the_space(provider, renter, db):
    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0010")
    here = await renter.post(
        f"/bookings/{booking['id']}/arrival",
        json={"latitude": 23.0225, "longitude": 72.5714},
    )
    assert here.status_code == 200, here.text


# --------------------------------------------------------------------------- #
# Interaction with the rest of the lifecycle
# --------------------------------------------------------------------------- #


async def test_ungated_listing_needs_no_code(provider, renter, db):
    """The default stays exactly as it was: no extra step."""
    space, booking = await gated_booking(provider, renter, db, gated=False, plate="GJ01AR0011")
    assert space["requires_arrival_code"] is False
    refused = await renter.post(f"/bookings/{booking['id']}/arrival", json={})
    # Nothing to announce against — the booking simply activates on schedule.
    assert refused.status_code in (200, 409)


async def test_maintenance_does_not_auto_activate_a_gated_booking(provider, renter, db):
    """Otherwise the timer would let a renter in without ever proving anything."""
    from app.modules.bookings import maintenance

    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0012")
    await maintenance.activate_started(db)
    await db.commit()

    after = (await renter.get(f"/bookings/{booking['id']}")).json()
    assert after["status"] == "CONFIRMED", "a gated booking must wait for its code"


async def test_maintenance_still_auto_activates_an_ungated_booking(provider, renter, db):
    """The exclusion must be targeted — ordinary bookings still start on time."""
    from app.modules.bookings import maintenance

    _, booking = await gated_booking(provider, renter, db, gated=False, plate="GJ01AR0014")
    await maintenance.activate_started(db)
    await db.commit()

    after = (await renter.get(f"/bookings/{booking['id']}")).json()
    assert after["status"] == "ACTIVE"


async def test_arrival_state_flags_a_silent_provider(provider, renter, db):
    """The renter has paid and is at a gate; they need a way out, not a spinner."""
    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0013")
    await renter.post(f"/bookings/{booking['id']}/arrival", json={})
    code_row = await code_for(db, booking["id"])
    code_row.requested_at = utcnow() - timedelta(minutes=30)
    await db.commit()

    state = (await renter.get(f"/bookings/{booking['id']}/arrival")).json()
    assert state["escalate"] is True


async def test_waiting_queue_shows_the_provider_who_is_at_a_gate(provider, renter, db):
    """The provider's alarm bell. A renter buried down a list of bookings is a
    renter left standing outside."""
    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0015")
    empty = (await provider.get("/bookings/arrivals/waiting")).json()
    assert empty == [], "nobody has announced yet"

    await renter.post(f"/bookings/{booking['id']}/arrival", json={})
    waiting = (await provider.get("/bookings/arrivals/waiting")).json()
    assert len(waiting) == 1
    entry = waiting[0]
    assert entry["reference"] == booking["reference"]
    assert entry["vehicle_number"] == "GJ01AR0015"
    assert len(entry["code"]) == 6

    # Once verified they drop off the queue.
    await renter.post(f"/bookings/{booking['id']}/arrival/verify", json={"code": entry["code"]})
    assert (await provider.get("/bookings/arrivals/waiting")).json() == []


async def test_waiting_queue_is_scoped_to_the_signed_in_provider(client, provider, renter, db):
    _, booking = await gated_booking(provider, renter, db, plate="GJ01AR0016")
    await renter.post(f"/bookings/{booking['id']}/arrival", json={})

    other = await register(client, full_name="Other Provider")
    await other.post("/providers", json={"provider_type": "INDIVIDUAL"})
    assert (await other.get("/bookings/arrivals/waiting")).json() == []

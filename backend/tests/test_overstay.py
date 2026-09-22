"""Charging for time taken beyond the booked window.

The arithmetic matters, but the two things that would actually hurt in
production are: an overstaying car must keep blocking its bay, and an abandoned
booking must not block it forever.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import update

from app.core.time import utcnow
from app.modules.bookings import maintenance, overstay
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.settings.service import get_config
from tests.conftest import ALL_WEEK_8_TO_20, add_vehicle, at, create_listing, pay_for, register


async def parked_booking(provider, renter, db, *, plate="GJ01OS0001", ended_minutes_ago=0, rate="60.00"):
    """An ACTIVE booking whose window ended `ended_minutes_ago` minutes back."""
    space = await create_listing(
        provider, prices=[{"unit": "HOURLY", "amount": rate}], rules=ALL_WEEK_8_TO_20
    )
    vehicle = await add_vehicle(renter, registration=plate)
    created = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "HOURLY",
            "start_at": at(7, 10).isoformat(),
            "end_at": at(7, 12).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    booking = await pay_for(renter, created.json()["id"])

    row = await db.get(Booking, uuid.UUID(booking["id"]))
    now = utcnow()
    row.end_at = now - timedelta(minutes=ended_minutes_ago)
    row.start_at = row.end_at - timedelta(hours=2)
    row.status = BookingStatus.ACTIVE
    await db.commit()
    return space, booking, row


# --------------------------------------------------------------------------- #
# The meter
# --------------------------------------------------------------------------- #


async def test_inside_the_grace_period_nothing_is_owed(provider, renter, db):
    _, booking, _ = await parked_booking(provider, renter, db, ended_minutes_ago=10)
    quote = (await renter.get(f"/bookings/{booking['id']}/overstay")).json()
    assert quote["overstay_minutes"] == 0
    assert Decimal(quote["overstay_amount"]) == Decimal("0.00")


async def test_past_grace_the_meter_runs_from_the_end_time(provider, renter, db):
    """Counting from the end of grace would make 16 minutes late cost the same
    as 1 minute late."""
    _, booking, _ = await parked_booking(provider, renter, db, ended_minutes_ago=20, plate="GJ01OS0002")
    quote = (await renter.get(f"/bookings/{booking['id']}/overstay")).json()
    # 20 min over, rounded up to a 15-minute block = 30 minutes.
    assert quote["overstay_minutes"] == 30
    # Rs 60/hr x 1.5 = Rs 90/hr, for half an hour.
    assert Decimal(quote["overstay_amount"]) == Decimal("45.00")


async def test_billing_is_in_whole_increments(provider, renter, db):
    _, booking, _ = await parked_booking(provider, renter, db, ended_minutes_ago=16, plate="GJ01OS0003")
    quote = (await renter.get(f"/bookings/{booking['id']}/overstay")).json()
    assert quote["overstay_minutes"] == 30, "16 minutes rounds up to two 15-minute blocks"


async def test_the_meter_stops_at_the_cap(provider, renter, db):
    _, booking, _ = await parked_booking(
        provider, renter, db, ended_minutes_ago=60 * 40, plate="GJ01OS0004"
    )
    quote = (await renter.get(f"/bookings/{booking['id']}/overstay")).json()
    config = await get_config(db)
    assert quote["meter_capped"] is True
    assert quote["overstay_minutes"] == config.overstay_max_hours * 60


async def test_a_daily_booking_still_yields_an_hourly_meter(provider, renter, db):
    """A booking sold by the day has no hourly price, but the meter needs one."""
    space = await create_listing(
        provider,
        prices=[{"unit": "DAILY", "amount": "240.00"}],
        rules=ALL_WEEK_8_TO_20,
        title="Daily bay",
    )
    vehicle = await add_vehicle(renter, registration="GJ01OS0005")
    created = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "DAILY",
            "start_at": at(7, 0).isoformat(),
            "quantity": 1,
        },
    )
    assert created.status_code == 201, created.text
    booking = await pay_for(renter, created.json()["id"])
    row = await db.get(Booking, uuid.UUID(booking["id"]))
    row.end_at = utcnow() - timedelta(minutes=50)
    row.start_at = row.end_at - timedelta(hours=12)
    row.status = BookingStatus.ACTIVE
    await db.commit()

    quote = (await renter.get(f"/bookings/{booking['id']}/overstay")).json()
    # Rs 240 over 12 hours = Rs 20/hr, x1.5 = Rs 30/hr. 50 min over rounds up
    # to one hour.
    assert Decimal(quote["overstay_amount"]) == Decimal("30.00")


# --------------------------------------------------------------------------- #
# The bay
# --------------------------------------------------------------------------- #


async def test_an_overstaying_booking_still_blocks_its_bay(client, provider, renter, db):
    """The one that would really hurt: letting the next renter book a bay with a
    car still sitting in it."""
    space, booking, row = await parked_booking(
        provider, renter, db, ended_minutes_ago=30, plate="GJ01OS0006"
    )
    config = await get_config(db)
    await maintenance.start_overstays(db, config)
    await db.commit()
    await db.refresh(row)
    assert row.status == BookingStatus.OVERSTAYING

    # A booking in the past is refused before availability is consulted, so ask
    # the question the booking path actually asks: is this slot spoken for?
    from app.modules.availability.service import taken_slots

    held = await taken_slots(db, uuid.UUID(space["id"]), row.start_at, row.end_at)
    assert row.slot_index in held, "an overstaying car must keep holding its bay"

    # And the guarantee this rests on, stated outright.
    from app.modules.bookings.models import BLOCKING_STATUSES

    assert BookingStatus.OVERSTAYING in BLOCKING_STATUSES


async def test_maintenance_moves_a_late_booking_onto_the_meter(provider, renter, db):
    _, _, row = await parked_booking(provider, renter, db, ended_minutes_ago=45, plate="GJ01OS0007")
    config = await get_config(db)
    started = await maintenance.start_overstays(db, config)
    await db.commit()
    await db.refresh(row)
    assert row.id in {b.id for b in started}
    assert row.status == BookingStatus.OVERSTAYING
    assert row.overstay_amount > 0


async def test_a_booking_inside_grace_is_left_for_the_renter_to_close(provider, renter, db):
    """The sweep must not close an ACTIVE booking out for free.

    It runs every minute, so it would always reach a booking one minute past its
    end — inside the grace period — and nothing would ever survive to reach the
    meter. Leaving on time is something the renter says, through /end.
    """
    _, booking, row = await parked_booking(provider, renter, db, ended_minutes_ago=5, plate="GJ01OS0008")
    config = await get_config(db)
    assert await maintenance.start_overstays(db, config) == []
    assert await maintenance.complete_finished(db, config) == []
    await db.commit()
    await db.refresh(row)
    assert row.status == BookingStatus.ACTIVE

    done = await renter.post(f"/bookings/{booking['id']}/end")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "COMPLETED"


async def test_the_meter_is_reachable_under_a_repeating_sweep(provider, renter, db):
    """The regression that made every overstay unreachable.

    Calling the transitions once, on a booking already well past grace, hid it.
    The live scheduler sees a booking every minute from the moment it ends, and
    it is that first pass — inside the grace period — that used to close it.
    """
    _, _, row = await parked_booking(provider, renter, db, ended_minutes_ago=1, plate="GJ01OS0016")
    config = await get_config(db)
    end_at = row.end_at

    # Sweep once a minute across the grace boundary, as the scheduler does.
    for minutes_past_end in range(1, config.overstay_grace_minutes + 3):
        await db.execute(
            update(Booking)
            .where(Booking.id == row.id)
            .values(end_at=utcnow() - timedelta(minutes=minutes_past_end))
        )
        await db.commit()
        await maintenance.run_once(db)

    await db.refresh(row)
    assert row.status == BookingStatus.OVERSTAYING, "the meter must survive a repeating sweep"
    assert row.overstay_amount > 0
    assert end_at is not None


async def test_an_abandoned_overstay_is_eventually_released(provider, renter, db):
    """Otherwise the bay is lost forever to a car nobody came back for."""
    _, _, row = await parked_booking(
        provider, renter, db, ended_minutes_ago=60 * 40, plate="GJ01OS0009"
    )
    config = await get_config(db)
    await maintenance.start_overstays(db, config)
    await db.commit()
    await db.refresh(row)
    assert row.status == BookingStatus.OVERSTAYING

    finished = await maintenance.complete_finished(db, config)
    await db.commit()
    await db.refresh(row)
    assert row.id in {b.id for b in finished}
    assert row.status == BookingStatus.COMPLETED
    assert row.overstay_amount > 0, "the debt stays on the record"


# --------------------------------------------------------------------------- #
# Settling up
# --------------------------------------------------------------------------- #


async def test_cannot_finish_while_money_is_owed(provider, renter, db):
    _, booking, _ = await parked_booking(provider, renter, db, ended_minutes_ago=40, plate="GJ01OS0010")
    refused = await renter.post(f"/bookings/{booking['id']}/end")
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "OVERSTAY_UNPAID"


async def test_paying_the_top_up_then_finishing(provider, renter, db):
    _, booking, _ = await parked_booking(provider, renter, db, ended_minutes_ago=40, plate="GJ01OS0011")
    paid = await renter.post("/payments/sandbox/complete", json={"booking_id": booking["id"]})
    assert paid.status_code == 200, paid.text
    assert paid.json()["overstay_paid_at"] is not None

    done = await renter.post(f"/bookings/{booking['id']}/end")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "COMPLETED"


async def test_leaving_on_time_needs_no_payment(provider, renter, db):
    _, booking, _ = await parked_booking(provider, renter, db, ended_minutes_ago=2, plate="GJ01OS0012")
    done = await renter.post(f"/bookings/{booking['id']}/end")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "COMPLETED"


async def test_ending_twice_is_idempotent(provider, renter, db):
    _, booking, _ = await parked_booking(provider, renter, db, ended_minutes_ago=2, plate="GJ01OS0013")
    assert (await renter.post(f"/bookings/{booking['id']}/end")).status_code == 200
    assert (await renter.post(f"/bookings/{booking['id']}/end")).status_code == 200


async def test_the_top_up_does_not_resurrect_the_booking(provider, renter, db):
    """Capturing an overstay payment must not re-run booking confirmation and
    drag a finished booking back to CONFIRMED."""
    _, booking, row = await parked_booking(provider, renter, db, ended_minutes_ago=40, plate="GJ01OS0014")
    config = await get_config(db)
    await maintenance.start_overstays(db, config)
    await db.commit()

    after = (await renter.post("/payments/sandbox/complete", json={"booking_id": booking["id"]})).json()
    assert after["status"] == "OVERSTAYING", after["status"]
    await db.refresh(row)
    assert row.status == BookingStatus.OVERSTAYING


async def test_another_renter_cannot_pay_your_overstay(client, provider, renter, db):
    _, booking, _ = await parked_booking(provider, renter, db, ended_minutes_ago=40, plate="GJ01OS0015")
    intruder = await register(client, full_name="Chancer")
    refused = await intruder.post("/payments/overstay", json={"booking_id": booking["id"]})
    assert refused.status_code in (403, 404), refused.text

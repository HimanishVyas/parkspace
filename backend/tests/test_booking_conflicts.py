"""Double-booking protection (PRD §13) — the guarantee the marketplace rests on."""
import asyncio

from httpx import ASGITransport, AsyncClient

from tests.conftest import (
    ALL_WEEK_8_TO_20,
    ALL_WEEK_FULL,
    add_vehicle,
    at,
    create_listing,
    register,
)


async def _book(user, space_id, vehicle_id, start_hour, end_hour, day=7):
    return await user.post(
        "/bookings",
        json={
            "parking_space_id": space_id,
            "vehicle_id": vehicle_id,
            "unit": "HOURLY",
            "start_at": at(day, start_hour).isoformat(),
            "end_at": at(day, end_hour).isoformat(),
        },
    )


async def test_overlapping_booking_is_rejected(client, provider, renter):
    space = await create_listing(provider)
    vehicle = await add_vehicle(renter)
    first = await _book(renter, space["id"], vehicle["id"], 10, 13)
    assert first.status_code == 201

    other = await register(client, full_name="Other Renter")
    other_vehicle = await add_vehicle(other, registration="GJ05XY4321")
    for start, end in [(11, 12), (9, 11), (12, 14), (10, 13), (9, 14)]:
        clash = await _book(other, space["id"], other_vehicle["id"], start, end)
        assert clash.status_code == 409, f"{start}-{end} should clash: {clash.text}"
        assert clash.json()["error"]["code"] == "ALREADY_BOOKED"


async def test_adjacent_bookings_are_allowed(client, provider, renter):
    """A booking ends exactly when the next begins — the range is half-open."""
    space = await create_listing(provider)
    vehicle = await add_vehicle(renter)
    assert (await _book(renter, space["id"], vehicle["id"], 10, 13)).status_code == 201

    other = await register(client, full_name="Next Renter")
    other_vehicle = await add_vehicle(other, registration="GJ09PQ1111")
    assert (await _book(other, space["id"], other_vehicle["id"], 13, 15)).status_code == 201
    assert (await _book(other, space["id"], other_vehicle["id"], 8, 10)).status_code == 201


async def test_concurrent_bookings_only_one_wins(app, client, provider):
    """Ten renters go for the same slot at the same moment.

    The exclusion constraint is the arbiter, so exactly one commits regardless of
    how the availability reads interleave.
    """
    space = await create_listing(provider)

    renters = []
    for index in range(10):
        transport = ASGITransport(app=app)
        renter_client = AsyncClient(transport=transport, base_url="http://test")
        user = await register(renter_client, full_name=f"Racer {index}")
        vehicle = await add_vehicle(user, registration=f"GJ01RC{index:04d}")
        renters.append((renter_client, user, vehicle))

    results = await asyncio.gather(
        *[_book(user, space["id"], vehicle["id"], 10, 13) for _, user, vehicle in renters],
        return_exceptions=True,
    )
    for renter_client, _, _ in renters:
        await renter_client.aclose()

    statuses = [r.status_code for r in results if hasattr(r, "status_code")]
    assert len(statuses) == 10, f"unexpected exceptions: {results}"
    assert statuses.count(201) == 1, f"exactly one booking should win, got {statuses}"
    assert statuses.count(409) == 9, statuses


async def test_multi_slot_space_accepts_concurrent_bookings(client, provider):
    """A society space with three bays takes three bookings, then refuses the fourth."""
    space = await create_listing(provider, total_slots=3)

    booked = 0
    rejected = 0
    for index in range(4):
        user = await register(client, full_name=f"Bay Renter {index}")
        vehicle = await add_vehicle(user, registration=f"GJ02BY{index:04d}")
        response = await _book(user, space["id"], vehicle["id"], 10, 13)
        if response.status_code == 201:
            booked += 1
        else:
            assert response.status_code == 409, response.text
            rejected += 1
    assert (booked, rejected) == (3, 1)


async def test_booking_outside_availability_is_rejected(provider, renter):
    space = await create_listing(provider, rules=ALL_WEEK_8_TO_20)
    vehicle = await add_vehicle(renter)
    # 07:00-09:00 starts before the space opens at 08:00.
    response = await _book(renter, space["id"], vehicle["id"], 7, 9)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OUTSIDE_AVAILABILITY"


async def test_blocked_period_is_rejected(provider, renter):
    space = await create_listing(provider)
    block = await provider.post(
        f"/parking/{space['id']}/blocks",
        json={
            "start_at": at(7, 0).isoformat(),
            "end_at": at(8, 0).isoformat(),
            "reason": "Owner needs the spot",
        },
    )
    assert block.status_code == 201, block.text
    vehicle = await add_vehicle(renter)
    response = await _book(renter, space["id"], vehicle["id"], 10, 13)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BLOCKED"


async def test_provider_cannot_block_a_sold_period(provider, renter):
    """Existing bookings win: a provider must cancel before blocking."""
    space = await create_listing(provider)
    vehicle = await add_vehicle(renter)
    assert (await _book(renter, space["id"], vehicle["id"], 10, 13)).status_code == 201

    block = await provider.post(
        f"/parking/{space['id']}/blocks",
        json={"start_at": at(7, 9).isoformat(), "end_at": at(7, 14).isoformat()},
    )
    assert block.status_code == 409
    assert block.json()["error"]["code"] == "BOOKINGS_IN_PERIOD"


async def test_cancelled_booking_frees_the_slot(client, provider, renter):
    space = await create_listing(provider)
    vehicle = await add_vehicle(renter)
    first = await _book(renter, space["id"], vehicle["id"], 10, 13)
    assert first.status_code == 201

    cancelled = await renter.post(
        f"/bookings/{first.json()['id']}/cancel", json={"reason": "Plans changed"}
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"

    other = await register(client, full_name="Second Chance")
    other_vehicle = await add_vehicle(other, registration="GJ07MM2222")
    assert (await _book(other, space["id"], other_vehicle["id"], 10, 13)).status_code == 201


async def test_daily_booking_spans_whole_days(provider, renter):
    space = await create_listing(
        provider,
        prices=[{"unit": "HOURLY", "amount": "50.00"}, {"unit": "DAILY", "amount": "300.00"}],
        rules=ALL_WEEK_FULL,
    )
    vehicle = await add_vehicle(renter)
    response = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "DAILY",
            "start_at": at(7, 0).isoformat(),
            "quantity": 2,
        },
    )
    assert response.status_code == 201, response.text
    booking = response.json()
    assert booking["quantity"] == "2.00"
    assert booking["base_amount"] == "600.00"


async def test_daily_booking_must_start_at_midnight(provider, renter):
    space = await create_listing(
        provider, prices=[{"unit": "DAILY", "amount": "300.00"}], rules=ALL_WEEK_FULL
    )
    vehicle = await add_vehicle(renter)
    response = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "DAILY",
            "start_at": at(7, 10).isoformat(),
            "end_at": at(8, 10).isoformat(),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_BOUNDARY"

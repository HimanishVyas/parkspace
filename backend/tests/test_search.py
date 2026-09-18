"""Search, filtering, distance and the listing/vehicle surfaces."""
from decimal import Decimal

from app.modules.parking.location import bounding_box, haversine_km
from tests.conftest import ALL_WEEK_8_TO_20, ALL_WEEK_FULL, add_vehicle, at, create_listing

# Ahmedabad landmarks, roughly 5 km apart.
ASHRAM_ROAD = (23.0225, 72.5714)
BODAKDEV = (23.0400, 72.5100)


def test_haversine_matches_known_distance():
    distance = haversine_km(*ASHRAM_ROAD, *BODAKDEV)
    assert 6.0 < distance < 7.5


def test_bounding_box_contains_the_circle():
    min_lat, max_lat, min_lon, max_lon = bounding_box(23.0225, 72.5714, 5)
    assert min_lat < 23.0225 < max_lat
    assert min_lon < 72.5714 < max_lon
    # The box must be a superset of the circle, never tighter (the edge sits
    # exactly on the radius, so allow for float error rather than demanding >).
    assert haversine_km(23.0225, 72.5714, max_lat, 72.5714) >= 5 - 1e-6
    # A corner is further out than the radius, which is what makes it a superset.
    assert haversine_km(23.0225, 72.5714, max_lat, max_lon) > 5


async def test_radius_search_excludes_distant_listings(client, provider):
    near = await create_listing(provider, title="Near listing", latitude=ASHRAM_ROAD[0], longitude=ASHRAM_ROAD[1])
    await create_listing(provider, title="Far listing", latitude=BODAKDEV[0], longitude=BODAKDEV[1])

    tight = await client.get(
        "/api/v1/parking",
        params={"latitude": ASHRAM_ROAD[0], "longitude": ASHRAM_ROAD[1], "radius_km": 2},
    )
    assert [item["id"] for item in tight.json()["items"]] == [near["id"]]

    wide = await client.get(
        "/api/v1/parking",
        params={"latitude": ASHRAM_ROAD[0], "longitude": ASHRAM_ROAD[1], "radius_km": 20},
    )
    assert wide.json()["total"] == 2
    # Results come back nearest first.
    distances = [item["distance_km"] for item in wide.json()["items"]]
    assert distances == sorted(distances)


async def test_filters_narrow_the_results(client, provider):
    await create_listing(
        provider, title="Covered car park", parking_type="COVERED", vehicle_types=["CAR"],
        prices=[{"unit": "HOURLY", "amount": "80.00"}],
    )
    await create_listing(
        provider, title="Open bike park", parking_type="OPEN", vehicle_types=["BIKE"],
        prices=[{"unit": "HOURLY", "amount": "20.00"}],
    )

    async def search(**params):
        response = await client.get("/api/v1/parking", params=params)
        assert response.status_code == 200, response.text
        return response.json()

    by_vehicle = await search(vehicle_type="BIKE")
    assert [item["title"] for item in by_vehicle["items"]] == ["Open bike park"]

    by_type = await search(parking_type="COVERED")
    assert [item["title"] for item in by_type["items"]] == ["Covered car park"]

    by_price = await search(unit="HOURLY", max_price=50)
    assert [item["title"] for item in by_price["items"]] == ["Open bike park"]

    by_text = await search(q="bike")
    assert [item["title"] for item in by_text["items"]] == ["Open bike park"]

    cheapest_first = await search(unit="HOURLY", sort="price_asc")
    assert [item["title"] for item in cheapest_first["items"]] == ["Open bike park", "Covered car park"]


async def test_search_respects_opening_hours(client, provider):
    """Principle 4 — a space closed at that hour must not appear as available."""
    await create_listing(provider, rules=ALL_WEEK_8_TO_20)

    open_hours = await client.get(
        "/api/v1/parking",
        params={"start_at": at(7, 10).isoformat(), "end_at": at(7, 12).isoformat(), "unit": "HOURLY"},
    )
    assert open_hours.json()["total"] == 1

    closed_hours = await client.get(
        "/api/v1/parking",
        params={"start_at": at(7, 6).isoformat(), "end_at": at(7, 7).isoformat(), "unit": "HOURLY"},
    )
    assert closed_hours.json()["total"] == 0


async def test_search_hides_blocked_periods(client, provider):
    space = await create_listing(provider)
    block = await provider.post(
        f"/parking/{space['id']}/blocks",
        json={"start_at": at(7, 0).isoformat(), "end_at": at(8, 0).isoformat(), "reason": "Maintenance"},
    )
    assert block.status_code == 201

    blocked = await client.get(
        "/api/v1/parking",
        params={"start_at": at(7, 10).isoformat(), "end_at": at(7, 12).isoformat(), "unit": "HOURLY"},
    )
    assert blocked.json()["total"] == 0

    # The following day is unaffected.
    free = await client.get(
        "/api/v1/parking",
        params={"start_at": at(9, 10).isoformat(), "end_at": at(9, 12).isoformat(), "unit": "HOURLY"},
    )
    assert free.json()["total"] == 1


async def test_listing_detail_exposes_prices_and_provider(client, provider):
    space = await create_listing(
        provider,
        prices=[{"unit": "HOURLY", "amount": "50.00"}, {"unit": "DAILY", "amount": "300.00"}],
    )
    detail = await client.get(f"/api/v1/parking/{space['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert {price["unit"] for price in body["prices"]} == {"HOURLY", "DAILY"}
    assert body["provider"]["display_name"] == "Pravin Provider"
    # Trust without oversharing: no email, no phone, no address of the person.
    assert "email" not in body["provider"]
    assert "phone" not in body["provider"]


async def test_publishing_requires_price_and_availability(provider):
    response = await provider.post(
        "/parking",
        json={
            "title": "Half-finished listing",
            "parking_type": "OPEN",
            "vehicle_types": ["CAR"],
            "address_line": "12 Ashram Road",
            "city": "Ahmedabad",
            "latitude": 23.02,
            "longitude": 72.57,
            "authority_confirmed": True,
            "prices": [{"unit": "HOURLY", "amount": "50.00"}],
        },
    )
    space = response.json()
    # No availability set yet.
    blocked = await provider.post(f"/parking/{space['id']}/publish")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "AVAILABILITY_REQUIRED"

    await provider.put(f"/parking/{space['id']}/availability", json={"rules": ALL_WEEK_FULL})
    assert (await provider.post(f"/parking/{space['id']}/publish")).status_code == 200


async def test_overlapping_availability_rules_are_rejected(provider):
    space = await create_listing(provider, publish=False)
    response = await provider.put(
        f"/parking/{space['id']}/availability",
        json={
            "rules": [
                {"day_of_week": 0, "start_minute": 480, "end_minute": 720},
                {"day_of_week": 0, "start_minute": 600, "end_minute": 900},
            ]
        },
    )
    assert response.status_code == 422


async def test_paused_listing_leaves_search(client, provider):
    space = await create_listing(provider)
    assert (await provider.post(f"/parking/{space['id']}/pause")).status_code == 200
    assert (await client.get(f"/api/v1/parking/{space['id']}")).status_code == 404
    assert (await client.get("/api/v1/parking")).json()["total"] == 0


async def test_listing_with_bookings_cannot_be_deleted(provider, renter):
    space = await create_listing(provider)
    vehicle = await add_vehicle(renter)
    booking = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "HOURLY",
            "start_at": at(7, 10).isoformat(),
            "end_at": at(7, 12).isoformat(),
        },
    )
    assert booking.status_code == 201
    response = await provider.delete(f"/parking/{space['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HAS_BOOKINGS"


async def test_vehicle_management(renter):
    first = await add_vehicle(renter, registration="gj-01 ab 1234")
    # Registration numbers are normalised to one canonical form.
    assert first["registration_number"] == "GJ01AB1234"
    assert first["is_default"] is True

    duplicate = await renter.post(
        "/vehicles", json={"vehicle_type": "CAR", "registration_number": "GJ01AB1234"}
    )
    assert duplicate.status_code == 409

    second = await add_vehicle(renter, vehicle_type="BIKE", registration="GJ01CD5678")
    assert second["is_default"] is False

    promoted = await renter.patch(f"/vehicles/{second['id']}", json={"is_default": True})
    assert promoted.json()["is_default"] is True
    listing = (await renter.get("/vehicles")).json()
    assert [v["id"] for v in listing][0] == second["id"]
    assert sum(1 for v in listing if v["is_default"]) == 1


async def test_vehicle_type_must_be_supported_by_the_space(provider, renter):
    space = await create_listing(provider, vehicle_types=["CAR"])
    bike = await add_vehicle(renter, vehicle_type="BIKE", registration="GJ01BK1111")
    response = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": bike["id"],
            "unit": "HOURLY",
            "start_at": at(7, 10).isoformat(),
            "end_at": at(7, 12).isoformat(),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VEHICLE_NOT_SUPPORTED"


async def test_calendar_shows_open_and_blocked_days(provider):
    space = await create_listing(provider, rules=ALL_WEEK_8_TO_20)
    day = at(7, 0).date()
    await provider.post(
        f"/parking/{space['id']}/blocks",
        json={"start_at": at(7, 0).isoformat(), "end_at": at(8, 0).isoformat()},
    )
    calendar = await provider.get(
        f"/parking/{space['id']}/calendar",
        params={"from_date": day.isoformat(), "to_date": (day).isoformat()},
    )
    assert calendar.status_code == 200
    entry = calendar.json()["days"][0]
    assert entry["blocked"] is True
    assert entry["is_open"] is False
    assert entry["windows"] == [[480, 1200]]

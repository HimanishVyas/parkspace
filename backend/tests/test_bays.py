"""Named bays: the renter picks the spot instead of being assigned one.

The concurrency guarantee is the same exclusion constraint as before — these
tests exist to prove that picking a bay rides on it rather than around it.
"""
import asyncio

from tests.conftest import ALL_WEEK_8_TO_20, add_vehicle, at, create_listing, register


async def multi_bay_listing(provider, slots=6, **kw):
    return await create_listing(
        provider, total_slots=slots, rules=ALL_WEEK_8_TO_20, title="Society visitor bays", **kw
    )


async def book(user, space_id, vehicle_id, hour=10, slot_index=None, hours=2):
    payload = {
        "parking_space_id": space_id,
        "vehicle_id": vehicle_id,
        "unit": "HOURLY",
        "start_at": at(7, hour).isoformat(),
        "end_at": at(7, hour + hours).isoformat(),
    }
    if slot_index is not None:
        payload["slot_index"] = slot_index
    return await user.post("/bookings", json=payload)


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #


async def test_bays_are_created_with_the_listing(client, provider):
    space = await multi_bay_listing(provider, slots=8)
    layout = (await client.get(f"/api/v1/parking/{space['id']}/bays")).json()
    assert layout["total_slots"] == 8
    assert [b["slot_index"] for b in layout["bays"]] == list(range(8))
    # Rows of six, so the ninth bay would start a new row.
    assert [b["label"] for b in layout["bays"]] == [
        "A-1", "A-2", "A-3", "A-4", "A-5", "A-6", "B-1", "B-2",
    ]
    assert layout["bays"][6]["row_index"] == 1
    assert layout["bays"][6]["col_index"] == 0


async def test_growing_a_listing_keeps_existing_bay_names(provider, client):
    space = await multi_bay_listing(provider, slots=3)
    await provider.put(f"/parking/{space['id']}/bays", json={"labels": {"0": "Gate side"}})
    await provider.patch(f"/parking/{space['id']}", json={"total_slots": 5})

    layout = (await client.get(f"/api/v1/parking/{space['id']}/bays")).json()
    assert layout["total_slots"] == 5
    assert layout["bays"][0]["label"] == "Gate side", "a renamed bay must survive a resize"
    assert layout["bays"][4]["label"] == "A-5"


async def test_provider_can_rename_and_deactivate_a_bay(provider, client):
    space = await multi_bay_listing(provider, slots=4)
    renamed = (
        await provider.put(f"/parking/{space['id']}/bays", json={"labels": {"2": "Near the lift"}})
    ).json()
    assert [b for b in renamed if b["slot_index"] == 2][0]["label"] == "Near the lift"

    await provider.post(f"/parking/{space['id']}/bays/3/active", json={"is_active": False})
    layout = (await client.get(f"/api/v1/parking/{space['id']}/bays")).json()
    assert layout["bays"][3]["is_active"] is False


async def test_duplicate_bay_names_are_refused(provider):
    space = await multi_bay_listing(provider, slots=3)
    clash = await provider.put(
        f"/parking/{space['id']}/bays", json={"labels": {"0": "Same", "1": "same"}}
    )
    assert clash.status_code == 422, clash.text


# --------------------------------------------------------------------------- #
# Picking one
# --------------------------------------------------------------------------- #


async def test_renter_can_pick_a_bay(provider, renter):
    space = await multi_bay_listing(provider)
    vehicle = await add_vehicle(renter, registration="GJ01BY0001")
    created = await book(renter, space["id"], vehicle["id"], slot_index=3)
    assert created.status_code == 201, created.text
    assert created.json()["bay_label"] == "A-4"


async def test_layout_reports_which_bays_are_taken(provider, renter, client):
    space = await multi_bay_listing(provider)
    vehicle = await add_vehicle(renter, registration="GJ01BY0002")
    assert (await book(renter, space["id"], vehicle["id"], slot_index=2)).status_code == 201

    layout = (
        await client.get(
            f"/api/v1/parking/{space['id']}/bays",
            params={"start_at": at(7, 10).isoformat(), "end_at": at(7, 12).isoformat()},
        )
    ).json()
    taken = [b["slot_index"] for b in layout["bays"] if b["taken"]]
    assert taken == [2]


async def test_a_taken_bay_is_refused_rather_than_swapped(client, provider, renter):
    """The whole point of choosing. Somebody who picked the bay by the lift must
    not be quietly moved to the far corner and find out on arrival."""
    space = await multi_bay_listing(provider)
    first_vehicle = await add_vehicle(renter, registration="GJ01BY0003")
    assert (await book(renter, space["id"], first_vehicle["id"], slot_index=1)).status_code == 201

    second = await register(client, full_name="Second Renter")
    second_vehicle = await add_vehicle(second, registration="GJ01BY0004")
    clash = await book(second, space["id"], second_vehicle["id"], slot_index=1)
    assert clash.status_code == 409, clash.text
    assert clash.json()["error"]["code"] == "ALREADY_BOOKED"


async def test_without_a_choice_the_server_still_assigns_one(provider, renter):
    """The original behaviour has to keep working for anyone who does not care."""
    space = await multi_bay_listing(provider)
    vehicle = await add_vehicle(renter, registration="GJ01BY0005")
    created = await book(renter, space["id"], vehicle["id"])
    assert created.status_code == 201, created.text
    assert created.json()["bay_label"] == "A-1"


async def test_an_out_of_service_bay_cannot_be_booked(provider, renter):
    space = await multi_bay_listing(provider)
    await provider.post(f"/parking/{space['id']}/bays/4/active", json={"is_active": False})
    vehicle = await add_vehicle(renter, registration="GJ01BY0006")
    refused = await book(renter, space["id"], vehicle["id"], slot_index=4)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "BAY_INACTIVE"


async def test_a_bay_that_does_not_exist_is_refused(provider, renter):
    space = await multi_bay_listing(provider, slots=4)
    vehicle = await add_vehicle(renter, registration="GJ01BY0007")
    refused = await book(renter, space["id"], vehicle["id"], slot_index=99)
    assert refused.status_code == 422, refused.text


async def test_two_renters_racing_for_one_bay_produce_one_booking(client, provider):
    """Choosing a bay must ride on the exclusion constraint, not around it."""
    space = await multi_bay_listing(provider)
    racers = []
    for i in range(6):
        user = await register(client, full_name=f"Racer {i}")
        vehicle = await add_vehicle(user, registration=f"GJ01RC{i:04d}")
        racers.append((user, vehicle))

    results = await asyncio.gather(
        *[book(user, space["id"], vehicle["id"], slot_index=5) for user, vehicle in racers]
    )
    created = [r for r in results if r.status_code == 201]
    clashed = [r for r in results if r.status_code == 409]
    assert len(created) == 1, f"expected exactly one winner, got {len(created)}"
    assert len(clashed) == len(racers) - 1
    assert created[0].json()["bay_label"] == "A-6"

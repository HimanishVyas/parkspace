"""Role and ownership enforcement (PRD §34) — server-side, never trusting the client."""
from tests.conftest import add_vehicle, at, create_listing, register


async def test_renter_cannot_create_a_listing(renter):
    response = await renter.post(
        "/parking",
        json={
            "title": "Sneaky listing",
            "parking_type": "OPEN",
            "vehicle_types": ["CAR"],
            "address_line": "Somewhere nice",
            "city": "Ahmedabad",
            "latitude": 23.02,
            "longitude": 72.57,
            "authority_confirmed": True,
            "prices": [{"unit": "HOURLY", "amount": "50.00"}],
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NO_PROVIDER_PROFILE"


async def test_provider_cannot_touch_another_providers_listing(client, provider):
    space = await create_listing(provider)
    intruder = await register(client, full_name="Nosy Provider", role="PROVIDER")

    assert (await intruder.patch(f"/parking/{space['id']}", json={"title": "Mine now"})).status_code == 403
    assert (await intruder.delete(f"/parking/{space['id']}")).status_code == 403
    assert (await intruder.post(f"/parking/{space['id']}/pause")).status_code == 403
    assert (
        await intruder.put(f"/parking/{space['id']}/availability", json={"rules": []})
    ).status_code == 403
    assert (await intruder.get(f"/parking/{space['id']}/calendar")).status_code == 403


async def test_renter_cannot_see_another_renters_booking(client, provider, renter):
    space = await create_listing(provider)
    vehicle = await add_vehicle(renter)
    booking = (
        await renter.post(
            "/bookings",
            json={
                "parking_space_id": space["id"],
                "vehicle_id": vehicle["id"],
                "unit": "HOURLY",
                "start_at": at(7, 10).isoformat(),
                "end_at": at(7, 12).isoformat(),
            },
        )
    ).json()

    stranger = await register(client, full_name="Curious Stranger")
    # A 404 rather than a 403: a stranger shouldn't learn the booking exists.
    assert (await stranger.get(f"/bookings/{booking['id']}")).status_code == 404
    assert (await stranger.post(f"/bookings/{booking['id']}/cancel", json={})).status_code == 404


async def test_renter_cannot_book_with_someone_elses_vehicle(client, provider, renter):
    space = await create_listing(provider)
    other = await register(client, full_name="Vehicle Owner")
    their_vehicle = await add_vehicle(other, registration="GJ03OW1111")

    response = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": their_vehicle["id"],
            "unit": "HOURLY",
            "start_at": at(7, 10).isoformat(),
            "end_at": at(7, 12).isoformat(),
        },
    )
    assert response.status_code == 404


async def test_provider_cannot_book_their_own_space(provider):
    space = await create_listing(provider)
    vehicle = await add_vehicle(provider, registration="GJ04SF2222")
    response = await provider.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "HOURLY",
            "start_at": at(7, 10).isoformat(),
            "end_at": at(7, 12).isoformat(),
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "OWN_LISTING"


async def test_non_admin_cannot_reach_admin_endpoints(renter, provider):
    for user in (renter, provider):
        assert (await user.get("/admin/dashboard")).status_code == 403
        assert (await user.get("/admin/users")).status_code == 403
        assert (await user.get("/admin/settings")).status_code == 403
        assert (await user.patch("/admin/settings", json={"commission_percent": 0})).status_code == 403


async def test_admin_can_reach_admin_endpoints(admin):
    assert (await admin.get("/admin/dashboard")).status_code == 200
    assert (await admin.get("/admin/users")).status_code == 200


async def test_suspended_user_is_locked_out(admin, renter):
    assert (await renter.get("/me")).status_code == 200
    suspend = await admin.post(f"/admin/users/{renter.id}/status", json={"status": "SUSPENDED"})
    assert suspend.status_code == 200
    # Suspension takes effect at once, not when the token expires.
    response = await renter.get("/me")
    assert response.status_code in (401, 403)


async def test_suspended_provider_listings_leave_search(client, admin, provider):
    space = await create_listing(provider)
    found = await client.get("/api/v1/parking", params={"latitude": 23.0225, "longitude": 72.5714})
    assert found.json()["total"] == 1

    provider_profile = (await provider.get("/providers/me")).json()
    suspend = await admin.post(
        f"/admin/providers/{provider_profile['id']}/status",
        json={"status": "SUSPENDED", "reason": "Under review"},
    )
    assert suspend.status_code == 200

    gone = await client.get("/api/v1/parking", params={"latitude": 23.0225, "longitude": 72.5714})
    assert gone.json()["total"] == 0
    assert (await client.get(f"/api/v1/parking/{space['id']}")).status_code == 404


async def test_draft_listing_is_not_publicly_visible(client, provider):
    space = await create_listing(provider, publish=False)
    assert (await client.get(f"/api/v1/parking/{space['id']}")).status_code == 404
    search = await client.get("/api/v1/parking", params={"latitude": 23.0225, "longitude": 72.5714})
    assert search.json()["total"] == 0


async def test_access_instructions_hidden_until_confirmed(client, provider, renter):
    """Principle 2 — the gate code is not public information."""
    space = await create_listing(provider)
    public = await client.get(f"/api/v1/parking/{space['id']}")
    assert public.status_code == 200
    assert "access_instructions" not in public.json()

    vehicle = await add_vehicle(renter)
    booking = (
        await renter.post(
            "/bookings",
            json={
                "parking_space_id": space["id"],
                "vehicle_id": vehicle["id"],
                "unit": "HOURLY",
                "start_at": at(7, 10).isoformat(),
                "end_at": at(7, 12).isoformat(),
            },
        )
    ).json()
    assert booking["access_instructions"] is None

    confirmation = await renter.get(f"/bookings/{booking['id']}/confirmation")
    assert confirmation.json()["parking_instructions"] is None


async def test_provider_endpoints_reject_renters(renter):
    assert (await renter.get("/providers/me")).status_code == 403
    assert (await renter.get("/providers/dashboard")).status_code == 403
    assert (await renter.get("/providers/earnings")).status_code == 403
    assert (await renter.get("/parking/mine")).status_code == 403


async def test_individual_provider_has_no_society_profile(provider):
    assert (await provider.get("/providers/me/society")).status_code == 403

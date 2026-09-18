"""PRD §47 — the mandatory end-to-end acceptance scenario.

Provider lists a space at Rs 50/hour, open 8 AM-8 PM. A renter finds it,
books 10 AM-1 PM, pays Rs 150 plus fees and gets a confirmation. The provider
sees the booking, the renter's vehicle, and the slot blocked. A second renter
trying 11 AM-12 PM is refused.
"""
from decimal import Decimal

import pytest

from tests.conftest import ALL_WEEK_8_TO_20, add_vehicle, at, create_listing, pay_for, register


async def test_full_booking_journey(client, provider, renter):
    # --- Provider: register, list, price, set hours, publish --------------- #
    space = await create_listing(
        provider,
        title="Gated parking near Ashram Road",
        prices=[{"unit": "HOURLY", "amount": "50.00"}],
        rules=ALL_WEEK_8_TO_20,
    )
    assert space["status"] == "PUBLISHED"

    # --- Renter: search the provider's location and find it ---------------- #
    start_at = at(7, 10)
    end_at = at(7, 13)
    search = await client.get(
        "/api/v1/parking",
        params={
            "latitude": 23.0225,
            "longitude": 72.5714,
            "radius_km": 5,
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "unit": "HOURLY",
            "vehicle_type": "CAR",
        },
    )
    assert search.status_code == 200, search.text
    results = search.json()
    assert results["total"] == 1
    assert results["items"][0]["id"] == space["id"]
    assert results["items"][0]["distance_km"] < 0.1

    # --- Renter: price the 10 AM-1 PM window ------------------------------- #
    vehicle = await add_vehicle(renter)
    quote = await renter.post(
        "/bookings/quote",
        json={
            "parking_space_id": space["id"],
            "unit": "HOURLY",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        },
    )
    assert quote.status_code == 200, quote.text
    priced = quote.json()
    # 3 hours at Rs 50 = Rs 150 base, plus the configured platform fee and tax.
    assert Decimal(priced["base_amount"]) == Decimal("150.00")
    assert Decimal(priced["platform_fee"]) == Decimal("7.50")   # 5% of 150
    assert Decimal(priced["tax_amount"]) == Decimal("1.35")     # 18% of 7.50
    assert Decimal(priced["total_amount"]) == Decimal("158.85")
    assert priced["available"] is True

    # --- Renter: book and pay ---------------------------------------------- #
    created = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "HOURLY",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    booking = created.json()
    assert booking["status"] == "PENDING_PAYMENT"
    assert Decimal(booking["total_amount"]) == Decimal("158.85")
    # Instructions stay hidden until the booking is paid for.
    assert booking["access_instructions"] is None

    paid = await pay_for(renter, booking["id"])
    assert paid["status"] == "CONFIRMED"
    assert paid["access_instructions"] == "Enter through the left gate. Space A-12."

    # --- Renter: sees the confirmation and the booking in their dashboard -- #
    confirmation = await renter.get(f"/bookings/{booking['id']}/confirmation")
    assert confirmation.status_code == 200
    ticket = confirmation.json()
    assert ticket["reference"] == booking["reference"]
    assert ticket["vehicle_number"] == "GJ01AB1234"
    assert ticket["parking_instructions"] == "Enter through the left gate. Space A-12."
    assert ticket["qr_payload"] == f"PARKSPACE:{booking['reference']}"

    mine = await renter.get("/bookings", params={"scope": "upcoming"})
    assert mine.status_code == 200
    assert [b["id"] for b in mine.json()["items"]] == [booking["id"]]

    # --- Provider: sees the booking, the renter and the vehicle ------------ #
    provider_view = await provider.get("/bookings", params={"role": "provider"})
    assert provider_view.status_code == 200
    provider_bookings = provider_view.json()["items"]
    assert len(provider_bookings) == 1
    assert provider_bookings[0]["renter"]["full_name"] == "Riya Renter"
    assert provider_bookings[0]["vehicle_number"] == "GJ01AB1234"
    # Provider earns the base price minus the 15% commission.
    assert Decimal(provider_bookings[0]["provider_earning"]) == Decimal("127.50")

    # --- Provider: the 10 AM-1 PM period is blocked on the calendar -------- #
    day = start_at.date()
    calendar = await provider.get(
        f"/parking/{space['id']}/calendar",
        params={"from_date": day.isoformat(), "to_date": day.isoformat()},
    )
    assert calendar.status_code == 200
    booked_day = calendar.json()["days"][0]
    assert booked_day["booked_slots"] == 1
    assert booked_day["is_open"] is False

    # --- Second renter: 11 AM-12 PM must be refused ------------------------ #
    second = await register(client, full_name="Sam Second")
    second_vehicle = await add_vehicle(second, registration="GJ01ZZ9999")
    clash = await second.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": second_vehicle["id"],
            "unit": "HOURLY",
            "start_at": at(7, 11).isoformat(),
            "end_at": at(7, 12).isoformat(),
        },
    )
    assert clash.status_code == 409, clash.text
    assert clash.json()["error"]["code"] == "ALREADY_BOOKED"

    # And the search no longer offers it for that window.
    search_again = await client.get(
        "/api/v1/parking",
        params={
            "latitude": 23.0225,
            "longitude": 72.5714,
            "start_at": at(7, 11).isoformat(),
            "end_at": at(7, 12).isoformat(),
            "unit": "HOURLY",
        },
    )
    assert search_again.json()["total"] == 0

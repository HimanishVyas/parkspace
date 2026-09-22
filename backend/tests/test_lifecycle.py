"""Booking lifecycle driven by the clock: holds, activation, completion, reviews."""
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, update

from app.core.time import utcnow
from app.modules.bookings.maintenance import run_once
from app.modules.bookings.models import Booking, BookingStatus
from tests.conftest import ALL_WEEK_FULL, add_vehicle, at, create_listing, pay_for, register


async def _book(user, space_id, vehicle_id, start_hour=10, end_hour=13, day=7):
    response = await user.post(
        "/bookings",
        json={
            "parking_space_id": space_id,
            "vehicle_id": vehicle_id,
            "unit": "HOURLY",
            "start_at": at(day, start_hour).isoformat(),
            "end_at": at(day, end_hour).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_unpaid_hold_expires_and_frees_the_slot(client, db, provider, renter):
    space = await create_listing(provider)
    vehicle = await add_vehicle(renter)
    booking = await _book(renter, space["id"], vehicle["id"])

    # Wind the hold back into the past rather than waiting 15 minutes.
    await db.execute(
        update(Booking).where(Booking.id == booking["id"]).values(hold_expires_at=utcnow() - timedelta(minutes=1))
    )
    await db.commit()

    counts = await run_once(db)
    assert counts["expired"] == 1

    assert (await renter.get(f"/bookings/{booking['id']}")).json()["status"] == "EXPIRED"

    # The slot is available again.
    other = await register(client, full_name="Waiting Renter")
    other_vehicle = await add_vehicle(other, registration="GJ08WT3333")
    assert await _book(other, space["id"], other_vehicle["id"])


async def test_paid_booking_survives_the_hold_sweep(db, provider, renter):
    space = await create_listing(provider)
    vehicle = await add_vehicle(renter)
    booking = await _book(renter, space["id"], vehicle["id"])
    await pay_for(renter, booking["id"])

    await run_once(db)
    assert (await renter.get(f"/bookings/{booking['id']}")).json()["status"] == "CONFIRMED"


async def test_booking_activates_then_completes(db, provider, renter):
    space = await create_listing(provider, rules=ALL_WEEK_FULL)
    vehicle = await add_vehicle(renter)
    booking = await _book(renter, space["id"], vehicle["id"])
    await pay_for(renter, booking["id"])

    now = utcnow()
    # Pretend the booking window has just opened.
    await db.execute(
        update(Booking)
        .where(Booking.id == booking["id"])
        .values(start_at=now - timedelta(minutes=5), end_at=now + timedelta(hours=1))
    )
    await db.commit()
    counts = await run_once(db)
    assert counts["activated"] == 1
    assert (await renter.get(f"/bookings/{booking['id']}")).json()["status"] == "ACTIVE"

    # ...and now that it has passed. The sweep leaves an ACTIVE booking alone:
    # with no exit sensor, a booking nobody closed out means a car still in the
    # bay. Completing it here would also always beat the meter, since the sweep
    # runs every minute — see test_overstay.py.
    await db.execute(
        update(Booking)
        .where(Booking.id == booking["id"])
        .values(start_at=now - timedelta(hours=2), end_at=now - timedelta(minutes=2))
    )
    await db.commit()
    counts = await run_once(db)
    assert counts["completed"] == 0
    assert (await renter.get(f"/bookings/{booking['id']}")).json()["status"] == "ACTIVE"

    # The renter closing it out themselves is what completes it, and costs
    # nothing inside the grace period.
    done = await renter.post(f"/bookings/{booking['id']}/end")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "COMPLETED"


async def test_a_booking_left_running_past_grace_becomes_an_overstay(db, provider, renter):
    """The lifecycle change that came with overstay billing: an ACTIVE booking
    well past its end is no longer closed out for free."""
    space = await create_listing(provider, rules=ALL_WEEK_FULL)
    vehicle = await add_vehicle(renter, registration="GJ01LC0099")
    booking = await _book(renter, space["id"], vehicle["id"])
    await pay_for(renter, booking["id"])

    now = utcnow()
    await db.execute(
        update(Booking)
        .where(Booking.id == booking["id"])
        .values(
            status="ACTIVE",
            start_at=now - timedelta(hours=3),
            end_at=now - timedelta(hours=1),
        )
    )
    await db.commit()
    counts = await run_once(db)
    assert counts["overstaying"] == 1
    assert counts["completed"] == 0
    assert (await renter.get(f"/bookings/{booking['id']}")).json()["status"] == "OVERSTAYING"


async def test_completion_moves_money_into_earnings(db, provider, renter):
    space = await create_listing(provider, rules=ALL_WEEK_FULL)
    vehicle = await add_vehicle(renter)
    booking = await _book(renter, space["id"], vehicle["id"])
    await pay_for(renter, booking["id"])

    before = (await provider.get("/providers/earnings")).json()
    assert Decimal(before["total_earnings"]) == Decimal("0.00")
    assert Decimal(before["upcoming_earnings"]) == Decimal("127.50")

    now = utcnow()
    await db.execute(
        update(Booking)
        .where(Booking.id == booking["id"])
        .values(start_at=now - timedelta(hours=3), end_at=now - timedelta(hours=1))
    )
    await db.commit()
    await run_once(db)

    after = (await provider.get("/providers/earnings")).json()
    assert Decimal(after["total_earnings"]) == Decimal("127.50")
    assert Decimal(after["pending_payout"]) == Decimal("127.50")


async def test_reminder_is_sent_once(db, provider, renter):
    space = await create_listing(provider, rules=ALL_WEEK_FULL)
    vehicle = await add_vehicle(renter)
    booking = await _book(renter, space["id"], vehicle["id"])
    await pay_for(renter, booking["id"])

    now = utcnow()
    await db.execute(
        update(Booking)
        .where(Booking.id == booking["id"])
        .values(start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=3))
    )
    await db.commit()

    assert (await run_once(db))["reminders"] == 1
    # A second pass must not send it again.
    assert (await run_once(db))["reminders"] == 0

    notifications = (await renter.get("/notifications")).json()
    events = [n["event"] for n in notifications["items"]]
    assert "BOOKING_REMINDER" in events


async def test_maintenance_is_safe_to_run_on_an_empty_database(db):
    assert await run_once(db) == {
        "expired": 0,
        "activated": 0,
        "overstaying": 0,
        "completed": 0,
        "reminders": 0,
    }


async def test_manual_approval_flow(db, provider, renter):
    space = await create_listing(provider, requires_approval=True)
    vehicle = await add_vehicle(renter)
    booking = await _book(renter, space["id"], vehicle["id"])
    assert booking["status"] == "PENDING_APPROVAL"

    # The renter cannot pay before the provider accepts.
    early = await renter.post("/payments/create", json={"booking_id": booking["id"]})
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "AWAITING_APPROVAL"

    approved = await provider.post(f"/bookings/{booking['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "PENDING_PAYMENT"

    paid = await pay_for(renter, booking["id"])
    assert paid["status"] == "CONFIRMED"


async def test_provider_can_reject_a_request(client, provider, renter):
    space = await create_listing(provider, requires_approval=True)
    vehicle = await add_vehicle(renter)
    booking = await _book(renter, space["id"], vehicle["id"])

    rejected = await provider.post(
        f"/bookings/{booking['id']}/reject", json={"reason": "Space is being resurfaced"}
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"

    # A rejected booking no longer blocks the slot.
    other = await register(client, full_name="Next In Line")
    other_vehicle = await add_vehicle(other, registration="GJ06NL4444")
    assert await _book(other, space["id"], other_vehicle["id"])


async def test_review_requires_a_completed_booking(db, provider, renter):
    space = await create_listing(provider, rules=ALL_WEEK_FULL)
    vehicle = await add_vehicle(renter)
    booking = await _book(renter, space["id"], vehicle["id"])
    await pay_for(renter, booking["id"])

    too_early = await renter.post("/reviews", json={"booking_id": booking["id"], "rating": 5})
    assert too_early.status_code == 409
    assert too_early.json()["error"]["code"] == "NOT_REVIEWABLE"

    now = utcnow()
    await db.execute(
        update(Booking)
        .where(Booking.id == booking["id"])
        .values(start_at=now - timedelta(hours=3), end_at=now - timedelta(hours=1))
    )
    await db.commit()
    await run_once(db)

    review = await renter.post(
        "/reviews", json={"booking_id": booking["id"], "rating": 5, "comment": "Easy to find, clean."}
    )
    assert review.status_code == 201, review.text
    assert review.json()["subject"] == "SPACE"
    assert review.json()["author_name"] == "Riya R."

    # The listing's rating is updated for search and listing pages.
    summary = await renter.get(f"/reviews/space/{space['id']}")
    assert summary.json()["count"] == 1
    assert Decimal(summary.json()["average"]) == Decimal("5.00")

    # One review per booking per direction.
    duplicate = await renter.post("/reviews", json={"booking_id": booking["id"], "rating": 1})
    assert duplicate.status_code == 409

    # The provider can rate the renter on the same booking.
    provider_review = await provider.post(
        "/reviews", json={"booking_id": booking["id"], "rating": 4, "comment": "Parked neatly."}
    )
    assert provider_review.status_code == 201
    assert provider_review.json()["subject"] == "RENTER"


async def test_issue_report_flags_the_booking(db, provider, renter, admin):
    space = await create_listing(provider, rules=ALL_WEEK_FULL)
    vehicle = await add_vehicle(renter)
    booking = await _book(renter, space["id"], vehicle["id"])
    await pay_for(renter, booking["id"])

    report = await renter.post(
        "/reports",
        json={
            "booking_id": booking["id"],
            "issue_type": "SPACE_OCCUPIED",
            "description": "Another car was parked in the bay when I arrived.",
        },
    )
    assert report.status_code == 201, report.text
    report_id = report.json()["id"]
    assert (await renter.get(f"/bookings/{booking['id']}")).json()["status"] == "DISPUTED"

    queue = await admin.get("/admin/reports", params={"report_status": "OPEN"})
    assert queue.json()["total"] == 1

    resolved = await admin.patch(
        f"/admin/reports/{report_id}",
        json={"status": "RESOLVED", "admin_notes": "Provider refunded the booking."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    # With nothing left open the booking comes out of dispute.
    assert (await renter.get(f"/bookings/{booking['id']}")).json()["status"] in (
        "CONFIRMED",
        "COMPLETED",
    )

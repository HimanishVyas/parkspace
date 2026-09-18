"""Admin marketplace management, configurable settings and the audit trail."""
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import update

from app.core.time import utcnow
from app.modules.bookings.maintenance import run_once
from app.modules.bookings.models import Booking
from tests.conftest import ALL_WEEK_FULL, add_vehicle, at, create_listing, pay_for


async def test_dashboard_counts_the_marketplace(admin, provider, renter):
    await create_listing(provider)
    dashboard = (await admin.get("/admin/dashboard")).json()
    assert dashboard["total_users"] >= 3
    assert dashboard["total_providers"] == 1
    assert dashboard["total_listings"] == 1
    assert dashboard["active_listings"] == 1
    assert dashboard["total_bookings"] == 0


async def test_settings_are_editable_and_take_effect(admin, provider, renter):
    """PRD §10/§15: commission and fees must be configurable, not hard-coded."""
    updated = await admin.patch(
        "/admin/settings", json={"commission_percent": 20, "renter_fee_percent": 0, "tax_percent": 0}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["commission_percent"] == 20

    space = await create_listing(provider)
    vehicle = await add_vehicle(renter)
    quote = await renter.post(
        "/bookings/quote",
        json={
            "parking_space_id": space["id"],
            "unit": "HOURLY",
            "start_at": at(7, 10).isoformat(),
            "end_at": at(7, 13).isoformat(),
        },
    )
    body = quote.json()
    # No renter fee or tax now, so the renter pays exactly the base price.
    assert Decimal(body["total_amount"]) == Decimal("150.00")

    booking = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "HOURLY",
            "start_at": at(7, 10).isoformat(),
            "end_at": at(7, 13).isoformat(),
        },
    )
    assert booking.status_code == 201
    provider_view = await provider.get("/bookings", params={"role": "provider"})
    # 20% commission on 150 leaves 120.
    assert Decimal(provider_view.json()["items"][0]["provider_earning"]) == Decimal("120.00")


async def test_invalid_settings_are_rejected(admin):
    response = await admin.patch("/admin/settings", json={"commission_percent": 150})
    assert response.status_code == 422


async def test_listing_approval_workflow(client, admin, provider):
    """With approval required, a published listing waits for an admin."""
    assert (await admin.patch("/admin/settings", json={"listing_requires_approval": True})).status_code == 200

    space = await create_listing(provider)
    assert space["status"] == "PENDING_APPROVAL"
    assert (await client.get(f"/api/v1/parking/{space['id']}")).status_code == 404

    queue = await admin.get("/admin/listings", params={"listing_status": "PENDING_APPROVAL"})
    assert queue.json()["total"] == 1

    approved = await admin.post(f"/admin/listings/{space['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "PUBLISHED"
    assert (await client.get(f"/api/v1/parking/{space['id']}")).status_code == 200


async def test_listing_rejection_records_a_reason(admin, provider):
    assert (await admin.patch("/admin/settings", json={"listing_requires_approval": True})).status_code == 200
    space = await create_listing(provider)
    rejected = await admin.post(
        f"/admin/listings/{space['id']}/reject", json={"reason": "Photos do not show the space"}
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"

    mine = await provider.get(f"/parking/mine/{space['id']}")
    assert mine.json()["rejection_reason"] == "Photos do not show the space"

    # A rejected listing cannot simply be republished.
    republish = await provider.post(f"/parking/{space['id']}/publish")
    assert republish.status_code == 403


async def test_provider_verification_workflow(admin, provider):
    submitted = await provider.post(
        "/providers/me/verification",
        json={
            "contact_phone": "9876543210",
            "address": "12 Ashram Road, Ahmedabad",
            "authority_declaration": True,
        },
    )
    assert submitted.status_code == 200
    assert submitted.json()["verification_status"] == "PENDING_VERIFICATION"

    provider_id = submitted.json()["id"]
    verified = await admin.post(
        f"/admin/providers/{provider_id}/verification",
        json={"status": "VERIFIED", "notes": "ID and ownership proof checked"},
    )
    assert verified.status_code == 200
    assert verified.json()["verification_status"] == "VERIFIED"

    notifications = (await provider.get("/notifications")).json()
    assert any(n["event"] == "PROVIDER_VERIFICATION" for n in notifications["items"])


async def test_authority_declaration_is_mandatory(provider):
    response = await provider.post(
        "/providers/me/verification",
        json={"contact_phone": "9876543210", "address": "12 Ashram Road", "authority_declaration": False},
    )
    assert response.status_code == 422


async def test_listing_requires_authority_confirmation(provider):
    """PRD §32 — the provider must confirm they may rent the space out."""
    response = await provider.post(
        "/parking",
        json={
            "title": "Unconfirmed space",
            "parking_type": "OPEN",
            "vehicle_types": ["CAR"],
            "address_line": "Somewhere in town",
            "city": "Ahmedabad",
            "latitude": 23.02,
            "longitude": 72.57,
            "authority_confirmed": False,
            "prices": [{"unit": "HOURLY", "amount": "50.00"}],
        },
    )
    assert response.status_code == 422


async def test_admin_can_cancel_a_booking_with_a_full_refund(admin, provider, renter):
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
                "end_at": at(7, 13).isoformat(),
            },
        )
    ).json()
    await pay_for(renter, booking["id"])

    cancelled = await admin.post(
        f"/admin/bookings/{booking['id']}/cancel", json={"reason": "Duplicate charge reported"}
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert Decimal(cancelled.json()["refund_amount"]) == Decimal(booking["total_amount"])


async def test_admin_actions_are_audited(admin, provider, renter):
    await admin.post(f"/admin/users/{renter.id}/status", json={"status": "SUSPENDED", "reason": "Spam"})
    logs = await admin.get("/admin/audit-logs", params={"action": "user.status"})
    assert logs.status_code == 200
    entries = logs.json()
    assert len(entries) == 1
    assert entries[0]["entity_id"] == str(renter.id)
    assert entries[0]["data"]["reason"] == "Spam"
    assert entries[0]["actor_id"] == str(admin.id)


async def test_admin_cannot_suspend_themselves(admin):
    response = await admin.post(f"/admin/users/{admin.id}/status", json={"status": "SUSPENDED"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SELF_ACTION"


async def test_payout_settles_completed_bookings(db, admin, provider, renter):
    space = await create_listing(provider, rules=ALL_WEEK_FULL)
    vehicle = await add_vehicle(renter)
    booking = (
        await renter.post(
            "/bookings",
            json={
                "parking_space_id": space["id"],
                "vehicle_id": vehicle["id"],
                "unit": "HOURLY",
                "start_at": at(7, 10).isoformat(),
                "end_at": at(7, 13).isoformat(),
            },
        )
    ).json()
    await pay_for(renter, booking["id"])

    now = utcnow()
    await db.execute(
        update(Booking)
        .where(Booking.id == booking["id"])
        .values(start_at=now - timedelta(hours=3), end_at=now - timedelta(hours=1))
    )
    await db.commit()
    await run_once(db)

    provider_id = (await provider.get("/providers/me")).json()["id"]
    payout = await admin.post("/admin/payouts", json={"provider_id": provider_id})
    assert payout.status_code == 201, payout.text
    assert Decimal(payout.json()["amount"]) == Decimal("127.50")
    assert payout.json()["booking_count"] == 1

    # A second payout has nothing left to settle.
    again = await admin.post("/admin/payouts", json={"provider_id": provider_id})
    assert again.status_code == 422
    assert again.json()["error"]["code"] == "NOTHING_TO_PAY"

    paid = await admin.post(f"/admin/payouts/{payout.json()['id']}/paid", json={"reference": "UTR12345"})
    assert paid.status_code == 200
    assert paid.json()["status"] == "PAID"

    earnings = (await provider.get("/providers/earnings")).json()
    assert Decimal(earnings["completed_payout"]) == Decimal("127.50")
    assert Decimal(earnings["pending_payout"]) == Decimal("0.00")


async def test_society_agreement_changes_the_revenue_split(client, admin, renter):
    """PRD §30 — an active agreement replaces the default commission."""
    from tests.conftest import register

    society_admin = await register(
        client,
        full_name="Society Admin",
        role="PROVIDER",
        provider_type="SOCIETY",
        organization_name="Green Acres Society",
    )
    profile = (await society_admin.get("/providers/me")).json()
    society_id = profile["society"]["id"]

    agreement = await admin.post(
        f"/admin/societies/{society_id}/agreements",
        json={
            "start_date": (utcnow().date() - timedelta(days=1)).isoformat(),
            "revenue_share_percent": "70.00",
            "parking_space_count": 10,
            "status": "ACTIVE",
        },
    )
    assert agreement.status_code == 201, agreement.text
    activated = await admin.patch(f"/admin/agreements/{agreement.json()['id']}", json={"status": "ACTIVE"})
    assert activated.status_code == 200

    space = await create_listing(society_admin)
    vehicle = await add_vehicle(renter)
    booking = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "HOURLY",
            "start_at": at(7, 10).isoformat(),
            "end_at": at(7, 13).isoformat(),
        },
    )
    assert booking.status_code == 201

    provider_view = await society_admin.get("/bookings", params={"role": "provider"})
    # The society keeps 70% of the Rs 150 base, not the default 85%.
    assert Decimal(provider_view.json()["items"][0]["provider_earning"]) == Decimal("105.00")

    # The society can read its own terms.
    own = await society_admin.get("/providers/me/society/agreements")
    assert own.status_code == 200
    assert Decimal(own.json()[0]["revenue_share_percent"]) == Decimal("70.00")

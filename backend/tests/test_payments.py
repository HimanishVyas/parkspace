"""Payment flow: signature verification, idempotency, webhooks and refunds."""
import hashlib
import hmac
import json
from decimal import Decimal

from app.core.config import settings
from tests.conftest import API, add_vehicle, at, create_listing, pay_for, register


def sign(payload: str) -> str:
    return hmac.new(settings.mock_gateway_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def make_booking(provider, renter, start_hour=10, end_hour=13, **listing_kwargs):
    space = await create_listing(provider, **listing_kwargs)
    vehicle = await add_vehicle(renter, registration=f"GJ01PY{start_hour:04d}")
    response = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "HOURLY",
            "start_at": at(7, start_hour).isoformat(),
            "end_at": at(7, end_hour).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return space, response.json()


async def test_payment_confirms_the_booking(provider, renter):
    _, booking = await make_booking(provider, renter)
    assert booking["status"] == "PENDING_PAYMENT"

    confirmed = await pay_for(renter, booking["id"])
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["confirmed_at"] is not None

    payment = await renter.get(f"/payments/booking/{booking['id']}")
    assert payment.status_code == 200
    assert payment.json()["status"] == "CAPTURED"
    assert Decimal(payment.json()["amount"]) == Decimal(booking["total_amount"])


async def test_forged_signature_is_rejected(provider, renter):
    _, booking = await make_booking(provider, renter)
    session = (await renter.post("/payments/create", json={"booking_id": booking["id"]})).json()

    response = await renter.post(
        "/payments/confirm",
        json={
            "order_id": session["order_id"],
            "payment_id": session["client_payload"]["mock_payment_id"],
            "signature": "f" * 64,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SIGNATURE"

    # The booking is still unpaid — a renter cannot confirm their own payment.
    still = await renter.get(f"/bookings/{booking['id']}")
    assert still.json()["status"] == "PENDING_PAYMENT"


async def test_confirming_twice_is_idempotent(provider, renter):
    _, booking = await make_booking(provider, renter)
    session = (await renter.post("/payments/create", json={"booking_id": booking["id"]})).json()
    order_id = session["order_id"]
    payment_id = session["client_payload"]["mock_payment_id"]
    body = {"order_id": order_id, "payment_id": payment_id, "signature": sign(f"{order_id}|{payment_id}")}

    first = await renter.post("/payments/confirm", json=body)
    second = await renter.post("/payments/confirm", json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "CONFIRMED"


async def test_reopening_checkout_reuses_the_same_order(provider, renter):
    _, booking = await make_booking(provider, renter)
    first = (await renter.post("/payments/create", json={"booking_id": booking["id"]})).json()
    second = (await renter.post("/payments/create", json={"booking_id": booking["id"]})).json()
    assert first["order_id"] == second["order_id"]


async def test_a_confirmed_booking_cannot_be_paid_again(provider, renter):
    _, booking = await make_booking(provider, renter)
    await pay_for(renter, booking["id"])
    response = await renter.post("/payments/create", json={"booking_id": booking["id"]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


async def test_another_user_cannot_pay_for_your_booking(client, provider, renter):
    _, booking = await make_booking(provider, renter)
    intruder = await register(client, full_name="Payment Intruder")
    response = await intruder.post("/payments/create", json={"booking_id": booking["id"]})
    assert response.status_code == 404


async def test_webhook_confirms_a_booking(client, provider, renter):
    """The webhook is authoritative: a renter who closes the tab still gets
    a confirmed booking."""
    _, booking = await make_booking(provider, renter)
    session = (await renter.post("/payments/create", json={"booking_id": booking["id"]})).json()

    payload = json.dumps(
        {
            "event_id": "evt_test_1",
            "event": "payment.captured",
            "order_id": session["order_id"],
            "payment_id": session["client_payload"]["mock_payment_id"],
            "status": "captured",
        }
    ).encode()
    signature = hmac.new(settings.mock_gateway_secret.encode(), payload, hashlib.sha256).hexdigest()

    response = await client.post(
        f"{API}/payments/webhook", content=payload, headers={"x-mock-signature": signature}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "captured"

    updated = await renter.get(f"/bookings/{booking['id']}")
    assert updated.json()["status"] == "CONFIRMED"


async def test_webhook_with_a_bad_signature_is_rejected(client, provider, renter):
    _, booking = await make_booking(provider, renter)
    session = (await renter.post("/payments/create", json={"booking_id": booking["id"]})).json()
    payload = json.dumps({"event_id": "evt_bad", "order_id": session["order_id"]}).encode()

    response = await client.post(
        f"{API}/payments/webhook", content=payload, headers={"x-mock-signature": "deadbeef"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SIGNATURE"
    assert (await renter.get(f"/bookings/{booking['id']}")).json()["status"] == "PENDING_PAYMENT"


async def test_replayed_webhook_is_ignored(client, provider, renter):
    _, booking = await make_booking(provider, renter)
    session = (await renter.post("/payments/create", json={"booking_id": booking["id"]})).json()
    payload = json.dumps(
        {
            "event_id": "evt_replay",
            "event": "payment.captured",
            "order_id": session["order_id"],
            "payment_id": session["client_payload"]["mock_payment_id"],
            "status": "captured",
        }
    ).encode()
    signature = hmac.new(settings.mock_gateway_secret.encode(), payload, hashlib.sha256).hexdigest()
    headers = {"x-mock-signature": signature}

    first = await client.post(f"{API}/payments/webhook", content=payload, headers=headers)
    second = await client.post(f"{API}/payments/webhook", content=payload, headers=headers)
    assert first.json()["status"] == "captured"
    assert second.json()["status"] == "duplicate"


async def test_cancellation_refunds_a_paid_booking(provider, renter, admin):
    """A booking cancelled well ahead of time refunds in full under the default policy."""
    _, booking = await make_booking(provider, renter)
    await pay_for(renter, booking["id"])

    cancelled = await renter.post(f"/bookings/{booking['id']}/cancel", json={"reason": "Changed plans"})
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "CANCELLED"
    # The booking starts 7 days out, so the 100% tier applies.
    assert Decimal(body["refund_amount"]) == Decimal(booking["total_amount"])

    payment = await renter.get(f"/payments/booking/{booking['id']}")
    assert payment.json()["status"] == "REFUNDED"


async def test_unpaid_cancellation_refunds_nothing(provider, renter):
    _, booking = await make_booking(provider, renter)
    cancelled = await renter.post(f"/bookings/{booking['id']}/cancel", json={})
    assert cancelled.status_code == 200
    assert Decimal(cancelled.json()["refund_amount"]) == Decimal("0.00")


async def test_provider_cancellation_refunds_in_full(provider, renter):
    """When the provider pulls out it is not the renter's fault, so the tiered
    policy doesn't apply."""
    _, booking = await make_booking(provider, renter)
    await pay_for(renter, booking["id"])
    cancelled = await provider.post(
        f"/bookings/{booking['id']}/cancel", json={"reason": "Gate under repair"}
    )
    assert cancelled.status_code == 200
    assert Decimal(cancelled.json()["refund_amount"]) == Decimal(booking["total_amount"])


async def test_cancelled_booking_earns_the_provider_nothing(provider, renter):
    _, booking = await make_booking(provider, renter)
    await pay_for(renter, booking["id"])
    await renter.post(f"/bookings/{booking['id']}/cancel", json={})

    earnings = await provider.get("/providers/earnings")
    assert Decimal(earnings.json()["upcoming_earnings"]) == Decimal("0.00")
    assert Decimal(earnings.json()["total_earnings"]) == Decimal("0.00")


async def test_provider_cancelling_an_unpaid_booking_refunds_nothing(provider, renter):
    """Nobody has been charged yet, so no refund should be recorded — otherwise
    the renter is told money is coming back that never left."""
    _, booking = await make_booking(provider, renter, start_hour=14, end_hour=16)
    assert booking["status"] == "PENDING_PAYMENT"

    cancelled = await provider.post(f"/bookings/{booking['id']}/cancel", json={"reason": "Gate repairs"})
    assert cancelled.status_code == 200
    assert Decimal(cancelled.json()["refund_amount"]) == Decimal("0.00")


async def test_admin_cancelling_an_unpaid_booking_refunds_nothing(admin, provider, renter):
    _, booking = await make_booking(provider, renter, start_hour=16, end_hour=18)
    cancelled = await admin.post(f"/admin/bookings/{booking['id']}/cancel", json={"reason": "Duplicate"})
    assert cancelled.status_code == 200
    assert Decimal(cancelled.json()["refund_amount"]) == Decimal("0.00")


async def test_sandbox_complete_pays_without_client_side_crypto(provider, renter):
    """The sandbox shortcut exists because SubtleCrypto is unavailable on a
    non-secure origin, so the browser cannot sign the mock order itself."""
    _, booking = await make_booking(provider, renter, start_hour=14, end_hour=16)
    assert booking["status"] == "PENDING_PAYMENT"

    response = await renter.post("/payments/sandbox/complete", json={"booking_id": booking["id"]})
    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["confirmed_at"] is not None
    # Access details are released by payment, exactly as on the signed path.
    assert confirmed["access_instructions"] is not None

    payment = (await renter.get(f"/payments/booking/{booking['id']}")).json()
    assert payment["status"] == "CAPTURED"


async def test_sandbox_complete_rejects_someone_elses_booking(client, provider, renter):
    _, booking = await make_booking(provider, renter, start_hour=17, end_hour=19)
    intruder = await register(client, full_name="Nosy Neighbour")
    response = await intruder.post("/payments/sandbox/complete", json={"booking_id": booking["id"]})
    assert response.status_code in (403, 404), response.text


async def test_sandbox_complete_is_idempotent(provider, renter):
    _, booking = await make_booking(provider, renter, start_hour=9, end_hour=11)
    first = await renter.post("/payments/sandbox/complete", json={"booking_id": booking["id"]})
    assert first.status_code == 200
    # A double tap on the pay button must not double-charge or error out.
    second = await renter.post("/payments/sandbox/complete", json={"booking_id": booking["id"]})
    assert second.status_code in (200, 409), second.text

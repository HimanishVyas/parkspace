"""Regressions for the production blockers.

Each test here stands in for a way the service could be taken down or taken
advantage of, rather than for a feature. They are grouped by the thing that went
wrong, and each one names the mistake it is holding the line against.
"""
import time
from datetime import timedelta

import pytest

from app.core.config import Settings
from app.core.startup import InsecureConfiguration, collect_problems, verify
from app.modules.availability.models import AvailabilityRule
from app.modules.availability.service import rules_cover_window, weekdays_touched
from app.modules.parking.models import PricingUnit
from tests.conftest import ALL_WEEK_FULL, add_vehicle, at, create_listing

# --------------------------------------------------------------------------- #
# An unbounded window used to be a lever on how much CPU one request could burn
# --------------------------------------------------------------------------- #
OPEN_ALL_WEEK = [
    AvailabilityRule(parking_space_id=None, day_of_week=day, start_minute=0, end_minute=1440, is_active=True)
    for day in range(7)
]


@pytest.mark.parametrize("unit", [PricingUnit.HOURLY, PricingUnit.DAILY, PricingUnit.MONTHLY])
def test_coverage_cost_does_not_grow_with_the_window(unit):
    """This ran once per calendar day in the window.

    An anonymous search with a far-future end date therefore blocked the event
    loop for seconds at a time — measured at 4.9s for a year-3000 end date, with
    /health stalled behind it for the duration. The answer only depends on which
    weekdays the window touches, so it must cost the same however long it is.
    """
    start = at(1, 9)

    def cost(days: int) -> float:
        end = start + timedelta(days=days)
        begin = time.perf_counter()
        for _ in range(200):
            rules_cover_window(OPEN_ALL_WEEK, start, end, unit)
        return time.perf_counter() - begin

    two_days = cost(2)
    thousand_years = cost(365_000)
    # Generous: the point is that it is flat, not that it is equal to the tick.
    assert thousand_years < two_days * 5 + 0.05, (
        f"a 1000-year window cost {thousand_years:.4f}s against {two_days:.4f}s for two days"
    )


def test_weekdays_touched_saturates_at_a_week():
    assert weekdays_touched(at(1, 0).date(), 0) == set()
    assert len(weekdays_touched(at(1, 0).date(), 3)) == 3
    assert weekdays_touched(at(1, 0).date(), 7) == set(range(7))
    assert weekdays_touched(at(1, 0).date(), 365_000) == set(range(7))


async def test_public_search_refuses_an_unbounded_window(client, provider):
    await create_listing(provider, rules=ALL_WEEK_FULL)
    refused = await client.get(
        "/api/v1/parking",
        params={
            "start_at": at(1, 9).isoformat(),
            "end_at": (at(1, 9) + timedelta(days=365_000)).isoformat(),
            "unit": "HOURLY",
        },
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "WINDOW_TOO_LONG"


async def test_quote_refuses_an_unbounded_window(client, provider):
    space = await create_listing(provider, rules=ALL_WEEK_FULL)
    refused = await client.post(
        "/api/v1/bookings/quote",
        json={
            "parking_space_id": space["id"],
            "unit": "HOURLY",
            "start_at": at(1, 9).isoformat(),
            "end_at": (at(1, 9) + timedelta(days=365_000)).isoformat(),
        },
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "WINDOW_TOO_LONG"


async def test_booking_refuses_an_unbounded_window(provider, renter):
    space = await create_listing(provider, rules=ALL_WEEK_FULL)
    vehicle = await add_vehicle(renter, registration="GJ01HD0001")
    refused = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "HOURLY",
            "start_at": at(1, 9).isoformat(),
            "end_at": (at(1, 9) + timedelta(days=365_000)).isoformat(),
        },
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "WINDOW_TOO_LONG"


async def test_an_ordinary_window_is_still_allowed(client, provider):
    space = await create_listing(provider, rules=ALL_WEEK_FULL)
    ok = await client.post(
        "/api/v1/bookings/quote",
        json={
            "parking_space_id": space["id"],
            "unit": "HOURLY",
            "start_at": at(1, 9).isoformat(),
            "end_at": at(1, 12).isoformat(),
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["available"] is True


# --------------------------------------------------------------------------- #
# Configuration that is merely left alone must not be able to reach production
# --------------------------------------------------------------------------- #
def _production(**overrides) -> Settings:
    base = {
        "environment": "production",
        "jwt_secret": "a-real-secret",
        "mock_gateway_secret": "a-real-mock-secret",
        "seed_admin_email": "ops@parkspace.app",
        "seed_admin_password": "a-real-password",
        "payment_gateway": "razorpay",
        "allow_sandbox_payments": False,
        "debug": False,
        "frontend_url": "https://parkspace.app",
        "cors_origins": ["https://parkspace.app"],
    }
    return Settings(**{**base, **overrides})


def test_a_correctly_configured_production_boots():
    assert collect_problems(_production()) == []
    verify(_production())


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"jwt_secret": "change-me-in-env"}, "jwt_secret"),
        ({"seed_admin_password": "admin12345"}, "seed_admin_password"),
        ({"seed_admin_email": "admin@example.com"}, "seed_admin_email"),
        ({"mock_gateway_secret": "mock-gateway-secret"}, "mock_gateway_secret"),
        ({"payment_gateway": "mock"}, "payment_gateway"),
        ({"allow_sandbox_payments": True}, "allow_sandbox_payments"),
        ({"debug": True}, "debug"),
        ({"frontend_url": "http://parkspace.app"}, "frontend_url"),
        ({"cors_origins": ["http://parkspace.app"]}, "cors_origins"),
    ],
)
def test_production_refuses_to_start_on_an_unsafe_default(overrides, expected):
    with pytest.raises(InsecureConfiguration) as raised:
        verify(_production(**overrides))
    assert expected in str(raised.value)


def test_smtp_credentials_without_tls_are_refused():
    with pytest.raises(InsecureConfiguration) as raised:
        verify(_production(email_backend="smtp", smtp_password="hunter2", smtp_tls=False))
    assert "clear text" in str(raised.value)


def test_development_is_warned_about_rather_than_blocked(caplog):
    """A laptop is allowed to be a laptop — but a production deploy that never
    set ENVIRONMENT never reaches the hard check, so the warning is the only
    signal it leaves."""
    settings = _production(environment="development", jwt_secret="change-me-in-env")
    verify(settings)  # must not raise
    assert "not production-safe" in caplog.text


def test_sandbox_completion_is_off_unless_explicitly_allowed():
    """The route exists in this test run because conftest opts in.

    What must not happen is it being reachable on a deploy that simply left the
    defaults alone — so the assertion is on the shipped default itself, not on a
    Settings() that would read this suite's own environment back.
    """
    assert Settings.model_fields["allow_sandbox_payments"].default is False


# --------------------------------------------------------------------------- #
# One maintenance pass at a time, however many processes are running
# --------------------------------------------------------------------------- #
async def test_only_one_worker_runs_a_maintenance_pass(db, provider, renter):
    """Two API processes each run their own maintenance loop.

    `expire_holds` and `activate_started` are single atomic UPDATEs and would
    survive that, but the reminder and completion sweeps select rows and then
    mutate them in Python — so both workers would send the same renter the same
    email and both would stamp `reminder_sent_at`.
    """
    import asyncio

    from app.core.database import SessionLocal
    from app.modules.bookings.maintenance import run_once

    space = await create_listing(provider, rules=ALL_WEEK_FULL)
    vehicle = await add_vehicle(renter, registration="GJ01HD0002")
    created = await renter.post(
        "/bookings",
        json={
            "parking_space_id": space["id"],
            "vehicle_id": vehicle["id"],
            "unit": "HOURLY",
            "start_at": at(1, 9).isoformat(),
            "end_at": at(1, 11).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    from tests.conftest import pay_for

    booking = await pay_for(renter, created.json()["id"])

    # Due for a reminder: inside the reminder horizon and not yet sent.
    from sqlalchemy import func, select, update

    from app.core.time import utcnow
    from app.modules.bookings.models import Booking
    from app.modules.notifications.models import Notification

    await db.execute(
        update(Booking)
        .where(Booking.id == booking["id"])
        .values(start_at=utcnow() + timedelta(minutes=30), end_at=utcnow() + timedelta(hours=2))
    )
    await db.commit()

    async def pass_in_its_own_session():
        async with SessionLocal() as session:
            return await run_once(session)

    results = await asyncio.gather(*(pass_in_its_own_session() for _ in range(4)))

    assert sum(r["reminders"] for r in results) == 1, (
        f"the reminder was claimed by more than one pass: {results}"
    )
    reminders = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.event == "BOOKING_REMINDER")
    )
    assert reminders == 1, "one booking, one reminder notification"

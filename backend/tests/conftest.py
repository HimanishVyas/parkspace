"""Test harness.

Environment is pinned before any application import, because settings are read
once at import time. Tests run against a real PostgreSQL database — the booking
guarantees under test are enforced by PostgreSQL (exclusion constraints,
generated columns), so an in-memory substitute would test something else.
"""
import os
import uuid
from datetime import datetime, timedelta

TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "parking_test")
_BASE_URL = os.environ.get(
    "TEST_DATABASE_URL", f"postgresql+asyncpg://parking:parking@localhost:55432/{TEST_DB_NAME}"
)
os.environ.update(
    DATABASE_URL=_BASE_URL,
    ENVIRONMENT="test",
    DEBUG="false",
    RATE_LIMIT_ENABLED="false",
    MAINTENANCE_ENABLED="false",
    PAYMENT_GATEWAY="mock",
    ALLOW_SANDBOX_PAYMENTS="true",
    MOCK_GATEWAY_SECRET="test-gateway-secret",
    EMAIL_BACKEND="console",
    REDIS_URL="",
    JWT_SECRET="test-jwt-secret-long-enough-for-hs256-0123456789",
    TIMEZONE="Asia/Kolkata",
    MEDIA_ROOT="/tmp/parkspace-test-media",
)

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.time import local_tz  # noqa: E402
from app.db.registry import Base  # noqa: E402
from app.main import create_app  # noqa: E402


async def _ensure_database() -> None:
    """Create the test database if it doesn't exist yet."""
    admin_url = _BASE_URL.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        exists = await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME})
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    await admin_engine.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def database():
    await _ensure_database()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(database):
    """Each test starts from an empty database."""
    yield
    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture(loop_scope="function")
async def db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            # A test that read rows without committing leaves a transaction
            # open, and closing that across the client's event loop raises.
            await session.rollback()


@pytest_asyncio.fixture
async def app():
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
API = "/api/v1"


class ApiUser:
    """A registered account plus the client calls made as that account."""

    def __init__(self, client: AsyncClient, data: dict, password: str):
        self._client = client
        self.password = password
        self.id = uuid.UUID(data["user"]["id"])
        self.email = data["user"]["email"]
        self.token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.role = data["user"]["role"]

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    async def get(self, path, **kwargs):
        return await self._client.get(f"{API}{path}", headers=self.headers, **kwargs)

    async def post(self, path, **kwargs):
        return await self._client.post(f"{API}{path}", headers=self.headers, **kwargs)

    async def patch(self, path, **kwargs):
        return await self._client.patch(f"{API}{path}", headers=self.headers, **kwargs)

    async def put(self, path, **kwargs):
        return await self._client.put(f"{API}{path}", headers=self.headers, **kwargs)

    async def delete(self, path, **kwargs):
        return await self._client.delete(f"{API}{path}", headers=self.headers, **kwargs)


async def register(client: AsyncClient, **overrides) -> ApiUser:
    password = overrides.pop("password", "sup3rsecret")
    payload = {
        "email": overrides.pop("email", f"user-{uuid.uuid4().hex[:10]}@example.com"),
        "password": password,
        "full_name": overrides.pop("full_name", "Test User"),
        **overrides,
    }
    response = await client.post(f"{API}/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return ApiUser(client, response.json(), password)


@pytest_asyncio.fixture
async def renter(client):
    return await register(client, full_name="Riya Renter")


@pytest_asyncio.fixture
async def provider(client):
    return await register(client, full_name="Pravin Provider", role="PROVIDER")


@pytest_asyncio.fixture
async def admin(client, db):
    """Admins are never self-registered, so this promotes a fresh account."""
    from sqlalchemy import update

    from app.modules.users.models import User, UserRole

    user = await register(client, full_name="Ada Admin")
    await db.execute(update(User).where(User.id == user.id).values(role=UserRole.ADMIN))
    await db.commit()
    login = await client.post(
        f"{API}/auth/login", json={"identifier": user.email, "password": user.password}
    )
    assert login.status_code == 200, login.text
    return ApiUser(client, login.json(), user.password)


def local(year, month, day, hour=0, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=local_tz())


def future_date(days: int = 7):
    """A date far enough ahead to clear lead-time rules, with a stable weekday."""
    from app.core.time import utcnow

    return (utcnow().astimezone(local_tz()) + timedelta(days=days)).date()


def at(days_ahead: int, hour: int, minute: int = 0) -> datetime:
    day = future_date(days_ahead)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=local_tz())


ALL_WEEK_8_TO_20 = [
    {"day_of_week": day, "start_minute": 8 * 60, "end_minute": 20 * 60} for day in range(7)
]
ALL_WEEK_FULL = [{"day_of_week": day, "start_minute": 0, "end_minute": 1440} for day in range(7)]


async def create_listing(
    user: ApiUser,
    *,
    prices=None,
    rules=None,
    publish=True,
    latitude=23.0225,
    longitude=72.5714,
    **overrides,
) -> dict:
    """Create (and by default publish) a listing with availability set up."""
    payload = {
        "title": overrides.pop("title", "Covered parking near Metro"),
        "description": "Safe, gated parking.",
        "parking_type": overrides.pop("parking_type", "COVERED"),
        "vehicle_types": overrides.pop("vehicle_types", ["CAR", "SUV"]),
        "address_line": "12 Ashram Road",
        "city": "Ahmedabad",
        "latitude": latitude,
        "longitude": longitude,
        "access_instructions": "Enter through the left gate. Space A-12.",
        "authority_confirmed": True,
        "prices": prices or [{"unit": "HOURLY", "amount": "50.00"}],
        **overrides,
    }
    response = await user.post("/parking", json=payload)
    assert response.status_code == 201, response.text
    space = response.json()

    rules_response = await user.put(
        f"/parking/{space['id']}/availability", json={"rules": rules or ALL_WEEK_8_TO_20}
    )
    assert rules_response.status_code == 200, rules_response.text

    if publish:
        published = await user.post(f"/parking/{space['id']}/publish")
        assert published.status_code == 200, published.text
        space = published.json()
    return space


async def add_vehicle(user: ApiUser, vehicle_type="CAR", registration="GJ01AB1234") -> dict:
    response = await user.post(
        "/vehicles",
        json={"vehicle_type": vehicle_type, "registration_number": registration, "make_model": "Hyundai i20"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def pay_for(user: ApiUser, booking_id: str) -> dict:
    """Drive a booking through the mock gateway end to end."""
    import hashlib
    import hmac

    from app.core.config import settings

    session = await user.post("/payments/create", json={"booking_id": booking_id})
    assert session.status_code == 200, session.text
    payload = session.json()
    order_id = payload["order_id"]
    payment_id = payload["client_payload"]["mock_payment_id"]
    signature = hmac.new(
        settings.mock_gateway_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    confirmed = await user.post(
        "/payments/confirm",
        json={"order_id": order_id, "payment_id": payment_id, "signature": signature},
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()

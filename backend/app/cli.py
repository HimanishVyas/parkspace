"""Operational commands.

    python -m app.cli seed          create the bootstrap admin account
    python -m app.cli demo          seed a small, realistic pilot dataset
    python -m app.cli maintenance   run one booking-maintenance pass
"""
import asyncio
import sys
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.core.time import local_tz, utcnow


async def seed_admin() -> None:
    """Create the bootstrap admin if it doesn't exist. Safe to re-run."""
    from app.modules.users.models import User, UserRole

    async with SessionLocal() as db:
        existing = await db.scalar(select(User).where(User.email == settings.seed_admin_email))
        if existing is not None:
            if existing.role != UserRole.ADMIN:
                existing.role = UserRole.ADMIN
                await db.commit()
                print(f"Promoted {existing.email} to admin")
            else:
                print(f"Admin {existing.email} already exists")
            return
        if settings.environment == "production" and settings.seed_admin_password == "admin12345":
            print("Refusing to seed the default admin password in production.", file=sys.stderr)
            print("Set SEED_ADMIN_PASSWORD to something unique first.", file=sys.stderr)
            sys.exit(1)
        db.add(
            User(
                email=settings.seed_admin_email,
                password_hash=hash_password(settings.seed_admin_password),
                full_name="Platform Admin",
                role=UserRole.ADMIN,
                email_verified=True,
            )
        )
        await db.commit()
        print(f"Created admin {settings.seed_admin_email}")


async def seed_demo() -> None:
    """A handful of listings and accounts so the app isn't empty on first run."""
    from app.modules.availability.models import AvailabilityRule
    from app.modules.parking.models import ListingStatus, ParkingPrice, ParkingSpace, PricingUnit
    from app.modules.providers.models import Provider, ProviderType, VerificationStatus
    from app.modules.users.models import User, UserRole
    from app.modules.vehicles.models import Vehicle

    if settings.environment == "production":
        print("Refusing to seed demo data in production.", file=sys.stderr)
        sys.exit(1)

    # title, type, lat, lon, vehicles, hourly, daily, street, landmark
    listings = [
        ("Covered parking near Ashram Road", "COVERED", 23.0225, 72.5714, ["CAR", "SUV"], "50.00",
         "300.00", "12 Ashram Road", "Opposite the metro entrance"),
        ("Open parking opposite CG Road", "OPEN", 23.0290, 72.5600, ["CAR", "BIKE"], "30.00",
         "200.00", "48 Chimanlal Girdharlal Road", "Behind the shopping arcade"),
        ("Basement bay, Prahlad Nagar", "BASEMENT", 23.0120, 72.5100, ["CAR", "SUV"], "60.00",
         "350.00", "7 Prahlad Nagar Garden Road", "Basement level 1, gated"),
        ("Society visitor parking, Bodakdev", "OPEN", 23.0400, 72.5100, ["CAR"], "40.00",
         "250.00", "Green Acres Society, Judges Bungalow Road", "Visitor bays near the main gate"),
    ]

    async with SessionLocal() as db:
        if await db.scalar(select(ParkingSpace.id).limit(1)):
            print("Demo data already present; skipping")
            return

        provider_user = User(
            email="provider@example.com",
            password_hash=hash_password("provider12345"),
            full_name="Pravin Shah",
            phone="+919876543210",
            role=UserRole.PROVIDER,
            email_verified=True,
        )
        renter_user = User(
            email="renter@example.com",
            password_hash=hash_password("renter12345"),
            full_name="Riya Mehta",
            phone="+919812345678",
            role=UserRole.RENTER,
            email_verified=True,
        )
        db.add_all([provider_user, renter_user])
        await db.flush()

        provider = Provider(
            user_id=provider_user.id,
            provider_type=ProviderType.INDIVIDUAL,
            display_name="Pravin Shah",
            contact_phone=provider_user.phone,
            address="Ashram Road, Ahmedabad",
            verification_status=VerificationStatus.VERIFIED,
            authority_declared_at=utcnow(),
        )
        db.add(provider)
        db.add(
            Vehicle(
                user_id=renter_user.id,
                vehicle_type="CAR",
                registration_number="GJ01AB1234",
                make_model="Hyundai i20",
                is_default=True,
            )
        )
        await db.flush()

        for title, parking_type, lat, lon, vehicles, hourly, daily, street, landmark in listings:
            space = ParkingSpace(
                provider_id=provider.id,
                title=title,
                description="Secure, easy to reach, and a short walk from the main road.",
                parking_type=parking_type,
                vehicle_types=vehicles,
                address_line=street,
                landmark=landmark,
                city="Ahmedabad",
                state="Gujarat",
                latitude=lat,
                longitude=lon,
                access_instructions="Enter through the main gate and show your booking reference.",
                status=ListingStatus.PUBLISHED,
                authority_confirmed=True,
                prices=[
                    ParkingPrice(unit=PricingUnit.HOURLY, amount=Decimal(hourly)),
                    ParkingPrice(unit=PricingUnit.DAILY, amount=Decimal(daily)),
                ],
                photos=[],
            )
            db.add(space)
            await db.flush()
            for day in range(7):
                db.add(
                    AvailabilityRule(
                        parking_space_id=space.id, day_of_week=day, start_minute=8 * 60, end_minute=20 * 60
                    )
                )
        await db.commit()
        print(f"Seeded {len(listings)} listings")
        print("  provider@example.com / provider12345")
        print("  renter@example.com / renter12345")


async def run_maintenance() -> None:
    from app.modules.bookings.maintenance import run_once

    async with SessionLocal() as db:
        print(await run_once(db))


COMMANDS = {
    "seed": seed_admin,
    "demo": seed_demo,
    "maintenance": run_maintenance,
}


def main() -> None:
    configure_logging()
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    handler = COMMANDS.get(command)
    if handler is None:
        print(f"Usage: python -m app.cli [{' | '.join(COMMANDS)}]", file=sys.stderr)
        sys.exit(1)
    asyncio.run(handler())


if __name__ == "__main__":
    main()

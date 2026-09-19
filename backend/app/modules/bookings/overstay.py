"""Charging for time taken beyond the booked window.

There is no exit sensor, so the platform cannot see a car leave. What it can see
is that a booking's window has passed and the renter has not closed it. After a
free grace period that becomes an overstay: the meter runs, the bay keeps
blocking, and the renter settles the top-up to finish.

Two things this is careful about:

  - The bay stays blocked. `OVERSTAYING` is in `BLOCKING_STATUSES`, because a
    car that is still there is still there whatever the booking says.
  - The meter stops. Without a cap an abandoned booking would accrue forever and
    take the bay with it, so `overstay_max_hours` ends it and leaves the debt on
    the record for an admin to chase.
"""
import math
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.time import utcnow
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.settings.schemas import PlatformConfig

MINUTES_PER_HOUR = Decimal("60")


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def hourly_rate(booking: Booking) -> Decimal:
    """What an hour of this booking cost, whatever unit it was sold in.

    A daily or monthly booking still has to yield an hourly number for the
    meter, so the paid base is spread across the hours it covered.
    """
    hours = Decimal((booking.end_at - booking.start_at).total_seconds()) / Decimal("3600")
    if hours <= 0:
        return Decimal(booking.unit_price)
    return Decimal(booking.base_amount) / hours


def grace_ends_at(booking: Booking, config: PlatformConfig) -> datetime:
    return booking.end_at + timedelta(minutes=config.overstay_grace_minutes)


def meter_stops_at(booking: Booking, config: PlatformConfig) -> datetime:
    return booking.end_at + timedelta(hours=config.overstay_max_hours)


def billable_minutes(booking: Booking, config: PlatformConfig, now: datetime | None = None) -> int:
    """Whole increments owed, counted from the END of the booking.

    The grace period decides *whether* the meter runs, not where it starts —
    otherwise being 16 minutes late would cost the same as being 1 minute late.
    """
    now = min(now or utcnow(), meter_stops_at(booking, config))
    if now <= grace_ends_at(booking, config):
        return 0
    over = (now - booking.end_at).total_seconds() / 60
    step = config.overstay_increment_minutes
    return int(math.ceil(over / step) * step)


def amount_for(booking: Booking, config: PlatformConfig, now: datetime | None = None) -> Decimal:
    minutes = billable_minutes(booking, config, now)
    if minutes <= 0:
        return Decimal("0.00")
    rate = hourly_rate(booking) * Decimal(str(config.overstay_rate_multiplier))
    return _money(rate * (Decimal(minutes) / MINUTES_PER_HOUR))


def quote(booking: Booking, config: PlatformConfig, now: datetime | None = None) -> dict:
    """What the renter sees on the live meter."""
    now = now or utcnow()
    minutes = billable_minutes(booking, config, now)
    due = amount_for(booking, config, now)
    already = Decimal(booking.overstay_amount or 0)
    capped = now >= meter_stops_at(booking, config)
    return {
        "booking_id": booking.id,
        "status": booking.status,
        "overstaying": booking.status == BookingStatus.OVERSTAYING,
        "grace_ends_at": grace_ends_at(booking, config),
        "overstay_minutes": minutes,
        "overstay_amount": due,
        "amount_due": _money(max(due - already, Decimal("0.00"))) if booking.overstay_paid_at else due,
        "paid": booking.overstay_paid_at is not None,
        "meter_capped": capped,
        "meter_stops_at": meter_stops_at(booking, config),
        "hourly_rate": _money(hourly_rate(booking) * Decimal(str(config.overstay_rate_multiplier))),
        "currency": booking.currency,
    }


def freeze(booking: Booking, config: PlatformConfig, now: datetime | None = None) -> Decimal:
    """Write the accrued overstay onto the booking and return what is owed."""
    now = now or utcnow()
    booking.overstay_minutes = billable_minutes(booking, config, now)
    booking.overstay_amount = amount_for(booking, config, now)
    return Decimal(booking.overstay_amount)

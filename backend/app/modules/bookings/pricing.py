"""Booking duration validation and price calculation.

Every percentage comes from `PlatformConfig` (admin-editable, stored in the
database) — none are hard-coded here. Amounts are computed with `Decimal` and
rounded once, at the end of each line, to avoid the drift float arithmetic
introduces on money.

    base parking price   = unit price x quantity
  + platform fee         = base x renter_fee_percent
  + tax                  = platform fee x tax_percent
  ------------------------------------------------
  = total the renter pays

    commission           = base x commission_percent   (or the society's share)
    provider earning     = base - commission
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.time import local_tz
from app.modules.parking.models import ParkingSpace, PricingUnit
from app.modules.settings.schemas import PlatformConfig

MONEY = Decimal("0.01")


class InvalidDuration(Exception):
    def __init__(self, message: str, code: str = "INVALID_DURATION"):
        super().__init__(message)
        self.message = message
        self.code = code


def money(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def add_months(moment: datetime, months: int) -> datetime:
    """Calendar-month arithmetic, clamping to the last valid day (31 Jan + 1 = 28/29 Feb)."""
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, _days_in_month(year, month))
    return moment.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (datetime(year, month + 1, 1) - timedelta(days=1)).day


def _is_local_midnight(moment: datetime) -> bool:
    local = moment.astimezone(local_tz())
    return (local.hour, local.minute, local.second, local.microsecond) == (0, 0, 0, 0)


def quantity_for(unit: PricingUnit, start_at: datetime, end_at: datetime, config: PlatformConfig) -> Decimal:
    """Billable units for the window, rejecting windows that don't fit the unit."""
    if end_at <= start_at:
        raise InvalidDuration("End time must be after start time")
    minutes = Decimal((end_at - start_at).total_seconds()) / Decimal(60)

    if unit == PricingUnit.HOURLY:
        slot = Decimal(config.booking_slot_minutes)
        if minutes % slot != 0:
            raise InvalidDuration(
                f"Hourly bookings must be a multiple of {config.booking_slot_minutes} minutes",
                code="INVALID_SLOT_ALIGNMENT",
            )
        return (minutes / Decimal(60)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if not _is_local_midnight(start_at) or not _is_local_midnight(end_at):
        raise InvalidDuration(
            f"{unit.value.capitalize()} bookings must start and end at midnight", code="INVALID_BOUNDARY"
        )

    if unit == PricingUnit.DAILY:
        days = minutes / Decimal(60 * 24)
        if days != days.to_integral_value():
            raise InvalidDuration("Daily bookings must cover whole days")
        return days.to_integral_value()

    if unit == PricingUnit.MONTHLY:
        months = 0
        cursor = start_at
        while cursor < end_at and months < 60:
            months += 1
            cursor = add_months(start_at, months)
        if cursor != end_at:
            raise InvalidDuration(
                "Monthly bookings must end on the same day of a later month", code="INVALID_BOUNDARY"
            )
        return Decimal(months)

    raise InvalidDuration(f"Unsupported duration type: {unit}")


def end_for(unit: PricingUnit, start_at: datetime, quantity: int) -> datetime:
    """Inverse of `quantity_for` — used by the frontend-facing quote helper."""
    if quantity < 1:
        raise InvalidDuration("Quantity must be at least 1")
    if unit == PricingUnit.HOURLY:
        return start_at + timedelta(hours=quantity)
    if unit == PricingUnit.DAILY:
        return start_at + timedelta(days=quantity)
    if unit == PricingUnit.MONTHLY:
        return add_months(start_at, quantity)
    raise InvalidDuration(f"Unsupported duration type: {unit}")


def unit_price_for(space: ParkingSpace, unit: PricingUnit) -> Decimal:
    for price in space.prices:
        if price.unit == unit:
            return Decimal(price.amount)
    raise InvalidDuration(
        f"This space is not offered on a {unit.value.lower()} basis", code="UNIT_NOT_OFFERED"
    )


@dataclass
class PriceBreakdown:
    unit: PricingUnit
    quantity: Decimal
    unit_price: Decimal
    base_amount: Decimal
    platform_fee: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    commission_amount: Decimal
    provider_earning: Decimal
    currency: str = "INR"

    def as_dict(self) -> dict:
        return asdict(self)


def calculate(
    space: ParkingSpace,
    unit: PricingUnit,
    start_at: datetime,
    end_at: datetime,
    config: PlatformConfig,
    *,
    provider_share_percent: Decimal | None = None,
) -> PriceBreakdown:
    """Full price breakdown for a window.

    `provider_share_percent` overrides the default commission — that is how a
    society's negotiated revenue share is applied (PRD §30).
    """
    quantity = quantity_for(unit, start_at, end_at, config)
    unit_price = unit_price_for(space, unit)

    base_amount = money(unit_price * quantity)
    platform_fee = money(base_amount * Decimal(str(config.renter_fee_percent)) / 100)
    tax_amount = money(platform_fee * Decimal(str(config.tax_percent)) / 100)
    total_amount = money(base_amount + platform_fee + tax_amount)

    if provider_share_percent is not None:
        provider_earning = money(base_amount * Decimal(str(provider_share_percent)) / 100)
        commission_amount = money(base_amount - provider_earning)
    else:
        commission_amount = money(base_amount * Decimal(str(config.commission_percent)) / 100)
        provider_earning = money(base_amount - commission_amount)

    return PriceBreakdown(
        unit=unit,
        quantity=quantity,
        unit_price=unit_price,
        base_amount=base_amount,
        platform_fee=platform_fee,
        tax_amount=tax_amount,
        total_amount=total_amount,
        commission_amount=commission_amount,
        provider_earning=provider_earning,
    )


def refund_for(total_amount: Decimal, hours_before_start: float, config: PlatformConfig) -> Decimal:
    """Refund due under the configured cancellation policy."""
    policy = config.cancellation_policy
    for tier in policy.tiers:
        if hours_before_start >= tier.min_hours_before:
            return money(total_amount * Decimal(str(tier.refund_percent)) / 100)
    return money(total_amount * Decimal(str(policy.default_refund_percent)) / 100)

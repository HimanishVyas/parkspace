"""Pricing and availability maths — pure functions, no database."""
from datetime import datetime
from decimal import Decimal

import pytest

from app.modules.availability.service import (
    covers,
    daily_segments,
    intervals_for_weekday,
    merge_intervals,
)
from app.modules.bookings.pricing import (
    InvalidDuration,
    add_months,
    calculate,
    end_for,
    quantity_for,
    refund_for,
)
from app.modules.parking.models import PricingUnit
from app.modules.settings.schemas import (
    CancellationPolicy,
    CancellationTier,
    PlatformConfig,
)
from tests.conftest import local


class FakeRule:
    def __init__(self, day, start, end, active=True):
        self.day_of_week, self.start_minute, self.end_minute, self.is_active = day, start, end, active


class FakePrice:
    def __init__(self, unit, amount):
        self.unit, self.amount = unit, Decimal(amount)


class FakeSpace:
    def __init__(self, prices):
        self.prices = prices


CONFIG = PlatformConfig()


# --------------------------------------------------------------------------- #
# Interval maths
# --------------------------------------------------------------------------- #
def test_merge_intervals_coalesces_overlaps_and_touches():
    assert merge_intervals([(600, 780), (480, 660)]) == [(480, 780)]
    assert merge_intervals([(480, 600), (600, 720)]) == [(480, 720)]
    assert merge_intervals([(480, 600), (700, 800)]) == [(480, 600), (700, 800)]
    assert merge_intervals([]) == []


def test_covers_requires_full_containment():
    assert covers([(480, 1200)], 600, 780)
    assert covers([(480, 1200)], 480, 1200)
    assert not covers([(480, 1200)], 400, 600)
    assert not covers([(480, 1200)], 1100, 1300)
    # A gap in the middle isn't covered even though both ends are.
    assert not covers([(480, 600), (700, 800)], 500, 750)


def test_inactive_rules_are_ignored():
    rules = [FakeRule(0, 480, 1200), FakeRule(0, 1200, 1380, active=False)]
    assert intervals_for_weekday(rules, 0) == [(480, 1200)]


def test_daily_segments_splits_across_midnight():
    segments = daily_segments(local(2026, 10, 1, 22, 0), local(2026, 10, 2, 3, 0))
    assert segments == [
        (local(2026, 10, 1).date(), 1320, 1440),
        (local(2026, 10, 2).date(), 0, 180),
    ]


# --------------------------------------------------------------------------- #
# Duration
# --------------------------------------------------------------------------- #
def test_hourly_quantity():
    assert quantity_for(
        PricingUnit.HOURLY, local(2026, 10, 1, 10), local(2026, 10, 1, 13), CONFIG
    ) == Decimal("3.00")
    # Half hours are fine at the default 30-minute slot.
    assert quantity_for(
        PricingUnit.HOURLY, local(2026, 10, 1, 10), local(2026, 10, 1, 11, 30), CONFIG
    ) == Decimal("1.50")


def test_hourly_rejects_unaligned_windows():
    with pytest.raises(InvalidDuration) as exc:
        quantity_for(PricingUnit.HOURLY, local(2026, 10, 1, 10), local(2026, 10, 1, 10, 17), CONFIG)
    assert exc.value.code == "INVALID_SLOT_ALIGNMENT"


def test_daily_requires_midnight_boundaries():
    assert quantity_for(
        PricingUnit.DAILY, local(2026, 10, 1), local(2026, 10, 3), CONFIG
    ) == Decimal("2")
    with pytest.raises(InvalidDuration) as exc:
        quantity_for(PricingUnit.DAILY, local(2026, 10, 1, 9), local(2026, 10, 3, 9), CONFIG)
    assert exc.value.code == "INVALID_BOUNDARY"


def test_monthly_counts_calendar_months():
    assert quantity_for(
        PricingUnit.MONTHLY, local(2026, 10, 1), local(2026, 11, 1), CONFIG
    ) == Decimal("1")
    assert quantity_for(
        PricingUnit.MONTHLY, local(2026, 10, 1), local(2027, 1, 1), CONFIG
    ) == Decimal("3")


def test_monthly_rejects_a_partial_month():
    with pytest.raises(InvalidDuration):
        quantity_for(PricingUnit.MONTHLY, local(2026, 10, 1), local(2026, 10, 20), CONFIG)


def test_add_months_clamps_to_the_last_valid_day():
    assert add_months(datetime(2026, 1, 31), 1).date() == datetime(2026, 2, 28).date()
    assert add_months(datetime(2024, 1, 31), 1).date() == datetime(2024, 2, 29).date()
    assert add_months(datetime(2026, 12, 15), 1).date() == datetime(2027, 1, 15).date()


def test_end_for_is_the_inverse_of_quantity_for():
    start = local(2026, 10, 1)
    for unit, quantity in [(PricingUnit.HOURLY, 3), (PricingUnit.DAILY, 2), (PricingUnit.MONTHLY, 2)]:
        end = end_for(unit, start, quantity)
        assert quantity_for(unit, start, end, CONFIG) == Decimal(quantity)


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #
def test_price_breakdown_matches_the_prd_example():
    """PRD §47: 3 hours at Rs 50 = Rs 150 base, plus platform fee and tax."""
    space = FakeSpace([FakePrice(PricingUnit.HOURLY, "50.00")])
    result = calculate(
        space, PricingUnit.HOURLY, local(2026, 10, 1, 10), local(2026, 10, 1, 13), CONFIG
    )
    assert result.base_amount == Decimal("150.00")
    assert result.platform_fee == Decimal("7.50")      # 5% renter fee
    assert result.tax_amount == Decimal("1.35")        # 18% GST on the fee
    assert result.total_amount == Decimal("158.85")
    assert result.commission_amount == Decimal("22.50")  # 15% commission
    assert result.provider_earning == Decimal("127.50")
    # The provider's share and the commission always reconstruct the base.
    assert result.commission_amount + result.provider_earning == result.base_amount


def test_commission_example_from_the_prd():
    """PRD §15: Rs 1,000 at 15% leaves the provider Rs 850."""
    space = FakeSpace([FakePrice(PricingUnit.DAILY, "1000.00")])
    result = calculate(space, PricingUnit.DAILY, local(2026, 10, 1), local(2026, 10, 2), CONFIG)
    assert result.base_amount == Decimal("1000.00")
    assert result.commission_amount == Decimal("150.00")
    assert result.provider_earning == Decimal("850.00")


def test_commission_is_configurable_not_hard_coded():
    space = FakeSpace([FakePrice(PricingUnit.HOURLY, "100.00")])
    config = PlatformConfig(commission_percent=25, renter_fee_percent=0, tax_percent=0)
    result = calculate(space, PricingUnit.HOURLY, local(2026, 10, 1, 10), local(2026, 10, 1, 11), config)
    assert result.commission_amount == Decimal("25.00")
    assert result.provider_earning == Decimal("75.00")
    assert result.total_amount == Decimal("100.00")


def test_society_revenue_share_overrides_commission():
    space = FakeSpace([FakePrice(PricingUnit.HOURLY, "100.00")])
    result = calculate(
        space,
        PricingUnit.HOURLY,
        local(2026, 10, 1, 10),
        local(2026, 10, 1, 11),
        CONFIG,
        provider_share_percent=Decimal("70"),
    )
    assert result.provider_earning == Decimal("70.00")
    assert result.commission_amount == Decimal("30.00")


def test_unoffered_duration_is_rejected():
    space = FakeSpace([FakePrice(PricingUnit.HOURLY, "50.00")])
    with pytest.raises(InvalidDuration) as exc:
        calculate(space, PricingUnit.MONTHLY, local(2026, 10, 1), local(2026, 11, 1), CONFIG)
    assert exc.value.code == "UNIT_NOT_OFFERED"


# --------------------------------------------------------------------------- #
# Cancellation policy
# --------------------------------------------------------------------------- #
def test_refund_tiers_are_applied_in_order():
    total = Decimal("1000.00")
    assert refund_for(total, 48, CONFIG) == Decimal("1000.00")   # >= 24h -> 100%
    assert refund_for(total, 24, CONFIG) == Decimal("1000.00")   # boundary is inclusive
    assert refund_for(total, 5, CONFIG) == Decimal("500.00")     # >= 2h  -> 50%
    assert refund_for(total, 1, CONFIG) == Decimal("0.00")       # otherwise the default
    assert refund_for(total, -3, CONFIG) == Decimal("0.00")      # already started


def test_refund_policy_is_configurable():
    config = PlatformConfig(
        cancellation_policy=CancellationPolicy(
            tiers=[CancellationTier(min_hours_before=1, refund_percent=80)],
            default_refund_percent=20,
        )
    )
    assert refund_for(Decimal("500.00"), 3, config) == Decimal("400.00")
    assert refund_for(Decimal("500.00"), 0.5, config) == Decimal("100.00")


def test_tiers_are_sorted_regardless_of_input_order():
    policy = CancellationPolicy(
        tiers=[
            CancellationTier(min_hours_before=2, refund_percent=50),
            CancellationTier(min_hours_before=24, refund_percent=100),
        ]
    )
    assert [tier.min_hours_before for tier in policy.tiers] == [24, 2]

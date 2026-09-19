from pydantic import BaseModel, Field, model_validator


class CancellationTier(BaseModel):
    # Cancelling at least this many hours before start gets `refund_percent`.
    min_hours_before: float = Field(ge=0)
    refund_percent: float = Field(ge=0, le=100)


class CancellationPolicy(BaseModel):
    tiers: list[CancellationTier] = Field(
        default_factory=lambda: [
            CancellationTier(min_hours_before=24, refund_percent=100),
            CancellationTier(min_hours_before=2, refund_percent=50),
        ]
    )
    # Refund when no tier matches (e.g. cancelling less than 2 hours before start).
    default_refund_percent: float = Field(default=0, ge=0, le=100)
    # Whether renters can cancel after the booking has started.
    allow_after_start: bool = False

    @model_validator(mode="after")
    def _sort(self):
        self.tiers = sorted(self.tiers, key=lambda t: t.min_hours_before, reverse=True)
        return self


class PlatformConfig(BaseModel):
    """All admin-configurable business rules with their defaults.

    Stored as individual rows in `platform_settings`; missing rows fall back to
    these defaults.
    """

    # Service fee charged to the renter on top of the base parking price (percent of base).
    renter_fee_percent: float = Field(default=5, ge=0, le=100)
    # Tax (e.g. GST) applied to the renter service fee (percent of that fee).
    tax_percent: float = Field(default=18, ge=0, le=100)
    # Commission deducted from the provider's base price (percent of base).
    commission_percent: float = Field(default=15, ge=0, le=100)
    cancellation_policy: CancellationPolicy = Field(default_factory=CancellationPolicy)
    # How long an unpaid booking holds the slot before expiring.
    payment_hold_minutes: int = Field(default=15, ge=1, le=240)
    # How long a provider has to accept a booking on a manual-approval listing
    # before it expires and the slot is released.
    approval_window_hours: int = Field(default=12, ge=1, le=168)
    # If true, published listings go to PENDING_APPROVAL until an admin approves.
    listing_requires_approval: bool = False
    # How far into the future a booking may start.
    booking_max_advance_days: int = Field(default=180, ge=1, le=730)
    # Minimum minutes between now and booking start.
    booking_min_lead_minutes: int = Field(default=0, ge=0, le=10080)
    # Booking start/end must align to this many minutes.
    booking_slot_minutes: int = Field(default=30, ge=5, le=60)
    # Hours before start to send a reminder notification.
    reminder_hours_before: float = Field(default=2, ge=0, le=72)

    # --- Arrival verification (PRD §18 extension) --------------------------- #
    # How long an arrival code stays valid. Long enough for a missed call and a
    # call back, short enough that a code overheard earlier is useless.
    arrival_code_ttl_minutes: int = Field(default=10, ge=1, le=120)
    # Wrong guesses allowed before the code is burned and must be re-requested.
    arrival_code_max_attempts: int = Field(default=5, ge=1, le=20)
    # How close the renter must be to announce arrival. Generous, because urban
    # GPS drifts badly between tall buildings.
    arrival_geofence_metres: int = Field(default=150, ge=20, le=2000)
    # After this long with no code from the provider, the renter is offered a
    # support route instead of a dead end.
    arrival_escalate_minutes: int = Field(default=10, ge=1, le=120)
    # How early before start a renter may announce arrival.
    arrival_early_minutes: int = Field(default=30, ge=0, le=240)

    # --- Overstay ---------------------------------------------------------- #
    # Free lateness. Absorbs ordinary delay without a charge that feels punitive.
    overstay_grace_minutes: int = Field(default=15, ge=0, le=240)
    # Multiple of the hourly rate once the meter runs. Above normal so it
    # discourages overstaying, below a penalty that invites a dispute.
    overstay_rate_multiplier: float = Field(default=1.5, ge=1, le=10)
    # Billed in whole blocks: per-minute pricing produces amounts nobody can
    # check, quarter-hours read cleanly on a receipt.
    overstay_increment_minutes: int = Field(default=15, ge=1, le=120)
    # The meter stops here. Without an exit sensor an abandoned booking would
    # otherwise accrue forever and block the bay for good.
    overstay_max_hours: int = Field(default=12, ge=1, le=72)

    @model_validator(mode="after")
    def _slot_divides_hour(self):
        if 60 % self.booking_slot_minutes != 0:
            raise ValueError("booking_slot_minutes must divide 60")
        return self


class PlatformConfigUpdate(BaseModel):
    overstay_grace_minutes: int | None = None
    overstay_rate_multiplier: float | None = None
    overstay_increment_minutes: int | None = None
    overstay_max_hours: int | None = None
    arrival_code_ttl_minutes: int | None = None
    arrival_code_max_attempts: int | None = None
    arrival_geofence_metres: int | None = None
    arrival_escalate_minutes: int | None = None
    arrival_early_minutes: int | None = None
    renter_fee_percent: float | None = None
    tax_percent: float | None = None
    commission_percent: float | None = None
    cancellation_policy: CancellationPolicy | None = None
    payment_hold_minutes: int | None = None
    approval_window_hours: int | None = None
    listing_requires_approval: bool | None = None
    booking_max_advance_days: int | None = None
    booking_min_lead_minutes: int | None = None
    booking_slot_minutes: int | None = None
    reminder_hours_before: float | None = None

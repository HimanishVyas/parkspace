import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.availability.models import MINUTES_PER_DAY


class RuleIn(BaseModel):
    # 0 = Monday ... 6 = Sunday.
    day_of_week: int = Field(ge=0, le=6)
    start_minute: int = Field(ge=0, lt=MINUTES_PER_DAY)
    end_minute: int = Field(gt=0, le=MINUTES_PER_DAY)
    is_active: bool = True

    @model_validator(mode="after")
    def _ordered(self):
        if self.end_minute <= self.start_minute:
            raise ValueError("end_minute must be after start_minute")
        return self


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    day_of_week: int
    start_minute: int
    end_minute: int
    is_active: bool


class RulesReplace(BaseModel):
    """The full weekly schedule. Replacing wholesale keeps the provider's
    calendar edits atomic and free of partial-update ordering bugs."""

    rules: list[RuleIn] = Field(max_length=100)

    @model_validator(mode="after")
    def _no_overlaps(self):
        by_day: dict[int, list[tuple[int, int]]] = {}
        for rule in self.rules:
            if not rule.is_active:
                continue
            by_day.setdefault(rule.day_of_week, []).append((rule.start_minute, rule.end_minute))
        for day, windows in by_day.items():
            windows.sort()
            for (_, prev_end), (next_start, _) in zip(windows, windows[1:]):
                if next_start < prev_end:
                    raise ValueError(f"Overlapping availability windows on day {day}")
        return self


class BlockIn(BaseModel):
    start_at: datetime
    end_at: datetime
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _ordered(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class BlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    reason: str | None


class AvailabilityOut(BaseModel):
    rules: list[RuleOut]
    blocks: list[BlockOut]


class CalendarDay(BaseModel):
    day: date
    windows: list[tuple[int, int]]
    blocked: bool
    booked_slots: int
    total_slots: int
    is_open: bool


class CalendarOut(BaseModel):
    parking_space_id: uuid.UUID
    days: list[CalendarDay]

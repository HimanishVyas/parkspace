import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.parking.models import VehicleType

_REGISTRATION_RE = re.compile(r"^[A-Z0-9]{4,20}$")


def normalize_registration(value: str | None) -> str | None:
    """Indian plates are written many ways (GJ-01 AB 1234); store one canonical form."""
    if value is None:
        return None
    cleaned = re.sub(r"[\s\-]", "", value).upper()
    if not _REGISTRATION_RE.match(cleaned):
        raise ValueError("Invalid vehicle registration number")
    return cleaned


class VehicleCreate(BaseModel):
    vehicle_type: VehicleType
    registration_number: str
    make_model: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=40)
    is_default: bool = False

    _registration = field_validator("registration_number")(normalize_registration)


class VehicleUpdate(BaseModel):
    vehicle_type: VehicleType | None = None
    registration_number: str | None = None
    make_model: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=40)
    is_default: bool | None = None

    _registration = field_validator("registration_number")(normalize_registration)


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vehicle_type: VehicleType
    registration_number: str
    make_model: str | None
    color: str | None
    is_default: bool
    created_at: datetime

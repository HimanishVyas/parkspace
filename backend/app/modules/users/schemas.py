import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.users.models import UserRole, UserStatus

_PHONE_RE = re.compile(r"^\+?[0-9]{10,15}$")


def normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"[\s\-()]", "", value)
    if not cleaned:
        return None
    if not _PHONE_RE.match(cleaned):
        raise ValueError("Invalid phone number")
    if not cleaned.startswith("+"):
        # Pilot market is India: bare 10-digit numbers get the +91 prefix.
        cleaned = "+91" + cleaned if len(cleaned) == 10 else "+" + cleaned
    return cleaned


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Plain str, not EmailStr: this is an output model. Re-validating a value
    # already stored would turn a stricter validator into a 500 on read.
    email: str
    phone: str | None
    full_name: str
    profile_photo_url: str | None
    role: UserRole
    status: UserStatus
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = None

    _phone = field_validator("phone")(normalize_phone)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

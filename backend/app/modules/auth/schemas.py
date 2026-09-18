from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.modules.users.schemas import UserOut, normalize_phone


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    phone: str | None = None
    # Admin accounts are never self-registered.
    role: Literal["RENTER", "PROVIDER"] = "RENTER"
    provider_type: Literal["INDIVIDUAL", "SOCIETY"] | None = None
    # Society / organisation name when provider_type == SOCIETY.
    organization_name: str | None = Field(default=None, max_length=200)

    _phone = field_validator("phone")(normalize_phone)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()

    @model_validator(mode="after")
    def _provider_fields(self):
        if self.role == "PROVIDER":
            self.provider_type = self.provider_type or "INDIVIDUAL"
            if self.provider_type == "SOCIETY" and not (self.organization_name or "").strip():
                raise ValueError("organization_name is required for society providers")
        else:
            self.provider_type = None
            self.organization_name = None
        return self


class LoginRequest(BaseModel):
    # Email address or phone number.
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut

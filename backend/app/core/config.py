"""Application configuration loaded from environment variables.

Only infrastructure/secrets live here. Business rules (fees, commission,
cancellation policy, ...) live in the `platform_settings` table so admins can
change them at runtime — see app/modules/settings.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # General
    app_name: str = "ParkSpace"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    # Public URL of the web frontend, used in emails and payment redirects.
    frontend_url: str = "http://localhost:18080"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://localhost:18080"])
    # All availability rules are interpreted in this timezone (single-city pilot).
    timezone: str = "Asia/Kolkata"

    # Database
    database_url: str = "postgresql+asyncpg://parking:parking@localhost:55432/parking"
    db_echo: bool = False

    # Redis (optional). When empty, rate limiting falls back to in-process memory.
    redis_url: str = ""

    # Auth
    jwt_secret: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    refresh_token_days: int = 30

    # Storage
    storage_backend: Literal["local"] = "local"
    media_root: str = "media"
    media_url: str = "/media"
    max_upload_bytes: int = 5 * 1024 * 1024

    # Payments
    payment_gateway: Literal["mock", "razorpay"] = "mock"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    # Secret used by the mock gateway to sign simulated payments.
    mock_gateway_secret: str = "mock-gateway-secret"

    # Email
    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "ParkSpace <no-reply@parkspace.app>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_tls: bool = False

    # Geocoding (address -> coordinates) proxy. Empty disables it.
    geocoder_url: str = "https://nominatim.openstreetmap.org/search"
    geocoder_user_agent: str = "parkspace-pilot/1.0"

    # Background maintenance loop (expire holds, activate/complete bookings, reminders)
    maintenance_enabled: bool = True
    maintenance_interval_seconds: int = 60

    # Rate limiting
    rate_limit_enabled: bool = True

    # Bootstrap admin created by `python -m app.cli seed`.
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "admin12345"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def local_tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def ensure_aware(dt: datetime) -> datetime:
    """Treat naive datetimes as local (pilot city) time."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=local_tz())
    return dt

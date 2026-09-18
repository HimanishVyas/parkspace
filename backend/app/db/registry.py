"""Imports every model module so `Base.metadata` is complete.

Alembic autogenerate and the test harness both rely on this single import.
"""
from app.db.base import Base
from app.modules.audit import models as audit_models  # noqa: F401
from app.modules.availability import models as availability_models  # noqa: F401
from app.modules.bookings import models as booking_models  # noqa: F401
from app.modules.notifications import models as notification_models  # noqa: F401
from app.modules.parking import models as parking_models  # noqa: F401
from app.modules.payments import models as payment_models  # noqa: F401
from app.modules.providers import models as provider_models  # noqa: F401
from app.modules.reports import models as report_models  # noqa: F401
from app.modules.reviews import models as review_models  # noqa: F401
from app.modules.settings import models as setting_models  # noqa: F401
from app.modules.users import models as user_models  # noqa: F401
from app.modules.vehicles import models as vehicle_models  # noqa: F401

__all__ = ["Base"]

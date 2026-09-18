import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.payments.models import PaymentStatus


class PaymentCreate(BaseModel):
    booking_id: uuid.UUID


class PaymentSession(BaseModel):
    """Everything the browser needs to open the gateway checkout."""

    payment_id: uuid.UUID
    booking_id: uuid.UUID
    gateway: str
    order_id: str
    amount: Decimal
    currency: str
    client_payload: dict[str, Any]


class PaymentConfirm(BaseModel):
    order_id: str = Field(min_length=4, max_length=120)
    payment_id: str = Field(min_length=4, max_length=120)
    signature: str = Field(min_length=8, max_length=256)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    gateway: str
    gateway_order_id: str
    amount: Decimal
    currency: str
    status: PaymentStatus
    method: str | None
    captured_at: datetime | None
    created_at: datetime

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.reviews.models import ReviewSubject


class ReviewCreate(BaseModel):
    booking_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    subject: ReviewSubject
    rating: int
    comment: str | None
    created_at: datetime
    # First name only — a review shouldn't expose a full identity.
    author_name: str | None = None


class ReviewSummary(BaseModel):
    average: Decimal | None
    count: int
    items: list[ReviewOut]

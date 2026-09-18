import uuid

from fastapi import APIRouter, Query, status

from app.core.deps import DB, CurrentUser
from app.modules.reviews import service
from app.modules.reviews.schemas import ReviewCreate, ReviewOut, ReviewSummary

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
async def create_review(data: ReviewCreate, user: CurrentUser, db: DB):
    """Rate a completed booking. Renters rate the space; providers rate the renter."""
    review = await service.create(db, user, data)
    await db.commit()
    await db.refresh(review)
    out = ReviewOut.model_validate(review)
    out.author_name = service.display_name(user.full_name)
    return out


@router.get("/space/{space_id}", response_model=ReviewSummary)
async def list_space_reviews(
    space_id: uuid.UUID,
    db: DB,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
):
    rows, average, count = await service.for_space(db, space_id, limit, offset)
    items = []
    for review, author_name in rows:
        out = ReviewOut.model_validate(review)
        out.author_name = service.display_name(author_name)
        items.append(out)
    return ReviewSummary(average=average, count=count, items=items)

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.core.deps import DB, CurrentUser
from app.core.ratelimit import rate_limit
from app.modules.auth import service
from app.modules.auth.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register", 10, 60))],
)
async def register(data: RegisterRequest, db: DB, background: BackgroundTasks):
    user = await service.register(db, data)
    from app.modules.notifications.service import notify

    await notify(
        db,
        background,
        user,
        "WELCOME",
        "Welcome to ParkSpace",
        "Your account has been created. Find parking nearby or list your unused space.",
    )
    await db.commit()
    return service.issue_tokens(user)


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit("login", 10, 60))])
async def login(data: LoginRequest, db: DB):
    user = await service.authenticate(db, data)
    return service.issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(rate_limit("refresh", 30, 60))])
async def refresh(data: RefreshRequest, db: DB):
    user = await service.refresh(db, data.refresh_token)
    return service.issue_tokens(user)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user: CurrentUser, db: DB):
    """Invalidate every token issued to the current user."""
    user.token_version += 1
    await db.commit()

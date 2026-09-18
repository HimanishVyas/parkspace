from fastapi import APIRouter, Depends, UploadFile, status
from sqlalchemy import select

from app.core.deps import DB, CurrentUser
from app.core.errors import Conflict, Unauthorized
from app.core.ratelimit import rate_limit
from app.core.security import hash_password, verify_password
from app.modules.users.models import User
from app.modules.users.schemas import PasswordChange, UserOut, UserUpdate

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserOut)
async def get_me(user: CurrentUser):
    return user


@router.patch("", response_model=UserOut)
async def update_me(data: UserUpdate, user: CurrentUser, db: DB):
    changes = data.model_dump(exclude_unset=True)
    if "phone" in changes and changes["phone"] and changes["phone"] != user.phone:
        taken = await db.scalar(select(User.id).where(User.phone == changes["phone"], User.id != user.id))
        if taken:
            raise Conflict("Phone number already in use", code="PHONE_TAKEN")
    for key, value in changes.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("password", 10, 60))],
)
async def change_password(data: PasswordChange, user: CurrentUser, db: DB):
    if not verify_password(data.current_password, user.password_hash):
        raise Unauthorized("Current password is incorrect", code="INVALID_CREDENTIALS")
    user.password_hash = hash_password(data.new_password)
    user.token_version += 1
    await db.commit()


@router.post("/photo", response_model=UserOut)
async def upload_profile_photo(file: UploadFile, user: CurrentUser, db: DB):
    from app.modules.storage.service import get_storage, read_validated_image

    content, ext = await read_validated_image(file)
    storage = get_storage()
    stored = await storage.save(content, folder="profiles", extension=ext)
    user.profile_photo_url = stored.url
    await db.commit()
    await db.refresh(user)
    return user

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, Forbidden, Unauthorized
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.modules.users.models import User, UserRole, UserStatus
from app.modules.users.schemas import UserOut, normalize_phone

# Constant hash to equalise timing when the user doesn't exist.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def issue_tokens(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_token(user.id, "access", user.token_version),
        refresh_token=create_token(user.id, "refresh", user.token_version),
        user=UserOut.model_validate(user),
    )


async def register(db: AsyncSession, data: RegisterRequest) -> User:
    existing = await db.scalar(
        select(User).where(or_(User.email == data.email, User.phone == data.phone if data.phone else False))
    )
    if existing:
        raise Conflict("An account with this email or phone already exists", code="ACCOUNT_EXISTS")
    user = User(
        email=data.email,
        phone=data.phone,
        password_hash=hash_password(data.password),
        full_name=data.full_name.strip(),
        role=UserRole(data.role),
    )
    db.add(user)
    await db.flush()
    if user.role == UserRole.PROVIDER:
        from app.modules.providers.service import create_provider_profile

        await create_provider_profile(db, user, data.provider_type or "INDIVIDUAL", data.organization_name)
    return user


async def authenticate(db: AsyncSession, data: LoginRequest) -> User:
    identifier = data.identifier.strip()
    if "@" in identifier:
        user = await db.scalar(select(User).where(User.email == identifier.lower()))
    else:
        try:
            phone = normalize_phone(identifier)
        except ValueError:
            phone = None
        user = await db.scalar(select(User).where(User.phone == phone)) if phone else None
    if user is None:
        verify_password(data.password, _DUMMY_HASH)
        raise Unauthorized("Invalid credentials", code="INVALID_CREDENTIALS")
    if not verify_password(data.password, user.password_hash):
        raise Unauthorized("Invalid credentials", code="INVALID_CREDENTIALS")
    if user.status != UserStatus.ACTIVE:
        raise Forbidden("Account suspended", code="ACCOUNT_SUSPENDED")
    return user


async def refresh(db: AsyncSession, refresh_token: str) -> User:
    payload = decode_token(refresh_token, "refresh")
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None or user.token_version != payload.get("ver"):
        raise Unauthorized("Invalid token", code="INVALID_TOKEN")
    if user.status != UserStatus.ACTIVE:
        raise Forbidden("Account suspended", code="ACCOUNT_SUSPENDED")
    return user

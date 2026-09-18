import uuid
from datetime import timedelta
from typing import Literal

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import Unauthorized
from app.core.time import utcnow

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(user_id: uuid.UUID, token_type: TokenType, token_version: int) -> str:
    now = utcnow()
    lifetime = (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    payload = {
        "sub": str(user_id),
        "type": token_type,
        # Bumping user.token_version invalidates all outstanding tokens (logout-all, suspension).
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token expired", code="TOKEN_EXPIRED")
    except jwt.PyJWTError:
        raise Unauthorized("Invalid token", code="INVALID_TOKEN")
    if payload.get("type") != expected_type:
        raise Unauthorized("Invalid token type", code="INVALID_TOKEN")
    return payload

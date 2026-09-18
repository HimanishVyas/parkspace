from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

_engine_options: dict[str, Any] = {"echo": settings.db_echo}
if settings.environment == "test":
    # Each test may run on its own event loop; a pooled connection opened on a
    # previous loop breaks when reused, so tests hold no connections between uses.
    _engine_options["poolclass"] = NullPool
else:
    _engine_options["pool_pre_ping"] = True

engine = create_async_engine(settings.database_url, **_engine_options)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session

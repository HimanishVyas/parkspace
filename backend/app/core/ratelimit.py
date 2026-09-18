"""Fixed-window rate limiting for sensitive endpoints.

Uses Redis when REDIS_URL is configured, otherwise an in-process dictionary
(adequate for a single-instance pilot and for tests).
"""
import time
from collections import defaultdict

from fastapi import Request

from app.core.config import settings
from app.core.errors import TooManyRequests

_memory: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
_redis = None


def _get_redis():
    global _redis
    if _redis is None and settings.redis_url:
        import redis.asyncio as redis

        _redis = redis.from_url(settings.redis_url)
    return _redis


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _hit(key: str, window: int) -> int:
    r = _get_redis()
    if r is not None:
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, window)
        return int(count)
    now_window = int(time.time()) // window
    stored_window, count = _memory[key]
    if stored_window != now_window:
        count = 0
    count += 1
    _memory[key] = (now_window, count)
    return count


def rate_limit(name: str, limit: int, window_seconds: int = 60):
    """FastAPI dependency: allow `limit` requests per client IP per window."""

    async def dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        bucket = int(time.time()) // window_seconds
        key = f"rl:{name}:{_client_ip(request)}:{bucket}"
        if await _hit(key, window_seconds) > limit:
            raise TooManyRequests("Too many requests, please try again shortly")

    return dependency


def reset_memory_limits() -> None:
    _memory.clear()

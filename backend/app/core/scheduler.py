"""Background maintenance loop.

Runs booking lifecycle transitions on a timer inside the API process, which is
right for a single-instance pilot. Moving to a dedicated worker later means
calling `run_once` from there instead — nothing else changes.
"""
import asyncio
import logging

from app.core.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


async def _tick() -> None:
    from app.modules.bookings.maintenance import run_once

    async with SessionLocal() as session:
        counts = await run_once(session)
    if any(counts.values()):
        logger.info("Maintenance pass: %s", counts)


async def maintenance_loop() -> None:
    interval = max(settings.maintenance_interval_seconds, 10)
    logger.info("Maintenance loop started (every %ss)", interval)
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A failed pass must never kill the loop; the next tick retries.
            logger.exception("Maintenance pass failed")
        await asyncio.sleep(interval)


def start(app) -> asyncio.Task | None:
    if not settings.maintenance_enabled:
        logger.info("Maintenance loop disabled")
        return None
    return asyncio.create_task(maintenance_loop(), name="maintenance")


async def stop(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

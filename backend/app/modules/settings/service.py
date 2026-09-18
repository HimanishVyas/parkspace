import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationFailed
from app.modules.settings.models import PlatformSetting
from app.modules.settings.schemas import PlatformConfig, PlatformConfigUpdate


async def get_config(db: AsyncSession) -> PlatformConfig:
    rows = (await db.execute(select(PlatformSetting))).scalars().all()
    known = set(PlatformConfig.model_fields)
    stored = {r.key: r.value for r in rows if r.key in known}
    return PlatformConfig.model_validate(stored)


async def update_config(db: AsyncSession, update: PlatformConfigUpdate, actor_id: uuid.UUID) -> PlatformConfig:
    changes = update.model_dump(exclude_unset=True, exclude_none=True, mode="json")
    current = (await get_config(db)).model_dump(mode="json")
    try:
        merged = PlatformConfig.model_validate({**current, **changes})
    except ValidationError as exc:
        raise ValidationFailed("Invalid settings", details=exc.errors(include_url=False, include_context=False))
    merged_json = merged.model_dump(mode="json")
    for key in changes:
        stmt = insert(PlatformSetting).values(key=key, value=merged_json[key], updated_by_id=actor_id)
        stmt = stmt.on_conflict_do_update(
            index_elements=[PlatformSetting.key],
            set_={"value": stmt.excluded.value, "updated_by_id": actor_id},
        )
        await db.execute(stmt)
    return merged

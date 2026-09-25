"""Instance settings changed while Winnow runs (guide 8.18), over the environment's.

The registration mode and the Unpaywall email can be set in the admin panel; a value set
there wins over the environment until it is cleared.
"""

import uuid
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import InstanceSetting

Registration = Literal["open", "invite_only", "closed"]
REGISTRATION = "registration"
UNPAYWALL_EMAIL = "unpaywall_email"


async def stored(db: AsyncSession, key: str) -> Any:
    return await db.scalar(select(InstanceSetting.value).where(InstanceSetting.key == key))


async def registration_mode(db: AsyncSession, settings: Settings) -> Registration:
    value = await stored(db, REGISTRATION)
    if value in ("open", "invite_only", "closed"):
        return cast("Registration", value)
    return settings.registration


async def unpaywall_email(db: AsyncSession, settings: Settings) -> str | None:
    value = await stored(db, UNPAYWALL_EMAIL)
    return value if isinstance(value, str) and value else settings.unpaywall_email


async def store(db: AsyncSession, key: str, value: Any, by: uuid.UUID) -> None:
    """Set (or, with None, clear back to the environment's) one live setting; not committed."""
    if value is None:
        existing = await db.get(InstanceSetting, key)
        if existing is not None:
            await db.delete(existing)
        return
    statement = insert(InstanceSetting).values(key=key, value=value, updated_by=by)
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[InstanceSetting.key],
            set_={"value": statement.excluded.value, "updated_by": by},
        )
    )

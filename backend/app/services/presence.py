"""Who is screening right now (guide 8.17: "Sara is screening").

Browsers on a screening page say so every 30 seconds; a person counts as present for a
minute after the last word. Held in Redis only (nothing to keep), and it says who is
screening which stage, never which record or what they decided, so blind mode loses
nothing.
"""

import json
import time
import uuid
from typing import Any, cast

from redis.asyncio import Redis

from app.models import ScreeningStage
from app.schemas.presence import PresentMember
from app.security.permissions import ProjectAccess

KEY = "presence:{project_id}"
FRESH_SECONDS = 60
# Kept a little longer than anyone counts as present; each heartbeat renews it.
KEY_TTL_SECONDS = 120


def _key(project_id: uuid.UUID) -> str:
    return KEY.format(project_id=project_id)


async def here(redis: Redis, access: ProjectAccess, stage: ScreeningStage) -> None:
    entry = json.dumps(
        {"name": access.user.name, "stage": stage.value, "at": time.time()}, ensure_ascii=False
    )
    key = _key(access.project_id)
    async with redis.pipeline(transaction=False) as pipe:
        pipe.hset(key, str(access.user.id), entry)
        pipe.expire(key, KEY_TTL_SECONDS)
        await pipe.execute()


async def gone(redis: Redis, access: ProjectAccess) -> None:
    await cast("Any", redis.hdel(_key(access.project_id), str(access.user.id)))


async def present(redis: Redis, access: ProjectAccess) -> list[PresentMember]:
    """Everyone else screening in the review in the last minute, by name."""
    key = _key(access.project_id)
    # redis-py types commands as sync-or-async; the asyncio client always awaits.
    entries = cast("dict[str, str]", await cast("Any", redis.hgetall(key)))
    cutoff = time.time() - FRESH_SECONDS
    found, stale = [], []
    for user_id, raw in entries.items():
        try:
            entry = json.loads(raw)
        except ValueError:
            stale.append(user_id)
            continue
        if entry.get("at", 0) < cutoff:
            stale.append(user_id)
        elif user_id != str(access.user.id):
            found.append(
                PresentMember(
                    user_id=uuid.UUID(user_id),
                    name=str(entry.get("name", "")),
                    stage=ScreeningStage(entry.get("stage", ScreeningStage.TITLE_ABSTRACT)),
                )
            )
    if stale:
        await cast("Any", redis.hdel(key, *stale))
    return sorted(found, key=lambda member: member.name.casefold())

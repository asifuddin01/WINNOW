"""Live project events over Redis pub/sub, read by the SSE endpoint (guide 10, 8.3).

Events are progress, not data: an import's counts, never record contents. They are
published per project, and the SSE route only subscribes after the membership check.
"""

import json
import uuid
from typing import Any, cast

from redis.asyncio import Redis

CHANNEL = "events:project:{project_id}"
# Long enough that a browser reconnecting after a blip still catches up, short enough
# that nothing lingers: the database holds the real state.
RECENT_KEY = "events:recent:{project_id}"
RECENT_TTL_SECONDS = 300
RECENT_MAX = 50


def channel_for(project_id: uuid.UUID) -> str:
    return CHANNEL.format(project_id=project_id)


async def publish(redis: Redis, project_id: uuid.UUID, event: str, data: dict[str, Any]) -> None:
    """Send one event to whoever is watching this project right now."""
    payload = json.dumps({"event": event, **data}, default=str)
    key = RECENT_KEY.format(project_id=project_id)
    async with redis.pipeline(transaction=False) as pipe:
        pipe.publish(channel_for(project_id), payload)
        pipe.lpush(key, payload)
        pipe.ltrim(key, 0, RECENT_MAX - 1)
        pipe.expire(key, RECENT_TTL_SECONDS)
        await pipe.execute()


async def recent(redis: Redis, project_id: uuid.UUID, limit: int = 10) -> list[str]:
    """The last few events, so a page that opens mid-import is not left guessing."""
    key = RECENT_KEY.format(project_id=project_id)
    # redis-py types commands as sync-or-async; the asyncio client always awaits.
    items = cast("list[str]", await cast("Any", redis.lrange(key, 0, limit - 1)))
    return list(reversed(items))

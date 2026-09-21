"""Redis client used for sessions, rate limits, the job queue and live events."""

import asyncio
import inspect
from typing import Annotated

import structlog
from fastapi import Depends, Request
from redis.asyncio import Redis

from app.config import Settings

log = structlog.get_logger(__name__)


def create_redis(settings: Settings) -> Redis:
    client: Redis = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=5,
        health_check_interval=30,
    )
    return client


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


RedisDep = Annotated[Redis, Depends(get_redis)]


async def ping_redis(redis: Redis, limit_seconds: float = 2.0) -> bool:
    """True when Redis answers PING within `limit_seconds`."""
    try:
        async with asyncio.timeout(limit_seconds):
            # redis-py types commands as sync-or-async; the asyncio client always awaits.
            reply = redis.ping()
            if inspect.isawaitable(reply):
                reply = await reply
    except Exception as exc:  # readiness must report any failure, not raise it
        log.warning("readiness.check_failed", check="redis", error=type(exc).__name__)
        return False
    return bool(reply)

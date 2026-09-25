"""The Redis client rides out a blip instead of failing the request (Phase 9 load test)."""

from redis.exceptions import TimeoutError as RedisTimeout

from app.config import get_settings
from app.redis_client import create_redis


async def test_a_timeout_is_tried_again_before_it_fails_a_request() -> None:
    connection = create_redis(get_settings()).connection_pool.make_connection()
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RedisTimeout("connecting timed out")
        return "answered"

    async def nothing(_: Exception) -> None:
        return None

    assert await connection.retry.call_with_retry(flaky, nothing) == "answered"
    assert attempts == 3

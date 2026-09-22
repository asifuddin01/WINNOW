"""Sliding-window rate limits in Redis (guide 12.6)."""

import hashlib
import secrets
import time
from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class Limit:
    name: str
    max_hits: int
    window_seconds: int


# Sign-in limits count failed attempts only: successes and the "enter your code" step are
# free, so two-step sign-in and many people behind one university NAT are not throttled.
LOGIN_PER_ACCOUNT = Limit("login-account", 5, 60)  # per IP + email
LOGIN_PER_IP = Limit("login-ip", 20, 3600)
REGISTER_PER_IP = Limit("register-ip", 5, 3600)
PASSWORD_RESET_PER_IP = Limit("password-reset-ip", 5, 3600)
VERIFY_EMAIL_PER_IP = Limit("verify-email-ip", 20, 3600)
RESEND_VERIFICATION_PER_USER = Limit("resend-verification", 5, 3600)
API_PER_USER = Limit("api-user", 600, 60)

# Atomically: drop hits older than the window, then either record this hit or report how
# long until the oldest one expires. Returns {allowed, retry_after_ms}.
_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
if redis.call('ZCARD', key) >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  return {0, tonumber(oldest[2]) + window - now}
end
if ARGV[4] ~= '' then
  redis.call('ZADD', key, now, ARGV[4])
  redis.call('PEXPIRE', key, window)
end
return {1, 0}
"""


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._script = redis.register_script(_SLIDING_WINDOW)

    async def hit(self, limit: Limit, subject: str) -> int | None:
        """Record one hit. None if allowed, otherwise the seconds to wait."""
        return await self._run(limit, subject, record=True)

    async def check(self, limit: Limit, subject: str) -> int | None:
        """Like hit(), without recording anything: for limits that count only failures."""
        return await self._run(limit, subject, record=False)

    async def _run(self, limit: Limit, subject: str, *, record: bool) -> int | None:
        # Keys hold a hash, not the raw IP or email.
        digest = hashlib.sha256(subject.encode()).hexdigest()[:32]
        now_ms = time.time_ns() // 1_000_000
        allowed, retry_ms = await self._script(
            keys=[f"rl:{limit.name}:{digest}"],
            args=[
                now_ms,
                limit.window_seconds * 1000,
                limit.max_hits,
                f"{now_ms}-{secrets.token_hex(4)}" if record else "",
            ],
        )
        if allowed:
            return None
        return max(1, -(-int(retry_ms) // 1000))

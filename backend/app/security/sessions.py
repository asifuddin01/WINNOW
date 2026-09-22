"""Server-side sessions in Redis (guide 12.1).

The browser holds a random 256-bit id in an HttpOnly cookie. Redis stores the session under
the SHA-256 of that id, so reading Redis does not hand out working cookies. Sessions end
after SESSION_IDLE_DAYS without use or SESSION_ABSOLUTE_DAYS after sign-in, whichever
comes first.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from app.config import Settings
from app.security.tokens import hash_token

SESSION_COOKIE = "__Host-winnow_session"
TOUCH_INTERVAL = timedelta(minutes=1)  # refresh last-seen at most this often


def session_key(raw_id: str) -> str:
    return hash_token(raw_id)


@dataclass(frozen=True, slots=True)
class Session:
    key: str  # hash of the cookie value; safe to show and to use as a public id
    user_id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    ip: str | None
    user_agent: str | None


def _redis_key(key: str) -> str:
    return f"sess:{key}"


def _user_index(user_id: uuid.UUID) -> str:
    return f"user-sessions:{user_id}"


class SessionStore:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._idle = timedelta(days=settings.session_idle_days)
        self._absolute = timedelta(days=settings.session_absolute_days)

    @property
    def absolute_lifetime(self) -> timedelta:
        return self._absolute

    async def create(self, user_id: uuid.UUID, ip: str | None, user_agent: str | None) -> str:
        """Start a session and return the raw id for the cookie. Callers rotate by
        deleting the old session first (guide 12.1: new id on every sign-in)."""
        raw_id = secrets.token_urlsafe(32)
        key = session_key(raw_id)
        now = datetime.now(UTC)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(
                _redis_key(key),
                mapping={
                    "user_id": str(user_id),
                    "created_at": now.isoformat(),
                    "last_seen_at": now.isoformat(),
                    "ip": ip or "",
                    "user_agent": (user_agent or "")[:512],
                },
            )
            pipe.expire(_redis_key(key), self._idle)
            pipe.sadd(_user_index(user_id), key)
            pipe.expire(_user_index(user_id), self._absolute)
            await pipe.execute()
        return raw_id

    async def get(self, raw_id: str) -> Session | None:
        """The live session for a cookie value, refreshing its idle timer."""
        key = session_key(raw_id)
        session = await self._load(key)
        if session is None:
            return None
        now = datetime.now(UTC)
        remaining = session.created_at + self._absolute - now
        if remaining <= timedelta(0):
            await self.delete(key, session.user_id)
            return None
        if now - session.last_seen_at >= TOUCH_INTERVAL:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.hset(_redis_key(key), "last_seen_at", now.isoformat())
                pipe.expire(_redis_key(key), min(self._idle, remaining))
                await pipe.execute()
        return session

    async def list_for_user(self, user_id: uuid.UUID) -> list[Session]:
        keys: set[str] = await self._redis.smembers(_user_index(user_id))  # type: ignore[misc]
        sessions: list[Session] = []
        expired: list[str] = []
        for key in keys:
            session = await self._load(key)
            if session is None or session.user_id != user_id:
                expired.append(key)
            else:
                sessions.append(session)
        if expired:
            await self._redis.srem(_user_index(user_id), *expired)  # type: ignore[misc]
        return sorted(sessions, key=lambda s: s.last_seen_at, reverse=True)

    async def delete(self, key: str, user_id: uuid.UUID) -> None:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.delete(_redis_key(key))
            pipe.srem(_user_index(user_id), key)
            await pipe.execute()

    async def delete_all(self, user_id: uuid.UUID, keep: str | None = None) -> int:
        """End every session of a user (optionally except one). Returns how many ended."""
        keys: set[str] = await self._redis.smembers(_user_index(user_id))  # type: ignore[misc]
        doomed = [key for key in keys if key != keep]
        if doomed:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.delete(*(_redis_key(key) for key in doomed))
                pipe.srem(_user_index(user_id), *doomed)
                await pipe.execute()
        return len(doomed)

    async def _load(self, key: str) -> Session | None:
        data: dict[str, str] = await self._redis.hgetall(_redis_key(key))  # type: ignore[misc]
        if not data:
            return None
        return Session(
            key=key,
            user_id=uuid.UUID(data["user_id"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_seen_at=datetime.fromisoformat(data["last_seen_at"]),
            ip=data.get("ip") or None,
            user_agent=data.get("user_agent") or None,
        )

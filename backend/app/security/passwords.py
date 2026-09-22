"""Argon2id password hashing (guide 12.1). Hashing runs in a thread: it is deliberately slow."""

import asyncio
import secrets

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import Settings

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256


class Passwords:
    def __init__(self, settings: Settings) -> None:
        self._hasher = PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_kib,
            parallelism=settings.argon2_parallelism,
            type=Type.ID,
        )
        # Verified against when the account does not exist, so an unknown email costs
        # the same time as a wrong password (guide 12.1: constant-time responses).
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(24))

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, password_hash: str, password: str) -> bool:
        return await asyncio.to_thread(self._verify, password_hash, password)

    async def burn_time(self, password: str) -> None:
        """Spend a real verification's worth of time without checking anything."""
        await asyncio.to_thread(self._verify, self._dummy_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        """True when the stored hash used weaker or different parameters than today's."""
        return self._hasher.check_needs_rehash(password_hash)

    def _verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

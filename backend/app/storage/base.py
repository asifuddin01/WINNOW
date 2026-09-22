"""Where uploaded files live (guide 5, 12.4).

The key is random, never the name the person uploaded: a file name from the internet must
never decide a path on disk. The original name is kept in the database instead.
"""

import secrets
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

KEY_BYTES = 16


def new_key(prefix: str) -> str:
    """A random storage key under `prefix`, e.g. "imports/9f3c…"."""
    return f"{prefix.strip('/')}/{secrets.token_hex(KEY_BYTES)}"


@runtime_checkable
class Storage(Protocol):
    """What the rest of the app may ask of a storage backend."""

    async def save(self, key: str, data: AsyncIterator[bytes], limit: int) -> int:
        """Write `data` under `key`; return the size. Raise TooLarge past `limit` bytes."""

    async def read_text(self, key: str) -> str:
        """The whole file as text, decoded as UTF-8 with the usual fallbacks."""

    async def read_head(self, key: str, limit: int) -> str:
        """The first `limit` bytes as text, for previews of files too big to hold."""

    async def delete(self, key: str) -> None:
        """Remove the file; missing files are not an error."""


class TooLargeError(Exception):
    """The upload went past the size the instance allows."""

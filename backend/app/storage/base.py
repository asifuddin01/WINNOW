"""Where uploaded files live (guide 5, 12.4).

The key is random, never the name the person uploaded: a file name from the internet must
never decide a path on disk. The original name is kept in the database instead.
"""

import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
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

    async def read_bytes(self, key: str) -> bytes:
        """The whole file, for files small enough to hold (a PDF, a ZIP's entry)."""

    def iter_bytes(self, key: str) -> AsyncIterator[bytes]:
        """The file in chunks, for streaming it to a scanner or a browser."""

    async def size(self, key: str) -> int:
        """The file's size in bytes."""

    async def move(self, source: str, target: str) -> None:
        """Give the file a new key (into quarantine, or from a ZIP into place)."""

    async def stored(self) -> list["StoredFile"]:
        """Every file held, for finding the ones nothing refers to any more."""


@dataclass(frozen=True)
class StoredFile:
    key: str
    size: int
    modified: float  # seconds since the epoch


class TooLargeError(Exception):
    """The upload went past the size the instance allows."""

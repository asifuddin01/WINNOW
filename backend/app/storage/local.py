"""Files on the server's own disk, the default for a self-hosted instance (guide 16.1)."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from app.storage.base import StoredFile, TooLargeError

# Search exports are text; these are the encodings databases actually write.
ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
CHUNK = 1024 * 1024


class LocalStorage:
    """Everything under one directory, each file at its random key."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise ValueError("storage key escapes the storage root")
        return path

    async def save(self, key: str, data: AsyncIterator[bytes], limit: int) -> int:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        size = 0
        with path.open("wb") as handle:
            async for chunk in data:
                size += len(chunk)
                if size > limit:
                    await asyncio.to_thread(path.unlink, True)
                    raise TooLargeError(f"the file is larger than {limit} bytes")
                await asyncio.to_thread(handle.write, chunk)
        return size

    async def read_text(self, key: str) -> str:
        return await asyncio.to_thread(self._read_text, key)

    async def read_head(self, key: str, limit: int) -> str:
        return await asyncio.to_thread(self._read_text, key, limit)

    def _read_text(self, key: str, limit: int | None = None) -> str:
        path = self._path(key)
        if limit is None:
            raw = path.read_bytes()
        else:
            with path.open("rb") as handle:
                raw = handle.read(limit)
        for encoding in ENCODINGS:
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, True)

    async def read_bytes(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def iter_bytes(self, key: str) -> AsyncIterator[bytes]:
        handle = await asyncio.to_thread(self._path(key).open, "rb")
        try:
            while chunk := await asyncio.to_thread(handle.read, CHUNK):
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)

    async def size(self, key: str) -> int:
        return (await asyncio.to_thread(self._path(key).stat)).st_size

    async def stored(self) -> list[StoredFile]:
        return await asyncio.to_thread(self._stored)

    def _stored(self) -> list[StoredFile]:
        if not self._root.is_dir():
            return []
        found = []
        for path in self._root.rglob("*"):
            if path.is_file():
                info = path.stat()
                found.append(
                    StoredFile(
                        key=path.relative_to(self._root).as_posix(),
                        size=info.st_size,
                        modified=info.st_mtime,
                    )
                )
        return found

    async def move(self, source: str, target: str) -> None:
        destination = self._path(target)
        await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self._path(source).replace, destination)

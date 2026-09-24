"""Stored files that no row refers to any more.

The app removes a file when it removes the row that names it (a replaced PDF, a discarded
ZIP, an undone import). Rows deleted another way — by an operator in SQL, or a deleted
test review — leave their files behind. `python -m app.cli sweep-files` finds them.
Files newer than the age given are never touched: an upload is stored a moment before
its row is committed.
"""

import time
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Fulltext, FulltextBatch, ImportBatch
from app.storage.base import Storage, StoredFile


@dataclass(frozen=True)
class Sweep:
    files: list[StoredFile]

    @property
    def size(self) -> int:
        return sum(file.size for file in self.files)


async def referenced(db: AsyncSession) -> set[str]:
    """Every storage key a row names."""
    keys = set(await db.scalars(select(ImportBatch.file_key)))
    keys |= set(await db.scalars(select(Fulltext.file_key)))
    for zip_key, entries in await db.execute(select(FulltextBatch.zip_key, FulltextBatch.entries)):
        if zip_key:
            keys.add(zip_key)
        keys |= {entry["key"] for entry in entries if entry.get("key")}
    return keys


async def sweep(db: AsyncSession, storage: Storage, *, older_than: timedelta, apply: bool) -> Sweep:
    """The unreferenced files older than `older_than`; removed when `apply`."""
    keys = await referenced(db)
    cutoff = time.time() - older_than.total_seconds()
    orphans = [
        file for file in await storage.stored() if file.key not in keys and file.modified < cutoff
    ]
    if apply:
        for file in orphans:
            await storage.delete(file.key)
    return Sweep(orphans)

"""Finding and removing stored files no row refers to (`python -m app.cli sweep-files`)."""

import os
import time
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli
from app.models import Fulltext, FulltextSource, ScanStatus
from app.models.base import uuid7
from app.storage import LocalStorage
from app.storage.sweep import sweep
from tests.conftest import MemoryMailer
from tests.screening_helpers import team


async def one(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def test_only_old_unreferenced_files_are_swept(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path)
    for key in ("fulltexts/kept", "fulltexts/orphan", "fulltext-zips/fresh-orphan"):
        await storage.save(key, one(b"%PDF-1.4"), 100)
    old = time.time() - 2 * 24 * 3600
    for key in ("fulltexts/kept", "fulltexts/orphan"):
        os.utime(tmp_path / key, (old, old))

    async with team(db_app, db, mailer, records=1) as t:
        db.add(
            Fulltext(
                id=uuid7(),
                project_id=uuid.UUID(t.pid),
                record_id=t.records[0],
                file_key="fulltexts/kept",
                filename="kept.pdf",
                size_bytes=8,
                sha256="0" * 64,
                scan_status=ScanStatus.CLEAN,
                source=FulltextSource.UPLOAD,
            )
        )
        await db.flush()

        found = await sweep(db, storage, older_than=timedelta(days=1), apply=False)
        assert [file.key for file in found.files] == ["fulltexts/orphan"]
        assert found.size == 8
        assert await storage.size("fulltexts/orphan") == 8  # a report removes nothing

        await sweep(db, storage, older_than=timedelta(days=1), apply=True)
        keys = sorted(file.key for file in await storage.stored())
        assert keys == ["fulltext-zips/fresh-orphan", "fulltexts/kept"]


def test_the_command_reports_unless_told_to_remove(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[bool, timedelta]] = []

    async def fake(*, apply: bool, older_than: timedelta) -> None:
        calls.append((apply, older_than))

    monkeypatch.setattr(cli, "sweep_files", fake)
    assert cli.main(["sweep-files"]) == 0
    assert cli.main(["sweep-files", "--apply", "--older-than-minutes", "5"]) == 0
    assert calls == [(False, timedelta(days=1)), (True, timedelta(minutes=5))]

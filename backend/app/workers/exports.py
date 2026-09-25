"""Building exports and backups in the worker (guide 8.16).

The job acts for the person who asked: their membership is checked again when it runs
(they may have left), and its database session runs as them, under row-level security,
as a request would. Files go to storage for a day, then are removed.
"""

import asyncio
import csv
import os
import re
import tempfile
import unicodedata
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from arq.connections import ArqRedis
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import Cell
from openpyxl.styles import Font
from openpyxl.worksheet._write_only import WriteOnlyWorksheet
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import act_for
from app.exports import BibtexWriter, ExportRecord, write_ris
from app.models import (
    ExportFormat,
    ExportJob,
    ExportKind,
    JobStatus,
    ProjectRole,
    RestoreJob,
    User,
)
from app.security.permissions import ProjectAccess, check_project_role
from app.services import audit, events
from app.services.audit import Actor
from app.services.blinding import sees_others
from app.services.errors import DomainError
from app.services.export_records import RecordFilters, headers, record_rows
from app.spreadsheet import safe_cell
from app.storage import Storage, new_key

log = structlog.get_logger(__name__)

KEEP = timedelta(days=1)
FILE_LIMIT = 4 * 1024**3
CHUNK = 1024 * 1024


class ExportFailedError(Exception):
    """The export cannot be made; the message is for the person who asked."""


async def run_export(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    storage: Storage,
    export_id: uuid.UUID,
) -> JobStatus | None:
    async with sessionmaker() as db:
        job = await db.get(ExportJob, export_id)
        if job is None or job.status is not JobStatus.QUEUED or job.requested_by is None:
            return None
        project_id, user_id = job.project_id, job.requested_by
        job.status = JobStatus.RUNNING
        await db.commit()
    await _tell(redis, project_id, export_id, JobStatus.RUNNING)

    try:
        async with sessionmaker() as db:
            act_for(db, user_id)
            user = await db.get(User, user_id)
            if user is None or user.deleted_at is not None:
                raise ExportFailedError("The account that asked for this export is gone.")
            try:
                minimum = ProjectRole.OWNER if job.kind is ExportKind.BACKUP else ProjectRole.VIEWER
                access = await check_project_role(db, user, project_id, minimum)
            except DomainError as error:
                raise ExportFailedError(
                    "You are no longer allowed to export this review."
                ) from error
            if job.kind is ExportKind.BACKUP:
                from app.backup.dump import write_backup  # the backup format's own module

                path, rows = await write_backup(db, storage, access)
                suffix = "backup.zip"
            else:
                path, rows = await _write_records(db, redis, access, job)
                suffix = (
                    f"records.{'bib' if job.format is ExportFormat.BIBTEX else job.format.value}"
                )
            key = new_key("exports")
            try:
                size = await storage.save(key, _chunks(path), FILE_LIMIT)
            finally:
                path.unlink(missing_ok=True)
            filename = f"{_slug(access.project.title)}-{datetime.now(UTC):%Y-%m-%d}-{suffix}"
    except ExportFailedError as error:
        await _finish(sessionmaker, export_id, status=JobStatus.FAILED, problem=str(error))
        await _tell(redis, project_id, export_id, JobStatus.FAILED)
        return JobStatus.FAILED
    except Exception:
        log.exception("export.failed", export_id=str(export_id))
        await _finish(
            sessionmaker,
            export_id,
            status=JobStatus.FAILED,
            problem="The export could not be made. Try again, or ask the instance's administrator.",
        )
        await _tell(redis, project_id, export_id, JobStatus.FAILED)
        return JobStatus.FAILED

    await _finish(
        sessionmaker,
        export_id,
        status=JobStatus.READY,
        file_key=key,
        filename=filename,
        size_bytes=size,
        rows=rows,
        expires_at=datetime.now(UTC) + KEEP,
    )
    await _tell(redis, project_id, export_id, JobStatus.READY)
    return JobStatus.READY


async def _finish(
    sessionmaker: async_sessionmaker[AsyncSession], export_id: uuid.UUID, **values: object
) -> None:
    async with sessionmaker() as db:
        job = await db.get(ExportJob, export_id)
        if job is None:
            return
        for name, value in values.items():
            setattr(job, name, value)
        await db.commit()


async def _tell(
    redis: Redis, project_id: uuid.UUID, export_id: uuid.UUID, status: JobStatus
) -> None:
    await events.publish(
        redis, project_id, "export", {"export_id": str(export_id), "status": status.value}
    )


async def _write_records(
    db: AsyncSession, redis: Redis, access: ProjectAccess, job: ExportJob
) -> tuple[Path, int]:
    filters = RecordFilters(
        q=str(job.filters.get("q", "")),
        status=job.filters.get("status"),
        full_text=job.filters.get("full_text"),
        batch=uuid.UUID(job.filters["batch"]) if job.filters.get("batch") else None,
        duplicates=bool(job.filters.get("duplicates", False)),
    )
    blind = not sees_others(access)
    columns = headers(blind=blind, duplicates=filters.duplicates)
    rows = record_rows(db, redis, access, filters)
    if job.format is ExportFormat.CSV:
        return await _csv(columns, rows)
    if job.format is ExportFormat.XLSX:
        return await _xlsx(columns, rows)
    if job.format in (ExportFormat.RIS, ExportFormat.BIBTEX):
        return await _citations(job.format, rows, mine=blind)
    raise ExportFailedError(f"Records cannot be exported as {job.format.value}.")


def _flat(value: object) -> object:
    """A list in one spreadsheet cell: its items joined with semicolons."""
    return "; ".join(str(item) for item in value) if isinstance(value, list | tuple) else value


def _citation(row: dict[str, object], *, mine: bool) -> ExportRecord:
    def text(name: str) -> str | None:
        value = row.get(name)
        return str(value) if value not in (None, "") else None

    def items(name: str) -> tuple[str, ...]:
        value = row.get(name)
        return tuple(str(item) for item in value) if isinstance(value, list | tuple) else ()

    year = row.get("year")
    return ExportRecord(
        id=str(row["id"]),
        title=text("title"),
        abstract=text("abstract"),
        authors=items("authors"),
        year=year if isinstance(year, int) else None,
        journal=text("journal"),
        volume=text("volume"),
        issue=text("issue"),
        pages=text("pages"),
        doi=text("doi"),
        pmid=text("pmid"),
        pmcid=text("pmcid"),
        url=text("url"),
        keywords=items("keywords"),
        publication_type=items("publication_type"),
        language=text("language"),
        database=text("database"),
        ta_status=text("ta_status"),
        ft_status=text("ft_status"),
        ta_reasons=items("ta_reasons"),
        ft_reasons=items("ft_reasons"),
        labels=items("labels"),
        mine=mine,
    )


async def _citations(
    format_: ExportFormat, batches: AsyncIterator[list[dict[str, object]]], *, mine: bool
) -> tuple[Path, int]:
    """RIS or BibTeX, written a batch at a time (BibTeX keys stay unique across batches)."""
    path = _temporary(".ris" if format_ is ExportFormat.RIS else ".bib")
    bibtex = BibtexWriter()
    count = 0
    # RIS carries its own CRLF line ends: no newline translation.
    with path.open("w", encoding="utf-8", newline="") as handle:
        async for batch in batches:
            records = [_citation(row, mine=mine) for row in batch]
            text = write_ris(records) if format_ is ExportFormat.RIS else bibtex.write(records)
            await asyncio.to_thread(handle.write, text)
            count += len(batch)
    return path, count


def _temporary(suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix="winnow-export-", suffix=suffix)
    os.close(descriptor)
    return Path(name)


async def _csv(
    columns: list[tuple[str, str]], batches: AsyncIterator[list[dict[str, object]]]
) -> tuple[Path, int]:
    path = _temporary(".csv")
    count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([heading for _, heading in columns])
        async for batch in batches:
            await asyncio.to_thread(
                writer.writerows,
                [[safe_cell(_flat(row[field])) for field, _ in columns] for row in batch],
            )
            count += len(batch)
    return path, count


def _text_cell(sheet: WriteOnlyWorksheet, value: object, *, bold: bool = False) -> Cell:
    plain: str | float | None = (
        value
        if isinstance(value, int | float) and not isinstance(value, bool)
        else None
        if value is None or value == ""
        else str(value)
    )
    cell = WriteOnlyCell(sheet, value=plain)
    if isinstance(plain, str):
        cell.data_type = "s"  # text, even when it starts with "=": never a formula
    if bold:
        cell.font = Font(bold=True)
    return cell


async def _xlsx(
    columns: list[tuple[str, str]], batches: AsyncIterator[list[dict[str, object]]]
) -> tuple[Path, int]:
    path = _temporary(".xlsx")
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Records")
    sheet.freeze_panes = "A2"
    sheet.append([_text_cell(sheet, heading, bold=True) for _, heading in columns])
    count = 0

    def add(batch: list[dict[str, object]]) -> None:
        for row in batch:
            sheet.append([_text_cell(sheet, _flat(row[field])) for field, _ in columns])

    async for batch in batches:
        await asyncio.to_thread(add, batch)
        count += len(batch)
    await asyncio.to_thread(workbook.save, path)
    return path, count


async def _chunks(path: Path) -> AsyncIterator[bytes]:
    with path.open("rb") as handle:
        while chunk := await asyncio.to_thread(handle.read, CHUNK):
            yield chunk


def _slug(title: str) -> str:
    plain = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:50] or "review"


async def purge_expired(*, sessionmaker: async_sessionmaker[AsyncSession], storage: Storage) -> int:
    """Exports older than a day go, files and all (failed ones too)."""
    cutoff = datetime.now(UTC)
    async with sessionmaker() as db:
        old = list(
            await db.scalars(
                select(ExportJob).where(
                    (ExportJob.expires_at < cutoff)
                    | (
                        ExportJob.status.in_([JobStatus.FAILED, JobStatus.QUEUED])
                        & (ExportJob.created_at < cutoff - KEEP)
                    )
                )
            )
        )
        for job in old:
            if job.file_key:
                await storage.delete(job.file_key)
        if old:
            await db.execute(delete(ExportJob).where(ExportJob.id.in_([job.id for job in old])))
        await db.commit()
        return len(old)


async def run_restore(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    queue: ArqRedis,
    storage: Storage,
    settings: Settings,
    restore_id: uuid.UUID,
) -> JobStatus | None:
    """Turn an uploaded backup into a new review, all at once or not at all."""
    from app.backup.restore import pending_scans, restore_backup
    from app.backup.spec import BackupFormatError
    from app.services.fulltext import SCAN_JOB

    async with sessionmaker() as db:
        job = await db.get(RestoreJob, restore_id)
        if job is None or job.status is not JobStatus.QUEUED or job.zip_key is None:
            return None
        user = await db.get(User, job.user_id)
        zip_key = job.zip_key
        job.status = JobStatus.RUNNING
        await db.commit()
    path = _temporary(".zip")
    try:
        with path.open("wb") as handle:
            async for chunk in storage.iter_bytes(zip_key):
                await asyncio.to_thread(handle.write, chunk)
        async with sessionmaker() as db:
            if user is None or user.deleted_at is not None:
                raise BackupFormatError("The account that uploaded this backup is gone.")
            project_id, counts = await restore_backup(
                db,
                storage,
                user,
                path,
                max_bytes=settings.max_backup_mb * 1024 * 1024,
                scanning=bool(settings.clamav_host),
            )
            audit.record(
                db,
                "project.restored",
                Actor(),
                user_id=user.id,
                project_id=project_id,
                entity_type="project",
                entity_id=project_id,
                after={"rows": counts},
            )
            await db.commit()
            scans = await pending_scans(db, project_id)
    except BackupFormatError as error:
        await _finish_restore(sessionmaker, restore_id, status=JobStatus.FAILED, problem=str(error))
        return JobStatus.FAILED
    except Exception:
        log.exception("restore.failed", restore_id=str(restore_id))
        await _finish_restore(
            sessionmaker,
            restore_id,
            status=JobStatus.FAILED,
            problem="The backup could not be restored. Nothing was kept.",
        )
        return JobStatus.FAILED
    finally:
        path.unlink(missing_ok=True)
        await storage.delete(zip_key)
    for fulltext_id in scans:
        await queue.enqueue_job(SCAN_JOB, str(fulltext_id), _job_id=f"scan:{fulltext_id}")
    await _finish_restore(
        sessionmaker,
        restore_id,
        status=JobStatus.READY,
        project_id=project_id,
        restored=counts,
        zip_key=None,
    )
    return JobStatus.READY


async def _finish_restore(
    sessionmaker: async_sessionmaker[AsyncSession], restore_id: uuid.UUID, **values: object
) -> None:
    async with sessionmaker() as db:
        job = await db.get(RestoreJob, restore_id)
        if job is None:
            return
        for name, value in values.items():
            setattr(job, name, value)
        job.zip_key = None
        await db.commit()

"""Uploading, previewing, running and undoing an import (guide 8.3).

The upload is written straight to storage under a random key and parsed only far enough to
show a preview; the real work happens in the worker after the person confirms.
"""

import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from itertools import islice
from typing import Any

from arq.connections import ArqRedis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import FileFormat, ImportBatch, ImportStatus, Record
from app.parsers import ParsedRecord, ParseProblem, csv_parser, detect, parse
from app.schemas.imports import (
    ConfirmImport,
    ImportMeta,
    ImportOut,
    ImportPreview,
    ImportUpload,
    RecordPreview,
    RejectedFile,
    problems_of,
)
from app.security.permissions import ProjectAccess
from app.services import audit
from app.services.audit import Actor
from app.services.errors import ConflictError, DomainError, NotFoundError
from app.storage import Storage, TooLargeError, new_key

# Enough of the file to detect the format and show five records, whatever its size.
HEAD_BYTES = 512 * 1024
PREVIEW_RECORDS = 5
PREVIEW_PROBLEMS = 20
MEGABYTE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class UploadedFile:
    """One file out of an upload, still streaming."""

    filename: str
    chunks: AsyncIterator[bytes]
    database_name: str | None = None


class UnknownFormatError(DomainError):
    status = 415
    code = "unknown_format"
    message = (
        "Winnow could not read that file. It reads RIS, BibTeX, PubMed NBIB, PubMed XML, "
        "EndNote XML and CSV exports."
    )


class FileTooLargeError(DomainError):
    status = 413
    code = "file_too_large"


class TooManyFilesError(DomainError):
    status = 400
    code = "too_many_files"


class ImportService:
    def __init__(
        self, db: AsyncSession, settings: Settings, storage: Storage, queue: ArqRedis
    ) -> None:
        self._db = db
        self._settings = settings
        self._storage = storage
        self._queue = queue

    # --- Uploading ---------------------------------------------------------------------

    async def upload(
        self,
        access: ProjectAccess,
        *,
        filename: str,
        chunks: AsyncIterator[bytes],
        meta: ImportMeta,
        actor: Actor,
    ) -> ImportBatch:
        """Store the file, work out what it is, and record the batch as queued."""
        key = new_key(f"imports/{access.project_id}")
        head = bytearray()

        async def tee() -> AsyncIterator[bytes]:
            async for chunk in chunks:
                if len(head) < HEAD_BYTES:
                    head.extend(chunk[: HEAD_BYTES - len(head)])
                yield chunk

        limit = self._settings.max_upload_mb * MEGABYTE
        try:
            size = await self._storage.save(key, tee(), limit)
        except TooLargeError as error:
            raise FileTooLargeError(
                f"That file is larger than this instance allows "
                f"({self._settings.max_upload_mb} MB)."
            ) from error
        if size == 0:
            await self._storage.delete(key)
            raise UnknownFormatError("That file is empty.")

        file_format = detect(filename, _decode(bytes(head)))
        if file_format is None:
            await self._storage.delete(key)
            raise UnknownFormatError
        batch = ImportBatch(
            project_id=access.project_id,
            source_name=meta.source_name or filename,
            database_name=meta.database_name,
            file_key=key,
            filename=filename[:255],
            size_bytes=size,
            file_format=FileFormat(file_format),
            status=ImportStatus.QUEUED,
            search_date=meta.search_date,
            search_string=meta.search_string,
            created_by=access.user.id,
        )
        self._db.add(batch)
        await self._db.flush()
        audit.record(
            self._db,
            "import.uploaded",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="import",
            entity_id=batch.id,
            after={"filename": batch.filename, "format": file_format, "bytes": size},
        )
        await self._db.commit()
        await self._db.refresh(batch)
        return batch

    async def upload_all(
        self,
        access: ProjectAccess,
        files: Sequence[UploadedFile],
        *,
        meta: ImportMeta,
        actor: Actor,
    ) -> ImportUpload:
        """Take a whole drop of search exports (guide 8.3).

        Each file becomes its own batch, because PRISMA counts each search separately and
        an undo has to be able to take one file back out. A file Winnow cannot read is
        reported beside the others rather than failing the upload.
        """
        limit = self._settings.max_upload_files
        if len(files) > limit:
            raise TooManyFilesError(f"That is more than {limit} files. Upload them in batches.")
        batches: list[ImportOut] = []
        rejected: list[RejectedFile] = []
        for item in files:
            database = item.database_name or meta.database_name
            # One name per file, so the history and PRISMA can tell eleven exports from
            # one database apart; a single file may keep the name the person gave it.
            named = meta.source_name if meta.source_name and len(files) == 1 else None
            file_meta = meta.model_copy(
                update={
                    "database_name": database,
                    "source_name": named or _source_name(database, item.filename),
                }
            )
            try:
                batch = await self.upload(
                    access, filename=item.filename, chunks=item.chunks, meta=file_meta, actor=actor
                )
            except DomainError as error:
                rejected.append(RejectedFile(filename=item.filename, reason=error.detail))
                continue
            batches.append(out(batch))
        if not batches and rejected:
            raise UnknownFormatError(rejected[0].reason)
        return ImportUpload(batches=batches, rejected=rejected)

    # --- Reading -----------------------------------------------------------------------

    async def batch(self, access: ProjectAccess, batch_id: uuid.UUID) -> ImportBatch:
        batch = await self._db.scalar(
            select(ImportBatch).where(
                ImportBatch.id == batch_id, ImportBatch.project_id == access.project_id
            )
        )
        if batch is None:
            raise NotFoundError("That import no longer exists.")
        return batch

    async def history(self, access: ProjectAccess) -> list[ImportOut]:
        rows = await self._db.scalars(
            select(ImportBatch)
            .where(ImportBatch.project_id == access.project_id)
            .order_by(ImportBatch.id.desc())
            .limit(200)
        )
        return [out(batch) for batch in rows]

    async def preview(self, access: ProjectAccess, batch_id: uuid.UUID) -> ImportPreview:
        """The first few records as Winnow reads them, plus CSV's column mapping."""
        batch = await self.batch(access, batch_id)
        # The head is enough for five records and the column names, whatever the size.
        text = await self._storage.read_head(batch.file_key, HEAD_BYTES)
        records: list[RecordPreview] = []
        problems: list[dict[str, Any]] = []
        for item in islice(parse(batch.file_format.value, text, batch.column_mapping), 500):
            if isinstance(item, ParsedRecord) and len(records) < PREVIEW_RECORDS:
                records.append(_preview_of(item))
            elif isinstance(item, ParseProblem) and len(problems) < PREVIEW_PROBLEMS:
                problems.append({"at": item.at, "unit": item.unit, "reason": item.reason})
            if len(records) >= PREVIEW_RECORDS and len(problems) >= PREVIEW_PROBLEMS:
                break
        columns: list[str] = []
        suggested: dict[str, str] = {}
        rows: list[dict[str, str]] = []
        if batch.file_format is FileFormat.CSV:
            columns = csv_parser.columns_of(text)
            suggested = batch.column_mapping or csv_parser.suggest_mapping(columns)
            rows = csv_parser.sample_rows(text, PREVIEW_RECORDS)
        return ImportPreview(
            batch=out(batch),
            records=records,
            problems=problems_of(problems),
            columns=columns,
            suggested_mapping=suggested,
            sample_rows=rows,
        )

    # --- Running and undoing -----------------------------------------------------------

    async def confirm(
        self, access: ProjectAccess, batch_id: uuid.UUID, body: ConfirmImport, actor: Actor
    ) -> tuple[ImportBatch, str | None]:
        """Hand the batch to the worker. Confirming twice is refused, not repeated."""
        batch = await self.batch(access, batch_id)
        if batch.status is not ImportStatus.QUEUED:
            raise ConflictError("This import has already been started.")
        # Out of "queued" here, not when the worker picks it up: otherwise a second
        # confirm in the meantime would import the file twice.
        batch.status = ImportStatus.PARSING
        batch.source_name = body.source_name or batch.source_name
        batch.database_name = body.database_name or batch.database_name
        batch.search_date = body.search_date or batch.search_date
        batch.search_string = body.search_string or batch.search_string
        if body.column_mapping is not None:
            batch.column_mapping = body.column_mapping
        audit.record(
            self._db,
            "import.started",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="import",
            entity_id=batch.id,
            after={"database": batch.database_name, "source": batch.source_name},
        )
        await self._db.commit()
        await self._db.refresh(batch)
        from app.workers.settings import IMPORT_RECORDS_JOB

        job = await self._queue.enqueue_job(IMPORT_RECORDS_JOB, str(batch.id))
        return batch, job.job_id if job else None

    async def undo(self, access: ProjectAccess, batch_id: uuid.UUID, actor: Actor) -> int:
        """Remove an import and the records it brought in (guide 8.3)."""
        batch = await self.batch(access, batch_id)
        if batch.status is ImportStatus.PARSING:
            raise ConflictError("This import is still running. Wait for it to finish.")
        count = await self._db.scalar(
            select(func.count()).select_from(Record).where(Record.import_batch_id == batch.id)
        )
        await self._db.execute(delete(ImportBatch).where(ImportBatch.id == batch.id))
        await self._storage.delete(batch.file_key)
        audit.record(
            self._db,
            "import.undone",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="import",
            entity_id=batch.id,
            before={"filename": batch.filename, "records": count or 0},
        )
        await self._db.commit()
        return count or 0


def _source_name(database: str, filename: str) -> str:
    """What this search is called in the history and in PRISMA."""
    stem = filename.rsplit(".", 1)[0][:80]
    return f"{database} · {stem}"[:200]


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _preview_of(record: ParsedRecord) -> RecordPreview:
    return RecordPreview(
        title=record.title,
        authors=record.authors[:10],
        year=record.year,
        journal=record.journal,
        doi=record.doi,
        pmid=record.pmid,
        abstract=(record.abstract or "")[:400] or None,
    )


def out(batch: ImportBatch) -> ImportOut:
    return ImportOut(
        id=batch.id,
        filename=batch.filename,
        file_format=batch.file_format,
        status=batch.status,
        source_name=batch.source_name,
        database_name=batch.database_name,
        search_date=batch.search_date,
        search_string=batch.search_string,
        size_bytes=batch.size_bytes,
        total=batch.total,
        imported=batch.imported,
        problems=problems_of(batch.errors or []),
        created_at=batch.created_at,
        updated_at=batch.updated_at,
    )

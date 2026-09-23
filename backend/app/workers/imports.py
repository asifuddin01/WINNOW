"""The import job: parse an uploaded file and COPY its records in (guide 8.3, 13).

Runs in the worker, never in a request. Records go in through PostgreSQL's COPY in
batches, progress is published as each batch lands, and a record that cannot be read is
collected as a problem rather than failing the import.
"""

import json
import uuid
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from typing import Any

import structlog
from arq.connections import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import COPY_COLUMNS, ImportBatch, ImportStatus, Project, ScreeningStage
from app.models.base import uuid7
from app.parsers import ParsedRecord, ParseProblem, parse
from app.parsers.xml_reader import MalformedXMLError
from app.schemas.projects import ProjectSettings
from app.services import events
from app.storage import Storage

log = structlog.get_logger(__name__)

# Rows per COPY: few enough round trips for 100k records, flat memory, visible progress.
BATCH_ROWS = 1_000
# What the import report keeps. The count of the rest is kept as well.
MAX_PROBLEMS = 200


def record_row(
    record: ParsedRecord, project_id: uuid.UUID, batch_id: uuid.UUID | None, now: datetime
) -> tuple[Any, ...]:
    """One record as a COPY tuple. `batch_id` is None for generated data (make seed-large)."""
    return (
        uuid7(),
        project_id,
        batch_id,
        record.title,
        record.abstract,
        record.authors,
        record.year,
        record.journal,
        record.volume,
        record.issue,
        record.pages,
        record.doi,
        record.pmid,
        record.pmcid,
        record.isbn,
        record.url,
        record.keywords,
        record.language,
        record.publication_type,
        json.dumps(record.raw, ensure_ascii=False),
        record.title_norm,
        record.doi_norm,
        now,
        now,
    )


async def copy_records(
    sessionmaker: async_sessionmaker[AsyncSession], rows: list[tuple[Any, ...]]
) -> None:
    """One COPY of a batch of rows straight into `records` (guide 13).

    It goes through a session rather than the engine so that it shares whatever connection
    the session has — which is what lets the tests run an import inside their transaction.
    """
    async with sessionmaker() as session:
        connection = await session.connection()
        raw = await connection.get_raw_connection()
        asyncpg_connection = raw.driver_connection
        if asyncpg_connection is None:  # pragma: no cover - only if the driver changes
            raise RuntimeError("COPY needs the asyncpg connection behind SQLAlchemy")
        await asyncpg_connection.copy_records_to_table(
            "records", records=rows, columns=list(COPY_COLUMNS)
        )
        await session.commit()


def _batched(items: Iterable[Any], size: int) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


async def run_import(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    storage: Storage,
    batch_id: uuid.UUID,
    queue: ArqRedis | None = None,
) -> dict[str, int]:
    """Parse the batch's file and load it. Returns what it read and what it could not.

    The file is read once, parsed as a stream and written in batches of BATCH_ROWS, so
    memory stays flat whatever the file's size.
    """
    async with sessionmaker() as session:
        batch = await session.get(ImportBatch, batch_id)
        if batch is None or batch.status is ImportStatus.DONE:
            return {"imported": 0, "problems": 0}
        project_id, file_key, file_format = batch.project_id, batch.file_key, batch.file_format
        mapping = batch.column_mapping
        batch.status = ImportStatus.PARSING
        await session.commit()

    await events.publish(
        redis, project_id, "import.started", {"batch_id": str(batch_id), "imported": 0}
    )
    problems: list[dict[str, Any]] = []
    imported = 0
    failure: str | None = None
    now = datetime.now(UTC)
    try:
        text = await storage.read_text(file_key)
        stream = parse(file_format.value, text, mapping)
        for chunk in _batched(stream, BATCH_ROWS):
            records = [item for item in chunk if isinstance(item, ParsedRecord)]
            for item in chunk:
                if isinstance(item, ParseProblem) and len(problems) < MAX_PROBLEMS:
                    problems.append({"at": item.at, "unit": item.unit, "reason": item.reason})
                elif isinstance(item, ParseProblem):
                    problems.append({"at": item.at, "unit": item.unit, "reason": "…"})
            if records:
                await copy_records(
                    sessionmaker, [record_row(r, project_id, batch_id, now) for r in records]
                )
                imported += len(records)
            await _progress(sessionmaker, redis, batch_id, project_id, imported, len(problems))
    except (MalformedXMLError, UnicodeDecodeError, ValueError) as error:
        failure = f"{type(error).__name__}: {error}"
        log.warning("import.failed", batch_id=str(batch_id), error=type(error).__name__)

    async with sessionmaker() as session:
        batch = await session.get(ImportBatch, batch_id)
        if batch is not None:
            batch.status = ImportStatus.FAILED if failure else ImportStatus.DONE
            batch.imported = imported
            batch.total = imported + len(problems)
            kept = problems[:MAX_PROBLEMS]
            if failure:
                kept = [{"at": 0, "unit": "file", "reason": failure}, *kept]
            batch.errors = kept
            await session.commit()
    if not failure and imported and queue is not None:
        await _dedup_if_wanted(sessionmaker, queue, project_id)
    await events.publish(
        redis,
        project_id,
        "import.failed" if failure else "import.finished",
        {
            "batch_id": str(batch_id),
            "imported": imported,
            "problems": len(problems),
            "reason": failure,
        },
    )
    return {"imported": imported, "problems": len(problems)}


async def _dedup_if_wanted(
    sessionmaker: async_sessionmaker[AsyncSession],
    queue: ArqRedis,
    project_id: uuid.UUID,
) -> None:
    """Guide 8.4: look for duplicates as soon as an import lands, if the review wants it,
    and rank the new records."""
    from app.services.dedup import SETTLE_SECONDS, enqueue_dedup

    async with sessionmaker() as session:
        raw = await session.scalar(select(Project.settings).where(Project.id == project_id))
    settings = ProjectSettings.model_validate(raw or {})
    if settings.dedup_on_import:
        await enqueue_dedup(queue, project_id, settle=SETTLE_SECONDS)
    if settings.ranking_enabled:
        # New records have no score yet: rank them in with the rest (guide 8.10). The job
        # does nothing until the review has enough decisions for a model.
        from app.services.ranking import SETTLE_SECONDS as RANK_SETTLE
        from app.services.ranking import enqueue_ranking

        await enqueue_ranking(queue, project_id, ScreeningStage.TITLE_ABSTRACT, defer=RANK_SETTLE)


async def _progress(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    batch_id: uuid.UUID,
    project_id: uuid.UUID,
    imported: int,
    problems: int,
) -> None:
    async with sessionmaker() as session:
        batch = await session.get(ImportBatch, batch_id)
        if batch is not None:
            batch.imported = imported
            await session.commit()
    await events.publish(
        redis,
        project_id,
        "import.progress",
        {"batch_id": str(batch_id), "imported": imported, "problems": problems},
    )

"""Full-text jobs (guide 8.8, 12.4): scanning a PDF before anyone can open it, and
unpacking a ZIP of PDFs and matching each to a record.

A PDF the scanner flags is moved to `quarantine/`, marked infected, and the review's owners
and admins are emailed. A clean PDF (or any PDF, on an instance without a scanner) has its
text and page count read for search and keyword highlighting.
"""

import asyncio
import hashlib
import io
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from arq import Retry
from arq.connections import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.email.mailer import SEND_EMAIL_JOB
from app.email.messages import pdf_quarantined
from app.fulltext import zipcheck
from app.fulltext.matching import Matcher, Outcome, RecordKeys
from app.fulltext.pdf import looks_like_pdf, read_text
from app.models import (
    BatchStatus,
    Fulltext,
    FulltextBatch,
    Project,
    ProjectMember,
    ProjectRole,
    Record,
    ScanStatus,
    TitleAbstractStatus,
    User,
)
from app.security import clamav
from app.services import audit, events
from app.services.audit import Actor
from app.services.fulltext import discard
from app.storage import Storage, new_key

log = structlog.get_logger(__name__)

SCAN_TRIES = 6
# Pieces of a ZIP nobody confirmed are removed after this long.
BATCH_KEEP = timedelta(days=1)


@dataclass(frozen=True)
class ScanOutcome:
    status: ScanStatus
    pages: int | None = None


async def run_scan(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    queue: ArqRedis,
    storage: Storage,
    settings: Settings,
    fulltext_id: uuid.UUID,
    attempt: int,
) -> ScanOutcome | None:
    async with sessionmaker() as db:
        row = await db.get(Fulltext, fulltext_id)
        if row is None:
            return None
        if row.scan_status in (ScanStatus.PENDING, ScanStatus.ERROR) and settings.clamav_host:
            try:
                result = await clamav.scan(
                    settings.clamav_host, settings.clamav_port, storage.iter_bytes(row.file_key)
                )
            except clamav.ScannerUnavailableError:
                if attempt < SCAN_TRIES:
                    raise Retry(defer=15 * attempt) from None
                row.scan_status = ScanStatus.ERROR
                await db.commit()
                log.warning("fulltext.scan_failed", fulltext_id=str(row.id))
                await _tell(redis, row)
                return ScanOutcome(ScanStatus.ERROR)
            row.scanned_at = datetime.now(UTC)
            if not result.clean:
                await _quarantine(db, queue, storage, settings, row, result.signature or "unknown")
                await _tell(redis, row)
                return ScanOutcome(ScanStatus.INFECTED)
            row.scan_status = ScanStatus.CLEAN
        elif row.scan_status is ScanStatus.INFECTED:
            return ScanOutcome(ScanStatus.INFECTED)

        text = await asyncio.to_thread(read_text, await storage.read_bytes(row.file_key))
        row.page_count = text.pages
        row.text_extracted = text.text
        await db.commit()
        await _tell(redis, row)
        return ScanOutcome(row.scan_status, text.pages)


async def _quarantine(
    db: AsyncSession,
    queue: ArqRedis,
    storage: Storage,
    settings: Settings,
    row: Fulltext,
    signature: str,
) -> None:
    target = new_key("quarantine")
    await storage.move(row.file_key, target)
    row.file_key = target
    row.scan_status = ScanStatus.INFECTED
    row.scan_signature = signature[:200]
    audit.record(
        db,
        "fulltext.quarantined",
        Actor(),
        user_id=row.uploaded_by,
        project_id=row.project_id,
        entity_type="record",
        entity_id=row.record_id,
        after={"signature": row.scan_signature, "sha256": row.sha256},
    )
    await db.commit()
    log.warning("fulltext.quarantined", fulltext_id=str(row.id), signature=row.scan_signature)
    project = await db.get(Project, row.project_id)
    if project is None:
        return
    managers = await db.scalars(
        select(User.email)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .where(
            ProjectMember.project_id == row.project_id,
            ProjectMember.role.in_([ProjectRole.OWNER, ProjectRole.ADMIN]),
            User.deleted_at.is_(None),
        )
    )
    link = f"{settings.public_origin}/p/{row.project_id}/fulltext"
    for email in managers:
        message = pdf_quarantined(
            email, project_title=project.title, signature=row.scan_signature, link=link
        )
        await queue.enqueue_job(SEND_EMAIL_JOB, message.to, message.subject, message.body)


async def _tell(redis: Redis, row: Fulltext) -> None:
    await events.publish(
        redis,
        row.project_id,
        "fulltext",
        {"record_id": str(row.record_id), "scan_status": row.scan_status.value},
    )


async def run_batch(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    storage: Storage,
    settings: Settings,
    batch_id: uuid.UUID,
) -> int:
    """Unpack a checked ZIP, keep its PDFs aside, and match each to a record. Nothing is
    attached until someone confirms the matches; the PDFs are scanned then."""
    async with sessionmaker() as db:
        batch = await db.get(FulltextBatch, batch_id)
        if batch is None or batch.status is not BatchStatus.CHECKING or batch.zip_key is None:
            return 0
        archive = io.BytesIO(await storage.read_bytes(batch.zip_key))
        match = await _matcher(db, batch.project_id)
        limit = settings.max_pdf_mb * 1024 * 1024
        entries = []
        kept: list[str] = []
        try:
            for raw in batch.entries:
                entry = zipcheck.Entry(
                    index=raw["index"],
                    path=raw["path"],
                    name=raw["name"],
                    size=raw["size"],
                    skip=raw.get("skip"),
                )
                if entry.skip is not None:
                    entries.append(raw)
                    continue
                data = await asyncio.to_thread(zipcheck.extract, archive, entry, limit=limit)
                if not looks_like_pdf(data[:1024]):
                    entries.append({**raw, "skip": "not_pdf"})
                    continue
                key = new_key("fulltext-zips")
                await storage.save(key, _one(data), limit)
                kept.append(key)
                found = match(entry.name)
                entries.append(
                    {
                        **raw,
                        "key": key,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "size": len(data),
                        "match": None
                        if found.match is None
                        else {
                            "record_id": str(found.match.record_id),
                            "by": found.match.by,
                            "confidence": found.match.confidence,
                        },
                        "candidates": [str(rid) for rid in found.candidates],
                    }
                )
        except zipcheck.ZipRejectedError as error:
            for key in kept:
                await storage.delete(key)
            batch.status = BatchStatus.REJECTED
            batch.problem = str(error)
            audit.record(
                db,
                "fulltext.zip_rejected",
                Actor(),
                user_id=batch.created_by,
                project_id=batch.project_id,
                entity_type="project",
                entity_id=batch.project_id,
                after={"filename": batch.filename[:200], "reason": str(error)},
            )
        else:
            batch.status = BatchStatus.READY
            batch.entries = entries
        await storage.delete(batch.zip_key)
        batch.zip_key = None
        await db.commit()
        await events.publish(
            redis,
            batch.project_id,
            "fulltext_batch",
            {"batch_id": str(batch.id), "status": batch.status.value},
        )
        return len(kept)


async def discard_stale_batches(
    *, sessionmaker: async_sessionmaker[AsyncSession], storage: Storage
) -> int:
    """ZIPs matched but never confirmed: their unpacked PDFs are removed after a day."""
    cutoff = datetime.now(UTC) - BATCH_KEEP
    async with sessionmaker() as db:
        stale = list(
            await db.scalars(
                select(FulltextBatch).where(
                    FulltextBatch.status.in_([BatchStatus.READY, BatchStatus.CHECKING]),
                    FulltextBatch.updated_at < cutoff,
                )
            )
        )
        for batch in stale:
            await discard(storage, batch)
        await db.commit()
        return len(stale)


async def _matcher(db: AsyncSession, project_id: uuid.UUID) -> Callable[[str], Outcome]:
    """Records at full text are tried first; a file for any other record still matches."""
    rows = await db.execute(
        select(
            Record.id,
            Record.title,
            Record.doi,
            Record.pmid,
            Record.pmcid,
            Record.authors,
            Record.year,
            Record.ta_final,
        ).where(Record.project_id == project_id, Record.is_duplicate.is_(False))
    )
    at_full_text: list[RecordKeys] = []
    everyone: list[RecordKeys] = []
    for row in rows:
        keys = RecordKeys(
            id=row.id,
            title=row.title,
            doi=row.doi,
            pmid=row.pmid,
            pmcid=row.pmcid,
            first_author=row.authors[0] if row.authors else None,
            year=row.year,
        )
        everyone.append(keys)
        if row.ta_final is TitleAbstractStatus.INCLUDED:
            at_full_text.append(keys)
    first, second = Matcher(at_full_text), Matcher(everyone)

    def match(filename: str) -> Outcome:
        found = first.match(filename)
        return found if found.match is not None else second.match(filename)

    return match


async def _one(data: bytes) -> AsyncIterator[bytes]:
    yield data

"""Full texts (guide 8.8, 12.4): uploading and fetching PDFs, handing them out through
short-lived links, annotations, "not retrievable", and ZIPs of PDFs matched to records.

A PDF is stored under a random key and is not available until the worker has scanned it
(`app.workers.fulltext`). Links to it last five minutes and belong to the person who asked
for them; the file is streamed by the API, never from a public URL.
"""

import hashlib
import io
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
from arq.connections import ArqRedis
from fastapi import UploadFile
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.fulltext import openaccess, zipcheck
from app.fulltext.pdf import looks_like_pdf
from app.models import (
    BatchStatus,
    Fulltext,
    FulltextBatch,
    FulltextSource,
    FullTextStatus,
    PdfAnnotation,
    Record,
    ScanStatus,
    ScreeningStage,
    TitleAbstractStatus,
    UnretrievableRecord,
    User,
)
from app.models.base import uuid7
from app.schemas.fulltext import (
    AnnotationIn,
    AnnotationOut,
    AnnotationPatch,
    BatchApplied,
    BatchEntryOut,
    BatchOut,
    FulltextOut,
    FulltextRecord,
    FulltextSummary,
    MatchOut,
    OpenAccessCandidate,
    OpenAccessFinds,
    RecordFulltext,
    SignedLink,
)
from app.security.permissions import Capability, ProjectAccess
from app.security.tokens import new_token
from app.services import audit
from app.services.audit import Actor
from app.services.blinding import sees_others, settings_of
from app.services.errors import ConflictError, DomainError, ForbiddenError, NotFoundError
from app.services.status import recompute
from app.storage import Storage
from app.storage.base import TooLargeError, new_key

LINK_SECONDS = 300
FINDS_SECONDS = 600
HEAD_BYTES = 1024
SCAN_JOB = "scan_fulltext"
BATCH_JOB = "match_fulltext_batch"
# Full-text stages run to hundreds, rarely a few thousand, records.
MAX_LISTED = 5_000


class NotPdfError(DomainError):
    status = 415
    code = "not_pdf"
    message = "That file is not a PDF."


class FileTooLargeError(DomainError):
    status = 413
    code = "too_large"


class ZipNotAcceptedError(DomainError):
    status = 422
    code = "zip_rejected"


class NotAvailableError(ConflictError):
    code = "not_available"
    message = "This PDF has not been cleared by the virus scanner."


class FetchFailedError(DomainError):
    status = 502
    code = "fetch_failed"


@dataclass(frozen=True)
class OpenedLink:
    key: str
    filename: str
    size: int
    inline: bool


def fulltext_out(row: Fulltext) -> FulltextOut:
    return FulltextOut(
        id=row.id,
        record_id=row.record_id,
        filename=row.filename,
        size_bytes=row.size_bytes,
        scan_status=row.scan_status,
        page_count=row.page_count,
        source=row.source,
        source_url=row.source_url,
        created_at=row.created_at,
    )


class FulltextService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        storage: Storage,
        queue: ArqRedis | None,
        redis: Redis,
        http: httpx.AsyncClient,
    ) -> None:
        self._db = db
        self._settings = settings
        self._storage = storage
        self._queue = queue
        self._redis = redis
        self._http = http
        # Files of replaced PDFs, removed from storage after the commit that replaced them.
        self._stale: list[str] = []

    @property
    def _pdf_limit(self) -> int:
        return self._settings.max_pdf_mb * 1024 * 1024

    @property
    def scanning(self) -> bool:
        return bool(self._settings.clamav_host)

    # --- One record's PDF --------------------------------------------------------------

    async def for_record(self, access: ProjectAccess, record_id: uuid.UUID) -> RecordFulltext:
        record = await self._record(access, record_id)
        row = await self._current(record.id)
        mark = await self._db.get(UnretrievableRecord, record.id)
        return RecordFulltext(
            fulltext=None if row is None else fulltext_out(row),
            not_retrievable=mark is not None,
            not_retrievable_note=None if mark is None else mark.note,
        )

    async def upload(
        self, access: ProjectAccess, record_id: uuid.UUID, file: UploadFile, actor: Actor
    ) -> FulltextOut:
        record = await self._record(access, record_id)
        key = new_key("fulltexts")
        digest = hashlib.sha256()
        head = bytearray()

        async def chunks() -> AsyncIterator[bytes]:
            while chunk := await file.read(1024 * 1024):
                digest.update(chunk)
                if len(head) < HEAD_BYTES:
                    head.extend(chunk[: HEAD_BYTES - len(head)])
                yield chunk

        try:
            size = await self._storage.save(key, chunks(), self._pdf_limit)
        except TooLargeError as error:
            raise FileTooLargeError(
                f"PDFs up to {self._settings.max_pdf_mb} MB are accepted."
            ) from error
        if not looks_like_pdf(bytes(head)):
            await self._storage.delete(key)
            raise NotPdfError
        row = await self._attach(
            access,
            record,
            key=key,
            filename=file.filename or "full text.pdf",
            size=size,
            sha256=digest.hexdigest(),
            source=FulltextSource.UPLOAD,
            actor=actor,
        )
        return await self._committed(row)

    async def remove(self, access: ProjectAccess, record_id: uuid.UUID, actor: Actor) -> None:
        record = await self._record(access, record_id)
        row = await self._current(record.id)
        if row is None:
            raise NotFoundError("This record has no PDF.")
        self._require_may_change(access, row)
        self._stale.append(row.file_key)
        await self._db.delete(row)
        audit.record(
            self._db,
            "fulltext.removed",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record.id,
        )
        await self._commit()

    async def link(
        self, access: ProjectAccess, record_id: uuid.UUID, *, download: bool
    ) -> SignedLink:
        record = await self._record(access, record_id)
        row = await self._current(record.id)
        if row is None:
            raise NotFoundError("This record has no PDF.")
        if row.scan_status not in (ScanStatus.CLEAN, ScanStatus.SKIPPED):
            raise NotAvailableError
        token = new_token()
        payload = {
            "fulltext_id": str(row.id),
            "user_id": str(access.user.id),
            "inline": not download,
        }
        await self._redis.set(f"ft-link:{token}", json.dumps(payload), ex=LINK_SECONDS)
        return SignedLink(url=f"/api/v1/files/{token}", expires_in=LINK_SECONDS)

    async def open_link(self, token: str, user_id: uuid.UUID) -> OpenedLink:
        """The file behind a link, if the link is live, the caller made it, and the file is
        still cleared. Anything else is simply not found."""
        raw = await self._redis.get(f"ft-link:{token}")
        if raw is None:
            raise NotFoundError("This link has expired.")
        payload = json.loads(raw)
        if payload.get("user_id") != str(user_id):
            raise NotFoundError("This link has expired.")
        row = await self._db.get(Fulltext, uuid.UUID(payload["fulltext_id"]))
        if row is None or row.scan_status not in (ScanStatus.CLEAN, ScanStatus.SKIPPED):
            raise NotFoundError("This link has expired.")
        return OpenedLink(
            key=row.file_key,
            filename=row.filename,
            size=row.size_bytes,
            inline=bool(payload["inline"]),
        )

    def stream(self, key: str) -> AsyncIterator[bytes]:
        return self._storage.iter_bytes(key)

    # --- Not retrievable ---------------------------------------------------------------

    async def mark_unretrievable(
        self, access: ProjectAccess, record_id: uuid.UUID, note: str | None, actor: Actor
    ) -> RecordFulltext:
        record = await self._record(access, record_id, full_text=True)
        await self._db.execute(
            insert(UnretrievableRecord)
            .values(
                record_id=record.id,
                project_id=access.project_id,
                marked_by=access.user.id,
                note=note,
            )
            .on_conflict_do_update(
                index_elements=[UnretrievableRecord.record_id],
                set_={"note": note, "marked_by": access.user.id},
            )
        )
        await recompute(
            self._db, access.project_id, ScreeningStage.FULL_TEXT, settings_of(access), [record.id]
        )
        audit.record(
            self._db,
            "fulltext.not_retrievable",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record.id,
        )
        await self._db.commit()
        return await self.for_record(access, record.id)

    async def unmark_unretrievable(
        self, access: ProjectAccess, record_id: uuid.UUID, actor: Actor
    ) -> RecordFulltext:
        record = await self._record(access, record_id, full_text=True)
        await self._clear_unretrievable(access, record.id)
        audit.record(
            self._db,
            "fulltext.retrievable",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record.id,
        )
        await self._db.commit()
        return await self.for_record(access, record.id)

    # --- Annotations -------------------------------------------------------------------

    async def annotations(
        self, access: ProjectAccess, fulltext_id: uuid.UUID
    ) -> list[AnnotationOut]:
        await self._fulltext(access, fulltext_id)
        statement = (
            select(PdfAnnotation, User.name)
            .join(User, User.id == PdfAnnotation.user_id)
            .where(
                PdfAnnotation.fulltext_id == fulltext_id,
                PdfAnnotation.project_id == access.project_id,
            )
            .order_by(PdfAnnotation.page, PdfAnnotation.created_at, PdfAnnotation.id)
        )
        # Under blind mode a comment can carry a judgement: others' are not shown (guide 8.6).
        if not sees_others(access):
            statement = statement.where(PdfAnnotation.user_id == access.user.id)
        rows = await self._db.execute(statement)
        return [_annotation_out(row, name, access.user.id) for row, name in rows]

    async def add_annotation(
        self, access: ProjectAccess, fulltext_id: uuid.UUID, body: AnnotationIn
    ) -> AnnotationOut:
        await self._fulltext(access, fulltext_id)
        row = PdfAnnotation(
            id=uuid7(),
            fulltext_id=fulltext_id,
            project_id=access.project_id,
            user_id=access.user.id,
            page=body.page,
            rects=[[min(max(v, 0.0), 1.0) for v in rect[:4]] for rect in body.rects],
            color=body.color,
            quote=body.quote,
            comment=body.comment,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return _annotation_out(row, access.user.name, access.user.id)

    async def update_annotation(
        self,
        access: ProjectAccess,
        fulltext_id: uuid.UUID,
        annotation_id: uuid.UUID,
        body: AnnotationPatch,
    ) -> AnnotationOut:
        row = await self._own_annotation(access, fulltext_id, annotation_id)
        changes = body.model_dump(exclude_unset=True)
        if "color" in changes and changes["color"] is not None:
            row.color = changes["color"]
        if "comment" in changes:
            row.comment = changes["comment"]
        await self._db.commit()
        await self._db.refresh(row)
        return _annotation_out(row, access.user.name, access.user.id)

    async def delete_annotation(
        self, access: ProjectAccess, fulltext_id: uuid.UUID, annotation_id: uuid.UUID
    ) -> None:
        row = await self._own_annotation(access, fulltext_id, annotation_id)
        await self._db.delete(row)
        await self._db.commit()

    # --- Open access -------------------------------------------------------------------

    async def find_open_access(
        self, access: ProjectAccess, record_id: uuid.UUID
    ) -> OpenAccessFinds:
        record = await self._record(access, record_id)
        if not self._settings.open_access_lookup:
            return OpenAccessFinds(candidates=[], note="Looking for free full text is off here.")
        email = self._settings.unpaywall_email
        if not record.doi and not record.pmcid:
            return OpenAccessFinds(
                candidates=[], note="This record has no DOI or PMCID to look it up by."
            )
        found = await openaccess.find(self._http, doi=record.doi, pmcid=record.pmcid, email=email)
        await self._redis.set(
            _finds_key(access, record.id),
            json.dumps([candidate.__dict__ for candidate in found]),
            ex=FINDS_SECONDS,
        )
        note = None
        if not found:
            note = "No free copy was found."
            if record.doi and not email:
                note += " Unpaywall was not asked: this Winnow has no contact email for it."
        return OpenAccessFinds(
            candidates=[
                OpenAccessCandidate(
                    id=candidate.id,
                    source=candidate.source,
                    host=candidate.host,
                    version=candidate.version,
                    license=candidate.license,
                )
                for candidate in found
            ],
            note=note,
        )

    async def fetch_open_access(
        self, access: ProjectAccess, record_id: uuid.UUID, candidate_id: str, actor: Actor
    ) -> FulltextOut:
        record = await self._record(access, record_id)
        raw = await self._redis.get(_finds_key(access, record.id))
        candidates = json.loads(raw) if raw else []
        chosen = next((item for item in candidates if item["id"] == candidate_id), None)
        if chosen is None:
            raise NotFoundError("Look for free full text again: that find has expired.")
        try:
            data = await openaccess.download(self._http, chosen["url"], limit=self._pdf_limit)
        except openaccess.FetchError as error:
            raise FetchFailedError(str(error)) from error
        if not looks_like_pdf(data[:HEAD_BYTES]):
            raise FetchFailedError("The site sent something that is not a PDF.")
        key = new_key("fulltexts")
        size = await self._storage.save(key, _one(data), self._pdf_limit)
        filename = f"{record.doi or record.pmcid or 'full text'}.pdf".replace("/", "_")
        row = await self._attach(
            access,
            record,
            key=key,
            filename=filename,
            size=size,
            sha256=hashlib.sha256(data).hexdigest(),
            source=FulltextSource.OPEN_ACCESS,
            source_url=chosen["url"],
            actor=actor,
        )
        return await self._committed(row)

    # --- ZIPs of PDFs ------------------------------------------------------------------

    async def start_batch(self, access: ProjectAccess, file: UploadFile, actor: Actor) -> BatchOut:
        key = new_key("fulltext-zips")

        async def chunks() -> AsyncIterator[bytes]:
            while chunk := await file.read(1024 * 1024):
                yield chunk

        try:
            size = await self._storage.save(
                key, chunks(), self._settings.max_upload_mb * 1024 * 1024
            )
        except TooLargeError as error:
            raise FileTooLargeError(
                f"ZIPs up to {self._settings.max_upload_mb} MB are accepted."
            ) from error
        filename = file.filename or "full texts.zip"
        try:
            entries = zipcheck.inspect(
                io.BytesIO(await self._storage.read_bytes(key)), max_entry_bytes=self._pdf_limit
            )
        except zipcheck.ZipRejectedError as error:
            await self._storage.delete(key)
            audit.record(
                self._db,
                "fulltext.zip_rejected",
                actor,
                user_id=access.user.id,
                project_id=access.project_id,
                entity_type="project",
                entity_id=access.project_id,
                after={"filename": filename[:200], "reason": str(error)},
            )
            await self._db.commit()
            raise ZipNotAcceptedError(str(error)) from error
        batch = FulltextBatch(
            id=uuid7(),
            project_id=access.project_id,
            zip_key=key,
            filename=filename,
            size_bytes=size,
            status=BatchStatus.CHECKING,
            entries=[
                {"index": e.index, "path": e.path, "name": e.name, "size": e.size, "skip": e.skip}
                for e in entries
            ],
            created_by=access.user.id,
        )
        self._db.add(batch)
        audit.record(
            self._db,
            "fulltext.zip_uploaded",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="project",
            entity_id=access.project_id,
            after={"filename": filename[:200], "entries": len(entries)},
        )
        await self._db.commit()
        if self._queue is not None:
            await self._queue.enqueue_job(BATCH_JOB, str(batch.id), _job_id=f"ft-batch:{batch.id}")
        await self._db.refresh(batch)
        return await self._batch_out(batch)

    async def batch(self, access: ProjectAccess, batch_id: uuid.UUID) -> BatchOut:
        return await self._batch_out(await self._batch(access, batch_id))

    async def confirm_batch(
        self,
        access: ProjectAccess,
        batch_id: uuid.UUID,
        choices: dict[int, uuid.UUID],
        *,
        replace: bool,
        actor: Actor,
    ) -> BatchApplied:
        batch = await self._batch(access, batch_id)
        if batch.status is not BatchStatus.READY:
            raise ConflictError("This ZIP is not ready to confirm.")
        chosen_records = {
            record.id: record
            for record in await self._db.scalars(
                select(Record).where(
                    Record.id.in_(set(choices.values())),
                    Record.project_id == access.project_id,
                    Record.is_duplicate.is_(False),
                )
            )
        }
        attached: list[uuid.UUID] = []
        skipped = 0
        used: set[uuid.UUID] = set()
        for entry in batch.entries:
            key = entry.get("key")
            if not key:
                continue
            chosen = choices.get(entry["index"])
            record = None if chosen is None else chosen_records.get(chosen)
            if (
                record is None
                or record.id in used
                or (not replace and await self._current(record.id) is not None)
            ):
                self._stale.append(key)
                skipped += 1
                continue
            used.add(record.id)
            row = await self._attach(
                access,
                record,
                key=key,
                filename=entry["name"],
                size=entry["size"],
                sha256=entry["sha256"],
                source=FulltextSource.ZIP,
                actor=actor,
            )
            attached.append(row.id)
        batch.status = BatchStatus.APPLIED
        batch.entries = [{**entry, "key": None} for entry in batch.entries]
        audit.record(
            self._db,
            "fulltext.zip_applied",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="project",
            entity_id=access.project_id,
            after={"attached": len(attached), "skipped": skipped},
        )
        await self._commit()
        await self._scan_later(attached)
        return BatchApplied(attached=len(attached), skipped=skipped)

    # --- The stage at a glance ---------------------------------------------------------

    async def summary(self, access: ProjectAccess) -> FulltextSummary:
        at_full_text = [
            Record.project_id == access.project_id,
            Record.is_duplicate.is_(False),
            Record.ta_final == TitleAbstractStatus.INCLUDED,
        ]
        records = await self._db.scalar(
            select(func.count()).select_from(Record).where(*at_full_text)
        )
        statuses = dict(
            (
                await self._db.execute(
                    select(Fulltext.scan_status, func.count())
                    .join(Record, Record.id == Fulltext.record_id)
                    .where(*at_full_text)
                    .group_by(Fulltext.scan_status)
                )
            )
            .tuples()
            .all()
        )
        unretrievable = await self._db.scalar(
            select(func.count())
            .select_from(Record)
            .where(*at_full_text, Record.ft_final == FullTextStatus.NOT_RETRIEVABLE)
        )
        with_pdf = statuses.get(ScanStatus.CLEAN, 0) + statuses.get(ScanStatus.SKIPPED, 0)
        scanning = statuses.get(ScanStatus.PENDING, 0) + statuses.get(ScanStatus.ERROR, 0)
        quarantined = statuses.get(ScanStatus.INFECTED, 0)
        total = records or 0
        return FulltextSummary(
            records=total,
            with_pdf=with_pdf,
            scanning=scanning,
            quarantined=quarantined,
            missing=max(0, total - with_pdf - scanning - quarantined - (unretrievable or 0)),
            not_retrievable=unretrievable or 0,
            scanner=self.scanning,
            open_access=self._settings.open_access_lookup,
        )

    async def records(self, access: ProjectAccess) -> list[FulltextRecord]:
        """Every record at full text, with its PDF or its "not retrievable" mark."""
        rows = await self._db.execute(
            select(Record, Fulltext, UnretrievableRecord.record_id)
            .outerjoin(Fulltext, Fulltext.record_id == Record.id)
            .outerjoin(UnretrievableRecord, UnretrievableRecord.record_id == Record.id)
            .where(
                Record.project_id == access.project_id,
                Record.is_duplicate.is_(False),
                Record.ta_final == TitleAbstractStatus.INCLUDED,
            )
            .order_by(Record.title.nulls_last(), Record.id)
            .limit(MAX_LISTED)
        )
        return [
            FulltextRecord(
                id=record.id,
                title=record.title,
                first_author=record.authors[0] if record.authors else None,
                year=record.year,
                journal=record.journal,
                doi=record.doi,
                pmid=record.pmid,
                pmcid=record.pmcid,
                fulltext=None if row is None else fulltext_out(row),
                not_retrievable=marked is not None,
            )
            for record, row, marked in rows
        ]

    async def discard_batch(self, access: ProjectAccess, batch_id: uuid.UUID, actor: Actor) -> None:
        batch = await self._batch(access, batch_id)
        if batch.status not in (BatchStatus.READY, BatchStatus.CHECKING):
            return
        await discard(self._storage, batch)
        audit.record(
            self._db,
            "fulltext.zip_discarded",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="project",
            entity_id=access.project_id,
        )
        await self._db.commit()

    # --- Internals ---------------------------------------------------------------------

    async def _attach(
        self,
        access: ProjectAccess,
        record: Record,
        *,
        key: str,
        filename: str,
        size: int,
        sha256: str,
        source: FulltextSource,
        actor: Actor,
        source_url: str | None = None,
    ) -> Fulltext:
        """The record's PDF is now this file: any earlier one (and its annotations) goes, a
        "not retrievable" mark goes, and the file waits for the scanner. Not committed; the
        earlier file is removed from storage once the caller has committed."""
        old = await self._current(record.id)
        if old is not None:
            self._require_may_change(access, old)
            self._stale.append(old.file_key)
            await self._db.delete(old)
            await self._db.flush()
        row = Fulltext(
            id=uuid7(),
            project_id=access.project_id,
            record_id=record.id,
            file_key=key,
            filename=filename[:255],
            size_bytes=size,
            sha256=sha256,
            mime="application/pdf",
            scan_status=ScanStatus.PENDING if self.scanning else ScanStatus.SKIPPED,
            source=source,
            source_url=source_url,
            uploaded_by=access.user.id,
        )
        self._db.add(row)
        await self._clear_unretrievable(access, record.id)
        audit.record(
            self._db,
            "fulltext.added",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record.id,
            after={"source": source.value, "size": size, "sha256": sha256},
        )
        await self._db.flush()
        return row

    async def _committed(self, row: Fulltext) -> FulltextOut:
        await self._commit()
        await self._scan_later([row.id])
        await self._db.refresh(row)
        return fulltext_out(row)

    async def _commit(self) -> None:
        await self._db.commit()
        stale, self._stale = self._stale, []
        for key in stale:
            await self._storage.delete(key)

    @staticmethod
    def _require_may_change(access: ProjectAccess, row: Fulltext) -> None:
        """A PDF someone may be reading or has annotated is replaced or removed only by
        whoever added it, or by an owner or admin. One that is unusable (quarantined, or
        never scanned) anyone screening may replace."""
        if row.scan_status in (ScanStatus.INFECTED, ScanStatus.ERROR):
            return
        if row.uploaded_by == access.user.id or access.can(Capability.IMPORT):
            return
        raise ForbiddenError(
            "Only whoever added this PDF, or an owner or admin, can replace or remove it."
        )

    async def _scan_later(self, ids: list[uuid.UUID]) -> None:
        """Scanning (or, with no scanner, reading the text) happens in the worker."""
        if self._queue is None:
            return
        for fulltext_id in ids:
            await self._queue.enqueue_job(SCAN_JOB, str(fulltext_id), _job_id=f"scan:{fulltext_id}")

    async def _clear_unretrievable(self, access: ProjectAccess, record_id: uuid.UUID) -> None:
        removed = await self._db.execute(
            delete(UnretrievableRecord)
            .where(UnretrievableRecord.record_id == record_id)
            .returning(UnretrievableRecord.record_id)
        )
        if removed.first() is not None:
            await recompute(
                self._db,
                access.project_id,
                ScreeningStage.FULL_TEXT,
                settings_of(access),
                [record_id],
            )

    async def _record(
        self, access: ProjectAccess, record_id: uuid.UUID, *, full_text: bool = False
    ) -> Record:
        record = await self._db.scalar(
            select(Record).where(
                Record.id == record_id,
                Record.project_id == access.project_id,
                Record.is_duplicate.is_(False),
            )
        )
        if record is None:
            raise NotFoundError("That record is not in this review.")
        if full_text and record.ta_final is not TitleAbstractStatus.INCLUDED:
            raise ConflictError("This record has not reached full-text screening.")
        return record

    async def _current(self, record_id: uuid.UUID) -> Fulltext | None:
        row: Fulltext | None = await self._db.scalar(
            select(Fulltext).where(Fulltext.record_id == record_id)
        )
        return row

    async def _fulltext(self, access: ProjectAccess, fulltext_id: uuid.UUID) -> Fulltext:
        row = await self._db.scalar(
            select(Fulltext).where(
                Fulltext.id == fulltext_id, Fulltext.project_id == access.project_id
            )
        )
        if row is None:
            raise NotFoundError("That PDF is not in this review.")
        return row

    async def _own_annotation(
        self, access: ProjectAccess, fulltext_id: uuid.UUID, annotation_id: uuid.UUID
    ) -> PdfAnnotation:
        row = await self._db.scalar(
            select(PdfAnnotation).where(
                PdfAnnotation.id == annotation_id,
                PdfAnnotation.fulltext_id == fulltext_id,
                PdfAnnotation.project_id == access.project_id,
                PdfAnnotation.user_id == access.user.id,
            )
        )
        if row is None:
            raise NotFoundError("That annotation is not yours, or it is gone.")
        return row

    async def _batch(self, access: ProjectAccess, batch_id: uuid.UUID) -> FulltextBatch:
        row = await self._db.scalar(
            select(FulltextBatch).where(
                FulltextBatch.id == batch_id, FulltextBatch.project_id == access.project_id
            )
        )
        if row is None:
            raise NotFoundError("That ZIP is not in this review.")
        return row

    async def _batch_out(self, batch: FulltextBatch) -> BatchOut:
        wanted: set[uuid.UUID] = set()
        for entry in batch.entries:
            if entry.get("match"):
                wanted.add(uuid.UUID(entry["match"]["record_id"]))
            wanted |= {uuid.UUID(rid) for rid in entry.get("candidates", [])}
        records: dict[uuid.UUID, Any] = {}
        with_pdf: set[uuid.UUID] = set()
        if wanted:
            rows = await self._db.execute(
                select(Record.id, Record.title, Record.year).where(Record.id.in_(wanted))
            )
            records = {row.id: row for row in rows}
            with_pdf = set(
                await self._db.scalars(
                    select(Fulltext.record_id).where(Fulltext.record_id.in_(wanted))
                )
            )

        def described(record_id: str, how: dict[str, Any] | None = None) -> MatchOut | None:
            key = uuid.UUID(record_id)
            row = records.get(key)
            if row is None:
                return None
            return MatchOut.model_validate(
                {
                    "record_id": key,
                    "title": row.title,
                    "year": row.year,
                    "has_fulltext": key in with_pdf,
                    **(how or {}),
                }
            )

        entries = []
        for entry in batch.entries:
            match = entry.get("match")
            entries.append(
                BatchEntryOut(
                    index=entry["index"],
                    name=entry["name"],
                    size=entry["size"],
                    skip=entry.get("skip"),
                    match=described(
                        match["record_id"], {"by": match["by"], "confidence": match["confidence"]}
                    )
                    if match
                    else None,
                    candidates=[
                        found
                        for rid in entry.get("candidates", [])
                        if (found := described(rid)) is not None
                    ],
                )
            )
        return BatchOut(
            id=batch.id,
            filename=batch.filename,
            size_bytes=batch.size_bytes,
            status=batch.status,
            problem=batch.problem,
            entries=entries,
            created_at=batch.created_at,
        )


async def discard(storage: Storage, batch: FulltextBatch) -> None:
    """Remove what a batch still holds on disk and mark it done with."""
    for entry in batch.entries:
        if entry.get("key"):
            await storage.delete(entry["key"])
    if batch.zip_key:
        await storage.delete(batch.zip_key)
    batch.zip_key = None
    batch.entries = [{**entry, "key": None} for entry in batch.entries]
    if batch.status in (BatchStatus.READY, BatchStatus.CHECKING):
        batch.status = BatchStatus.FAILED


def _finds_key(access: ProjectAccess, record_id: uuid.UUID) -> str:
    return f"oa-finds:{access.project_id}:{record_id}:{access.user.id}"


async def _one(data: bytes) -> AsyncIterator[bytes]:
    yield data


def _annotation_out(row: PdfAnnotation, author: str, me: uuid.UUID) -> AnnotationOut:
    return AnnotationOut(
        id=row.id,
        page=row.page,
        rects=row.rects,
        color=row.color,
        quote=row.quote,
        comment=row.comment,
        author=author,
        mine=row.user_id == me,
        created_at=row.created_at,
    )

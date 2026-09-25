"""Records with their decisions, for export (guide 8.16).

The records are those the records table would show for the same filters (the same query
builder). What they carry follows blind mode: a reader who may see others' decisions gets
each record's final status and reasons; a blinded reader gets their own decision and
reasons, and their own labels, under headings that say so.
"""

import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ConflictResolution,
    Decision,
    ExclusionReason,
    ImportBatch,
    Label,
    Record,
    RecordLabel,
    ScreeningStage,
)
from app.security.permissions import ProjectAccess
from app.services.blinding import sees_others
from app.services.records import RecordService
from app.services.search import parse_query

BATCH = 5_000
# Excel's limit on a cell; longer text is cut, with a mark.
MAX_CELL = 32_000


@dataclass(frozen=True)
class RecordFilters:
    q: str = ""
    status: str | None = None
    full_text: str | None = None
    batch: uuid.UUID | None = None
    duplicates: bool = False


FIELDS = (
    "id",
    "title",
    "authors",
    "year",
    "journal",
    "volume",
    "issue",
    "pages",
    "doi",
    "pmid",
    "pmcid",
    "url",
    "keywords",
    "publication_type",
    "language",
    "abstract",
    "database",
    "ta_status",
    "ta_reasons",
    "ft_status",
    "ft_reasons",
    "labels",
    "duplicate_of",
)


def headers(*, blind: bool, duplicates: bool) -> list[tuple[str, str]]:
    """(field, heading) for the file's first row."""
    names = {
        "id": "Winnow ID",
        "title": "Title",
        "authors": "Authors",
        "year": "Year",
        "journal": "Journal",
        "volume": "Volume",
        "issue": "Issue",
        "pages": "Pages",
        "doi": "DOI",
        "pmid": "PMID",
        "pmcid": "PMCID",
        "url": "URL",
        "keywords": "Keywords",
        "publication_type": "Publication type",
        "language": "Language",
        "abstract": "Abstract",
        "database": "Database",
        "ta_status": "My title/abstract decision" if blind else "Title/abstract status",
        "ta_reasons": "My title/abstract reasons" if blind else "Title/abstract reasons",
        "ft_status": "My full-text decision" if blind else "Full-text status",
        "ft_reasons": "My full-text reasons" if blind else "Full-text reasons",
        "labels": "My labels" if blind else "Labels",
        "duplicate_of": "Duplicate of",
    }
    return [(field, names[field]) for field in FIELDS if duplicates or field != "duplicate_of"]


def _cut(text: str | None) -> str:
    if not text:
        return ""
    return text if len(text) <= MAX_CELL else text[: MAX_CELL - 1] + "…"


async def record_rows(
    db: AsyncSession, redis: Redis, access: ProjectAccess, filters: RecordFilters
) -> AsyncIterator[list[dict[str, Any]]]:
    """The export's rows, a batch at a time, in import order. Lists (authors, reasons,
    labels) stay lists; each file format joins them its own way."""
    blind = not sees_others(access)
    records = RecordService(db, redis)
    base = records._filtered(  # the records table's own query, so the two always agree
        access,
        query=parse_query(filters.q),
        ta=filters.status,  # type: ignore[arg-type]
        ft=filters.full_text,  # type: ignore[arg-type]
        batch_id=filters.batch,
        duplicates=filters.duplicates,
    )
    reasons = {
        reason.id: str(reason.label)
        for reason in await db.scalars(
            select(ExclusionReason).where(ExclusionReason.project_id == access.project_id)
        )
    }
    databases = dict(
        (
            await db.execute(
                select(ImportBatch.id, ImportBatch.database_name).where(
                    ImportBatch.project_id == access.project_id
                )
            )
        )
        .tuples()
        .all()
    )
    last: uuid.UUID | None = None
    while True:
        statement = base.order_by(Record.id).limit(BATCH)
        if last is not None:
            statement = statement.where(Record.id > last)
        batch = list(await db.scalars(statement))
        if not batch:
            return
        last = batch[-1].id
        ids = [record.id for record in batch]
        work = await _work(db, access, ids, blind)
        yield [_row(record, work, reasons, databases, blind) for record in batch]


@dataclass
class _Work:
    # (record, stage) → the reviewers' reasons, or the resolution's, or mine
    reasons: dict[tuple[uuid.UUID, ScreeningStage], set[uuid.UUID]]
    mine: dict[tuple[uuid.UUID, ScreeningStage], str]
    labels: dict[uuid.UUID, set[str]]


async def _work(
    db: AsyncSession, access: ProjectAccess, ids: list[uuid.UUID], blind: bool
) -> _Work:
    decided = select(
        Decision.record_id, Decision.user_id, Decision.stage, Decision.decision, Decision.reason_ids
    ).where(Decision.record_id.in_(ids))
    if blind:
        decided = decided.where(Decision.user_id == access.user.id)
    reasons: dict[tuple[uuid.UUID, ScreeningStage], set[uuid.UUID]] = defaultdict(set)
    mine: dict[tuple[uuid.UUID, ScreeningStage], str] = {}
    for record_id, user_id, stage, decision, reason_ids in await db.execute(decided):
        if user_id == access.user.id:
            mine[(record_id, stage)] = decision.value
        if decision.value == "exclude":
            reasons[(record_id, stage)].update(reason_ids)
    if not blind:
        resolved = await db.execute(
            select(
                ConflictResolution.record_id,
                ConflictResolution.stage,
                ConflictResolution.reason_ids,
            ).where(ConflictResolution.record_id.in_(ids))
        )
        for record_id, stage, reason_ids in resolved:
            # A resolution's reasons are the record's reasons.
            reasons[(record_id, stage)] = set(reason_ids)
    labelled = (
        select(RecordLabel.record_id, Label.name)
        .join(Label, Label.id == RecordLabel.label_id)
        .where(RecordLabel.record_id.in_(ids))
    )
    if blind:
        labelled = labelled.where(RecordLabel.user_id == access.user.id)
    labels: dict[uuid.UUID, set[str]] = defaultdict(set)
    for record_id, name in await db.execute(labelled):
        labels[record_id].add(str(name))
    return _Work(reasons=reasons, mine=mine, labels=labels)


def _row(
    record: Record,
    work: _Work,
    reasons: dict[uuid.UUID, str],
    databases: dict[uuid.UUID, str],
    blind: bool,
) -> dict[str, Any]:
    def reason_list(stage: ScreeningStage, status: str) -> list[str]:
        if status not in ("excluded", "exclude"):
            return []
        return sorted(reasons[r] for r in work.reasons.get((record.id, stage), ()) if r in reasons)

    if blind:
        ta = work.mine.get((record.id, ScreeningStage.TITLE_ABSTRACT), "")
        ft = work.mine.get((record.id, ScreeningStage.FULL_TEXT), "")
    else:
        ta, ft = record.ta_final.value, record.ft_final.value
    return {
        "id": str(record.id),
        "title": _cut(record.title),
        "authors": list(record.authors),
        "year": record.year if record.year is not None else "",
        "journal": record.journal or "",
        "volume": record.volume or "",
        "issue": record.issue or "",
        "pages": record.pages or "",
        "doi": record.doi or "",
        "pmid": record.pmid or "",
        "pmcid": record.pmcid or "",
        "url": record.url or "",
        "keywords": list(record.keywords),
        "publication_type": list(record.publication_type),
        "language": record.language or "",
        "abstract": _cut(record.abstract),
        "database": databases.get(record.import_batch_id, "") if record.import_batch_id else "",
        "ta_status": ta,
        "ta_reasons": reason_list(ScreeningStage.TITLE_ABSTRACT, ta),
        "ft_status": ft,
        "ft_reasons": reason_list(ScreeningStage.FULL_TEXT, ft),
        "labels": sorted(work.labels.get(record.id, ())),
        "duplicate_of": str(record.duplicate_of) if record.duplicate_of else "",
    }

"""Extracted data for export (guide 8.12): one form version, long or wide.

"Final" is what an analysis uses: the consensus where there is one, else the only
submitted extraction of a study; a study extracted twice and not yet reconciled is left
out (and counted). "All" is every extractor's submitted data and the consensus, each
labelled, for checking. A blinded reader gets their own submitted extractions only.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import extraction
from app.models import (
    EntryStatus,
    ExtractionConsensus,
    ExtractionEntry,
    ExtractionForm,
    Record,
    User,
)
from app.security.permissions import ProjectAccess
from app.services.blinding import sees_others
from app.services.errors import NotFoundError
from app.services.extraction import checked_schema, study_label

DONE = (EntryStatus.SUBMITTED, EntryStatus.VERIFIED)
CONSENSUS = "consensus"


@dataclass(frozen=True)
class ExtractionTable:
    form: ExtractionForm
    headers: list[str]
    rows: list[dict[str, object]]
    # Studies extracted more than once and not reconciled: not in a "final" export.
    unreconciled: int


async def extraction_table(
    db: AsyncSession, access: ProjectAccess, options: dict[str, object]
) -> ExtractionTable:
    form = await db.scalar(
        select(ExtractionForm).where(
            ExtractionForm.id == uuid.UUID(str(options["form_id"])),
            ExtractionForm.project_id == access.project_id,
        )
    )
    if form is None:
        raise NotFoundError("That form is no longer in this review.")
    schema = checked_schema(form.schema)
    blind = not sees_others(access)
    which = options.get("which", "final")

    entries = (
        select(ExtractionEntry, User.name)
        .outerjoin(User, User.id == ExtractionEntry.user_id)
        .where(ExtractionEntry.form_id == form.id, ExtractionEntry.status.in_(DONE))
    )
    if blind:
        entries = entries.where(ExtractionEntry.user_id == access.user.id)
    by_record: dict[uuid.UUID, list[tuple[str, dict[str, object]]]] = defaultdict(list)
    for entry, name in await db.execute(entries.order_by(ExtractionEntry.created_at)):
        by_record[entry.record_id].append((name or "Former member", entry.data))
    agreed: dict[uuid.UUID, dict[str, object]] = {}
    if not blind:
        for record_id, data in await db.execute(
            select(ExtractionConsensus.record_id, ExtractionConsensus.data).where(
                ExtractionConsensus.form_id == form.id
            )
        ):
            agreed[record_id] = data
    ids = set(by_record) | set(agreed)
    labels = {
        record_id: study_label(authors, year, title)
        for record_id, authors, year, title in await db.execute(
            select(Record.id, Record.authors, Record.year, Record.title).where(
                Record.id.in_(ids), Record.project_id == access.project_id
            )
        )
    }
    order = sorted(ids, key=lambda record_id: (labels.get(record_id, ""), str(record_id)))

    rows: list[extraction.EntryForExport] = []
    unreconciled = 0
    for record_id in order:
        label = labels.get(record_id, "")
        made = by_record.get(record_id, [])
        if which == "all":
            rows += [
                extraction.EntryForExport(str(record_id), label, name, data) for name, data in made
            ]
            if record_id in agreed:
                rows.append(
                    extraction.EntryForExport(str(record_id), label, CONSENSUS, agreed[record_id])
                )
        elif record_id in agreed:
            rows.append(
                extraction.EntryForExport(str(record_id), label, CONSENSUS, agreed[record_id])
            )
        elif len(made) == 1 or blind:
            rows += [
                extraction.EntryForExport(str(record_id), label, name, data) for name, data in made
            ]
        else:
            unreconciled += 1

    if options.get("layout") == "long":
        return ExtractionTable(
            form, list(extraction.LONG_COLUMNS), extraction.long_rows(schema, rows), unreconciled
        )
    wide = extraction.wide_rows(schema, rows)
    return ExtractionTable(form, wide.headers, wide.rows, unreconciled)

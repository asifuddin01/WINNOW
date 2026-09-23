"""The derived state rule (guide 6.4): a record's final status at each stage.

`records.ta_final` and `ft_final` are written here and nowhere else, inside the same
transaction as the decision, undo, resolution or setting change that moved them.

1. A resolution exists → it decides.
2. Fewer decisions than the review requires → pending.
3. All decisions agree (a "maybe" counted as the settings say) → that decision.
4. Otherwise → conflict.

When the title/abstract status becomes included, the record enters full-text screening.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ConflictResolution,
    Decision,
    DecisionValue,
    FinalDecision,
    FullTextStatus,
    Record,
    ScreeningStage,
    TitleAbstractStatus,
)
from app.schemas.projects import ProjectSettings

# The statuses the rule can produce, per stage, by what they mean.
_TA = {
    "pending": TitleAbstractStatus.PENDING,
    "include": TitleAbstractStatus.INCLUDED,
    "exclude": TitleAbstractStatus.EXCLUDED,
    "maybe": TitleAbstractStatus.MAYBE,
    "conflict": TitleAbstractStatus.CONFLICT,
}
_FT = {
    "pending": FullTextStatus.PENDING,
    "include": FullTextStatus.INCLUDED,
    "exclude": FullTextStatus.EXCLUDED,
    # A full-text "maybe" is not a final answer; the record waits for someone to decide.
    "maybe": FullTextStatus.PENDING,
    "conflict": FullTextStatus.CONFLICT,
}
# Enough rows per UPDATE to recompute a 100,000-record review in a few round trips.
BATCH = 5_000


def outcome(
    decisions: Sequence[DecisionValue],
    resolution: FinalDecision | None,
    *,
    required: int,
    maybe_counts_as: str,
) -> str:
    """Rules 1-4 on plain values: "pending", "include", "exclude", "maybe" or "conflict"."""
    if resolution is not None:
        return resolution.value
    if len(decisions) < required:
        return "pending"
    effective = {
        DecisionValue.INCLUDE
        if value is DecisionValue.MAYBE and maybe_counts_as == "include"
        else value
        for value in decisions
    }
    if len(effective) == 1:
        return next(iter(effective)).value
    return "conflict"


async def recompute(
    db: AsyncSession,
    project_id: uuid.UUID,
    stage: ScreeningStage,
    settings: ProjectSettings,
    record_ids: Iterable[uuid.UUID] | None = None,
) -> None:
    """Recompute `stage` for the given records, or for every record in the review."""
    wanted = None if record_ids is None else list(dict.fromkeys(record_ids))
    if wanted is not None and not wanted:
        return

    scope = [Decision.project_id == project_id, Decision.stage == stage]
    if wanted is not None:
        scope.append(Decision.record_id.in_(wanted))
    by_record: defaultdict[uuid.UUID, list[DecisionValue]] = defaultdict(list)
    decided = await db.execute(select(Decision.record_id, Decision.decision).where(*scope))
    for record_id, value in decided:
        by_record[record_id].append(value)

    resolved_scope = [
        ConflictResolution.project_id == project_id,
        ConflictResolution.stage == stage,
    ]
    if wanted is not None:
        resolved_scope.append(ConflictResolution.record_id.in_(wanted))
    resolutions: dict[uuid.UUID, FinalDecision] = {}
    resolved = await db.execute(
        select(ConflictResolution.record_id, ConflictResolution.final_decision).where(
            *resolved_scope
        )
    )
    for record_id, final in resolved:
        resolutions[record_id] = final

    if wanted is None:
        targets = list(await db.scalars(select(Record.id).where(Record.project_id == project_id)))
    else:
        targets = wanted
    required = (
        settings.reviewers_per_record_ta
        if stage is ScreeningStage.TITLE_ABSTRACT
        else settings.reviewers_per_record_ft
    )
    # The review's maybe rule is for titles and abstracts. At full text a maybe is not an
    # answer: all maybes wait (pending), and a maybe beside a decision is a conflict.
    maybe_counts_as = (
        settings.maybe_counts_as if stage is ScreeningStage.TITLE_ABSTRACT else "maybe"
    )
    rows = [
        (
            record_id,
            outcome(
                by_record.get(record_id, []),
                resolutions.get(record_id),
                required=required,
                maybe_counts_as=maybe_counts_as,
            ),
        )
        for record_id in targets
    ]
    for start in range(0, len(rows), BATCH):
        await _write(db, project_id, stage, rows[start : start + BATCH])


async def recompute_record_status(
    db: AsyncSession,
    project_id: uuid.UUID,
    record_id: uuid.UUID,
    stage: ScreeningStage,
    settings: ProjectSettings,
) -> None:
    """Guide 6.4's single entry point, for one record."""
    await recompute(db, project_id, stage, settings, [record_id])


async def _write(
    db: AsyncSession,
    project_id: uuid.UUID,
    stage: ScreeningStage,
    rows: list[tuple[uuid.UUID, str]],
) -> None:
    """One UPDATE per outcome — at most five — however many records there are."""
    if not rows:
        return
    by_outcome: defaultdict[str, list[uuid.UUID]] = defaultdict(list)
    for record_id, result in rows:
        by_outcome[result].append(record_id)
    for result, ids in by_outcome.items():
        values_ = (
            {Record.ta_final: _TA[result]}
            if stage is ScreeningStage.TITLE_ABSTRACT
            else {Record.ft_final: _FT[result]}
        )
        await db.execute(
            update(Record)
            .where(Record.id.in_(ids), Record.project_id == project_id)
            .values(values_)
            .execution_options(synchronize_session=None)
        )
    if stage is ScreeningStage.TITLE_ABSTRACT:
        await _follow_into_full_text(db, project_id, [record_id for record_id, _ in rows])


async def _follow_into_full_text(
    db: AsyncSession, project_id: uuid.UUID, record_ids: list[uuid.UUID]
) -> None:
    """Included at title/abstract → waiting for full text; no longer included → out again,
    unless someone has already made a full-text decision on it."""
    await db.execute(
        update(Record)
        .where(
            Record.id.in_(record_ids),
            Record.project_id == project_id,
            Record.ta_final == TitleAbstractStatus.INCLUDED,
            Record.ft_final == FullTextStatus.NOT_ELIGIBLE,
        )
        .values(ft_final=FullTextStatus.PENDING)
        .execution_options(synchronize_session=None)
    )
    has_full_text_work = (
        select(Decision.record_id)
        .where(Decision.stage == ScreeningStage.FULL_TEXT, Decision.record_id == Record.id)
        .exists()
    )
    await db.execute(
        update(Record)
        .where(
            Record.id.in_(record_ids),
            Record.project_id == project_id,
            Record.ta_final != TitleAbstractStatus.INCLUDED,
            Record.ft_final == FullTextStatus.PENDING,
            ~has_full_text_work,
        )
        .values(ft_final=FullTextStatus.NOT_ELIGIBLE)
        .execution_options(synchronize_session=None)
    )

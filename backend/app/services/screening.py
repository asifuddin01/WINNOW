"""Title/abstract (and later full-text) screening: the queue, decisions and their undo,
history, labels, notes and bulk decisions (guide 8.5).

Blind mode is enforced here, not in the UI: what a caller is sent about other people's
work goes through `app.services.blinding` (guide 8.6). Every decision change recomputes
the record's status in the same transaction (guide 6.4).
"""

import hashlib
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

from arq.connections import ArqRedis
from sqlalchemy import ColumnElement, Select, Text, and_, cast, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ConflictResolution,
    Decision,
    DecisionValue,
    ExclusionReason,
    Fulltext,
    Label,
    Note,
    NoteVisibility,
    NotificationKind,
    ProjectMember,
    ProjectRole,
    ReasonStage,
    Record,
    RecordLabel,
    RecordScore,
    ResolutionSource,
    ScreeningStage,
    TitleAbstractStatus,
    UnretrievableRecord,
    User,
)
from app.models.base import uuid7
from app.schemas.projects import ProjectSettings
from app.schemas.screening import (
    MAX_TIME_MS,
    BulkDecisionIn,
    BulkDecisionOut,
    DecisionIn,
    DecisionOut,
    HistoryItem,
    HistoryPage,
    MyDecision,
    NoteOut,
    OtherDecision,
    Progress,
    QueuePage,
    QueueSort,
    ScreeningItem,
)
from app.security.permissions import ProjectAccess
from app.services import audit
from app.services.audit import Actor
from app.services.blinding import can_resolve, screens, sees_others, settings_of
from app.services.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
)
from app.services.fulltext import fulltext_out
from app.services.notifications import excerpt, mentioned, notify, resolvers
from app.services.pagination import decode_cursor, encode_cursor
from app.services.ranking import EXPLORE_EVERY, nudge
from app.services.records import apply_search
from app.services.search import parse_query
from app.services.status import recompute

MAX_QUEUE = 25
MAX_EXCLUDE = 60


class ReasonRequiredError(DomainError):
    status = 422
    code = "reason_required"
    message = "Choose at least one exclusion reason. This review asks for one."


class UnknownReasonError(DomainError):
    status = 422
    code = "unknown_reason"
    message = "One of those exclusion reasons does not belong to this review or stage."


class UnknownLabelError(DomainError):
    status = 422
    code = "unknown_label"
    message = "One of those labels does not belong to this review."


class NotScreeningError(ForbiddenError):
    code = "not_screening"
    message = "You do not screen records at this stage of this review."


class BulkChangedError(ConflictError):
    code = "bulk_changed"


def _required(settings: ProjectSettings, stage: ScreeningStage) -> int:
    if stage is ScreeningStage.TITLE_ABSTRACT:
        return settings.reviewers_per_record_ta
    return settings.reviewers_per_record_ft


def _hash(record_id: Any, user_id: Any) -> ColumnElement[str]:
    """The rendezvous hash that shares records out in `split` mode. A person's own id is
    passed in as text; a column is cast to it."""
    person = user_id if isinstance(user_id, str) else cast(user_id, Text)
    return func.md5(func.concat(cast(record_id, Text), person))


def assigned_to(
    access: ProjectAccess, stage: ScreeningStage, user_id: uuid.UUID
) -> ColumnElement[bool]:
    """Guide 8.5's `split` mode: each record goes to exactly N of the stage's screeners.

    Rendezvous hashing — a record belongs to the N screeners with the lowest
    md5(record, person) — needs no assignment table and no job: it is balanced across
    screeners, every record gets exactly N of them, and when someone joins or leaves only
    their share moves. The query asks how many screeners rank ahead of this one.
    """
    required = _required(settings_of(access), stage)
    ahead = (
        select(func.count())
        .select_from(ProjectMember)
        .where(
            ProjectMember.project_id == Record.project_id,
            ProjectMember.role != ProjectRole.VIEWER,
            ProjectMember.stages.contains([stage.value]),
            _hash(Record.id, ProjectMember.user_id) < _hash(Record.id, str(user_id)),
        )
        .correlate(Record)
        .scalar_subquery()
    )
    return ahead < required


async def check_reasons(
    db: AsyncSession, access: ProjectAccess, stage: ScreeningStage, reason_ids: list[uuid.UUID]
) -> None:
    """Every reason must be one of this review's, for this stage or for both."""
    if not reason_ids:
        return
    stages = [ReasonStage.BOTH, ReasonStage(stage.value)]
    known = set(
        await db.scalars(
            select(ExclusionReason.id).where(
                ExclusionReason.project_id == access.project_id,
                ExclusionReason.id.in_(reason_ids),
                ExclusionReason.stage.in_(stages),
            )
        )
    )
    if known != set(reason_ids):
        raise UnknownReasonError


class ScreeningService:
    def __init__(self, db: AsyncSession, queue: ArqRedis | None = None) -> None:
        self._db = db
        # Decisions nudge the ranking job (guide 8.10); None where no queue is needed.
        self._queue = queue

    # --- What is left to screen --------------------------------------------------------

    def _eligible(self, access: ProjectAccess, stage: ScreeningStage) -> list[Any]:
        conditions: list[Any] = [
            Record.project_id == access.project_id,
            Record.is_duplicate.is_(False),
        ]
        if stage is ScreeningStage.FULL_TEXT:
            conditions.append(Record.ta_final == TitleAbstractStatus.INCLUDED)
            # A report nobody could get is counted in PRISMA, not screened (guide 8.8).
            conditions.append(
                ~select(UnretrievableRecord.record_id)
                .where(UnretrievableRecord.record_id == Record.id)
                .exists()
            )
        if settings_of(access).assignment == "split":
            conditions.append(assigned_to(access, stage, access.user.id))
        return conditions

    def waiting(self, access: ProjectAccess, stage: ScreeningStage) -> list[Any]:
        """Eligible, not decided by me, and not settled by a resolution."""
        mine = (
            select(Decision.id)
            .where(
                Decision.record_id == Record.id,
                Decision.user_id == access.user.id,
                Decision.stage == stage,
            )
            .exists()
        )
        settled = (
            select(ConflictResolution.id)
            .where(ConflictResolution.record_id == Record.id, ConflictResolution.stage == stage)
            .exists()
        )
        return [*self._eligible(access, stage), ~mine, ~settled]

    async def queue(
        self,
        access: ProjectAccess,
        *,
        stage: ScreeningStage,
        n: int = 10,
        sort: QueueSort = "relevance",
        exclude: list[uuid.UUID] | None = None,
        search: str = "",
    ) -> QueuePage:
        """The next records for me, for the screen to hold ahead of time (guide 8.5)."""
        self._require_screening(access, stage)
        waiting = select(Record).where(*self.waiting(access, stage))
        if search:
            waiting = apply_search(
                waiting,
                parse_query(search),
                label_owner=None if sees_others(access) else access.user.id,
            )
        if exclude:
            waiting = waiting.where(Record.id.not_in(exclude[:MAX_EXCLUDE]))
        n = min(n, MAX_QUEUE)
        if sort == "relevance" and not settings_of(access).ranking_enabled:
            sort = "random"
        if sort == "relevance":
            # Where these records fall in my screening, so that exactly one in
            # EXPLORE_EVERY of everything I am served comes from random order.
            decided = await self._db.scalar(
                select(func.count()).where(
                    Decision.project_id == access.project_id,
                    Decision.user_id == access.user.id,
                    Decision.stage == stage,
                )
            )
            rows = await self._relevant_first(
                waiting,
                access.user.id,
                n,
                position=(decided or 0) + len(exclude or []),
                stage=stage,
                project_id=access.project_id,
            )
        else:
            rows = await self._in_order(waiting, sort, access.user.id, n)
        return QueuePage(items=await self._items(access, stage, rows))

    async def _relevant_first(
        self,
        waiting: Select[Any],
        user_id: uuid.UUID,
        n: int,
        *,
        position: int,
        stage: ScreeningStage,
        project_id: uuid.UUID,
    ) -> list[Record]:
        """Guide 9.2: most likely relevant first, by the model's score, but every
        EXPLORE_EVERY-th record from the random order, so the model also learns from
        records it would rank low. Records the model has not scored yet (none, before the
        first model) come in random order."""
        scored = await self._best_scored(waiting, project_id, stage, n)
        shuffled = await self._in_order(waiting, "random", user_id, n)
        rows: list[Record] = []
        seen: set[uuid.UUID] = set()
        for slot in range(n):
            explore = (position + slot + 1) % EXPLORE_EVERY == 0
            first, second = (shuffled, scored) if explore else (scored, shuffled)
            pick = next((row for row in first if row.id not in seen), None)
            if pick is None:
                pick = next((row for row in second if row.id not in seen), None)
            if pick is None:
                break
            seen.add(pick.id)
            rows.append(pick)
        return rows

    async def _best_scored(
        self, waiting: Select[Any], project_id: uuid.UUID, stage: ScreeningStage, n: int
    ) -> list[Record]:
        """The `n` best-scored records waiting for me. The review's best scores are read
        straight off the index, 20n at a time, then eight times as many while my own
        decisions have used them up: asked for in one query, PostgreSQL joined and sorted
        every score first (0.1-0.5 s at 100,000 records, Phase 9)."""
        depth = n * 20
        while True:
            top = (
                select(RecordScore.record_id, RecordScore.score)
                .where(RecordScore.project_id == project_id, RecordScore.stage == stage)
                .order_by(RecordScore.score.desc(), RecordScore.record_id)
                .limit(depth)
                .subquery()
            )
            rows = list(
                await self._db.scalars(
                    waiting.join(top, top.c.record_id == Record.id)
                    .order_by(top.c.score.desc(), Record.id)
                    .limit(n)
                )
            )
            if len(rows) == n:
                return rows
            read = await self._db.scalar(select(func.count()).select_from(top))
            if (read or 0) < depth:  # every score read: these are all there are
                return rows
            depth *= 8

    async def _in_order(
        self, waiting: Select[Any], sort: QueueSort, user_id: uuid.UUID, n: int
    ) -> list[Record]:
        """The next `n` records in `sort` order, each read from an index (guide 2.2).

        "random" walks the records' stored random sort key from a point that is fixed for
        each person, wrapping round at the end: stable, so the records held ahead do not
        reshuffle, and different for each reviewer. ("relevance" is `_relevant_first`.)
        """
        if sort == "year":
            ordered = waiting.order_by(Record.year.desc().nullslast(), Record.id)
            return list(await self._db.scalars(ordered.limit(n)))
        if sort == "title":
            ordered = waiting.order_by(Record.title_norm.asc().nullslast(), Record.id)
            return list(await self._db.scalars(ordered.limit(n)))
        if sort == "added":
            return list(await self._db.scalars(waiting.order_by(Record.id).limit(n)))
        rows: list[Record] = []
        start = _start_for(user_id)
        for part in (Record.sort_key >= start, Record.sort_key < start):
            if len(rows) >= n:
                break
            more = waiting.where(part).order_by(Record.sort_key, Record.id).limit(n - len(rows))
            rows += list(await self._db.scalars(more))
        return rows

    async def item(
        self, access: ProjectAccess, record_id: uuid.UUID, stage: ScreeningStage
    ) -> ScreeningItem:
        """One record, decided or not — for going back to it from the history."""
        record = await self._record(access, record_id)
        (item,) = await self._items(access, stage, [record])
        return item

    async def progress(self, access: ProjectAccess, stage: ScreeningStage) -> Progress:
        eligible = self._eligible(access, stage)
        total = await self._db.scalar(select(func.count()).select_from(Record).where(*eligible))
        remaining = await self._db.scalar(
            select(func.count()).select_from(Record).where(*self.waiting(access, stage))
        )
        mine = await self._db.execute(
            select(Decision.decision, func.count())
            .join(Record, Record.id == Decision.record_id)
            .where(Decision.user_id == access.user.id, Decision.stage == stage, *eligible)
            .group_by(Decision.decision)
        )
        counts: dict[DecisionValue, int] = {}
        for value, count in mine:
            counts[value] = count
        told = sees_others(access) or can_resolve(access)
        conflicts = None
        if told:
            column = Record.ta_final if stage is ScreeningStage.TITLE_ABSTRACT else Record.ft_final
            conflicts = await self._db.scalar(
                select(func.count())
                .select_from(Record)
                .where(
                    Record.project_id == access.project_id,
                    Record.is_duplicate.is_(False),
                    column == "conflict",
                )
            )
        screened = sum(counts.values())
        return Progress(
            stage=stage,
            screened=screened,
            total=total or 0,
            remaining=remaining or 0,
            included=counts.get(DecisionValue.INCLUDE, 0),
            excluded=counts.get(DecisionValue.EXCLUDE, 0),
            maybe=counts.get(DecisionValue.MAYBE, 0),
            conflicts=conflicts,
            blind=not sees_others(access),
            can_resolve=can_resolve(access),
            assignment=settings_of(access).assignment,
        )

    # --- Deciding ----------------------------------------------------------------------

    async def decide(
        self, access: ProjectAccess, record_id: uuid.UUID, body: DecisionIn, actor: Actor
    ) -> DecisionOut:
        """Record or change my decision, and recompute the record's status (guide 6.4)."""
        stage = body.stage
        self._require_screening(access, stage)
        record = await self._record(access, record_id)
        if stage is ScreeningStage.FULL_TEXT:
            if record.ta_final is not TitleAbstractStatus.INCLUDED:
                raise ConflictError("This record has not reached full-text screening.")
            if await self._db.get(UnretrievableRecord, record.id) is not None:
                raise ConflictError(
                    "This record's full text is marked not retrievable. Undo that to screen it."
                )
        settings = settings_of(access)
        reasons = body.reason_ids if body.decision is DecisionValue.EXCLUDE else []
        await check_reasons(self._db, access, stage, reasons)
        if (
            body.decision is DecisionValue.EXCLUDE
            and not reasons
            and self._reason_required(settings, stage)
        ):
            raise ReasonRequiredError

        spent = min(body.time_spent_ms, MAX_TIME_MS)
        values = insert(Decision).values(
            id=uuid7(),
            project_id=access.project_id,
            record_id=record.id,
            user_id=access.user.id,
            stage=stage,
            decision=body.decision,
            reason_ids=reasons,
            note=body.note,
            time_spent_ms=spent,
        )
        statement = values.on_conflict_do_update(
            index_elements=[Decision.record_id, Decision.user_id, Decision.stage],
            set_={
                "decision": values.excluded.decision,
                "reason_ids": values.excluded.reason_ids,
                "note": values.excluded.note,
                # Time on a record adds up over every visit to it.
                "time_spent_ms": Decision.time_spent_ms + values.excluded.time_spent_ms,
                "updated_at": func.now(),
            },
        ).returning(
            Decision.decision,
            Decision.reason_ids,
            Decision.note,
            Decision.updated_at,
            Decision.created_at,
        )
        saved = (await self._db.execute(statement)).one()
        column = Record.ta_final if stage is ScreeningStage.TITLE_ABSTRACT else Record.ft_final
        before = await self._db.scalar(select(column).where(Record.id == record.id))
        await recompute(self._db, access.project_id, stage, settings, [record.id])
        after = await self._db.scalar(select(column).where(Record.id == record.id))
        if after is not None and after.value == "conflict" and before != after:
            await notify(
                self._db,
                [
                    person
                    for person in await resolvers(self._db, access.project_id)
                    if person != access.user.id
                ],
                NotificationKind.CONFLICTS,
                project_id=access.project_id,
                data={"project_title": access.project.title},
            )
        audit.record(
            self._db,
            "decision.changed" if saved.created_at != saved.updated_at else "decision.made",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record.id,
            after={"stage": stage.value, "decision": body.decision.value, "reasons": len(reasons)},
        )
        await self._db.commit()
        await nudge(self._queue, access.project_id, stage, settings)
        return DecisionOut(
            record_id=record.id,
            stage=stage,
            decision=MyDecision(
                decision=saved.decision,
                reason_ids=list(saved.reason_ids),
                note=saved.note,
                updated_at=saved.updated_at,
            ),
        )

    async def undo(
        self, access: ProjectAccess, record_id: uuid.UUID, stage: ScreeningStage, actor: Actor
    ) -> DecisionOut:
        """Take my decision back (guide 8.5: Ctrl/Cmd+Z, or from the history)."""
        self._require_screening(access, stage)
        record = await self._record(access, record_id)
        removed = await self._db.scalar(
            delete(Decision)
            .where(
                Decision.record_id == record.id,
                Decision.user_id == access.user.id,
                Decision.stage == stage,
            )
            .returning(Decision.decision)
        )
        if removed is None:
            raise NotFoundError("You have not decided about this record.")
        await recompute(self._db, access.project_id, stage, settings_of(access), [record.id])
        audit.record(
            self._db,
            "decision.undone",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record.id,
            before={"stage": stage.value, "decision": removed.value},
        )
        await self._db.commit()
        await nudge(self._queue, access.project_id, stage, settings_of(access))
        return DecisionOut(record_id=record.id, stage=stage, decision=None)

    async def history(
        self,
        access: ProjectAccess,
        stage: ScreeningStage,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> HistoryPage:
        """My decisions, the latest first, to go back to and change (guide 8.5)."""
        statement = (
            select(Decision, Record.title, Record.year)
            .join(Record, Record.id == Decision.record_id)
            .where(
                Decision.project_id == access.project_id,
                Decision.user_id == access.user.id,
                Decision.stage == stage,
            )
            .order_by(Decision.updated_at.desc(), Decision.id.desc())
        )
        if cursor:
            when, last_id = decode_cursor(cursor, 2)
            at = datetime.fromisoformat(when)
            statement = statement.where(
                (Decision.updated_at < at)
                | and_(Decision.updated_at == at, Decision.id < uuid.UUID(last_id))
            )
        rows = list(await self._db.execute(statement.limit(limit + 1)))
        items = [
            HistoryItem(
                record_id=decision.record_id,
                title=title,
                year=year,
                decision=decision.decision,
                reason_ids=list(decision.reason_ids),
                updated_at=decision.updated_at,
            )
            for decision, title, year in rows[:limit]
        ]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1][0]
            next_cursor = encode_cursor(last.updated_at.isoformat(), str(last.id))
        return HistoryPage(items=items, next_cursor=next_cursor)

    # --- Labels and notes --------------------------------------------------------------

    async def set_labels(
        self, access: ProjectAccess, record_id: uuid.UUID, label_ids: list[uuid.UUID]
    ) -> list[uuid.UUID]:
        """Replace the labels I have put on this record (guide 8.9)."""
        if access.role is ProjectRole.VIEWER:
            raise ForbiddenError
        record = await self._record(access, record_id)
        wanted = list(dict.fromkeys(label_ids))
        if wanted:
            known = set(
                await self._db.scalars(
                    select(Label.id).where(
                        Label.project_id == access.project_id, Label.id.in_(wanted)
                    )
                )
            )
            if known != set(wanted):
                raise UnknownLabelError
        await self._db.execute(
            delete(RecordLabel).where(
                RecordLabel.record_id == record.id, RecordLabel.user_id == access.user.id
            )
        )
        self._db.add_all(
            RecordLabel(record_id=record.id, label_id=label_id, user_id=access.user.id)
            for label_id in wanted
        )
        await self._db.commit()
        return wanted

    async def add_note(
        self,
        access: ProjectAccess,
        record_id: uuid.UUID,
        body: str,
        visibility: NoteVisibility,
    ) -> NoteOut:
        if access.role is ProjectRole.VIEWER:
            raise ForbiddenError
        record = await self._record(access, record_id)
        note = Note(
            project_id=access.project_id,
            record_id=record.id,
            user_id=access.user.id,
            body=body.strip(),
            visibility=visibility,
        )
        self._db.add(note)
        if visibility is NoteVisibility.TEAM and "@" in note.body:
            members = (
                (
                    await self._db.execute(
                        select(User.id, User.name)
                        .join(ProjectMember, ProjectMember.user_id == User.id)
                        .where(
                            ProjectMember.project_id == access.project_id,
                            User.id != access.user.id,
                        )
                    )
                )
                .tuples()
                .all()
            )
            await notify(
                self._db,
                mentioned(note.body, list(members)),
                NotificationKind.MENTION,
                project_id=access.project_id,
                data={
                    "project_title": access.project.title,
                    "by": access.user.name,
                    "record_id": str(record.id),
                    "record_title": record.title or "",
                    "excerpt": excerpt(note.body),
                },
            )
        await self._db.commit()
        await self._db.refresh(note)
        return NoteOut(
            id=note.id,
            body=note.body,
            visibility=note.visibility,
            author=access.user.name,
            mine=True,
            created_at=note.created_at,
        )

    async def delete_note(self, access: ProjectAccess, note_id: uuid.UUID) -> None:
        """Only the author removes a note."""
        note = await self._db.scalar(
            select(Note).where(
                Note.id == note_id,
                Note.project_id == access.project_id,
                Note.user_id == access.user.id,
            )
        )
        if note is None:
            raise NotFoundError("That note is not yours, or it is gone.")
        await self._db.delete(note)
        await self._db.commit()

    # --- Bulk decisions ----------------------------------------------------------------

    def _bulk_targets(self, access: ProjectAccess, body: BulkDecisionIn) -> Select[Any]:
        settled = (
            select(ConflictResolution.id)
            .where(
                ConflictResolution.record_id == Record.id,
                ConflictResolution.stage == body.stage,
            )
            .exists()
        )
        statement = select(Record.id).where(
            Record.project_id == access.project_id,
            Record.is_duplicate.is_(False),
            ~settled,
        )
        if body.stage is ScreeningStage.FULL_TEXT:
            statement = statement.where(Record.ta_final == TitleAbstractStatus.INCLUDED)
        column = Record.ta_final if body.stage is ScreeningStage.TITLE_ABSTRACT else Record.ft_final
        if body.status is not None:
            statement = statement.where(column == body.status)
        if body.batch is not None:
            statement = statement.where(Record.import_batch_id == body.batch)
        if body.record_ids is not None:
            statement = statement.where(Record.id.in_(body.record_ids))
        if body.q:
            statement = apply_search(statement, parse_query(body.q))
        return statement

    async def bulk_count(self, access: ProjectAccess, body: BulkDecisionIn) -> int:
        targets = self._bulk_targets(access, body).subquery()
        return await self._db.scalar(select(func.count()).select_from(targets)) or 0

    async def bulk(
        self, access: ProjectAccess, body: BulkDecisionIn, actor: Actor
    ) -> BulkDecisionOut:
        """Decide every record the filter matches, as a final decision (guide 8.5).

        It is recorded as a resolution with source `bulk`, so it settles the records
        without pretending to be anyone's screening decision — agreement statistics are
        computed from decisions and are not skewed by it. Records already settled by a
        person are left alone.
        """
        await check_reasons(self._db, access, body.stage, body.reason_ids)
        ids = list(await self._db.scalars(self._bulk_targets(access, body)))
        if len(ids) != body.expected:
            raise BulkChangedError(
                f"The filter now matches {len(ids):,} records, not {body.expected:,}. "
                "Check them again before deciding."
            )
        if ids:
            await self._db.execute(
                insert(ConflictResolution),
                [
                    {
                        "id": uuid7(),
                        "project_id": access.project_id,
                        "record_id": record_id,
                        "stage": body.stage,
                        "resolved_by": access.user.id,
                        "final_decision": body.final_decision,
                        "reason_ids": body.reason_ids,
                        "note": body.note,
                        "source": ResolutionSource.BULK,
                    }
                    for record_id in ids
                ],
            )
            await recompute(self._db, access.project_id, body.stage, settings_of(access), ids)
        audit.record(
            self._db,
            "decision.bulk",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="project",
            entity_id=access.project_id,
            after={
                "bulk": True,
                "stage": body.stage.value,
                "decision": body.final_decision.value,
                "count": len(ids),
                "filter": {
                    "q": body.q,
                    "status": body.status,
                    "batch": str(body.batch) if body.batch else None,
                    "records": len(body.record_ids) if body.record_ids is not None else None,
                },
            },
        )
        await self._db.commit()
        if ids:
            await nudge(
                self._queue, access.project_id, body.stage, settings_of(access), count=len(ids)
            )
        return BulkDecisionOut(decided=len(ids))

    # --- Internals ---------------------------------------------------------------------

    def _require_screening(self, access: ProjectAccess, stage: ScreeningStage) -> None:
        if not screens(access, stage.value):
            raise NotScreeningError

    @staticmethod
    def _reason_required(settings: ProjectSettings, stage: ScreeningStage) -> bool:
        if stage is ScreeningStage.TITLE_ABSTRACT:
            return settings.require_reason_on_exclude_ta
        return settings.require_reason_on_exclude_ft

    async def _record(self, access: ProjectAccess, record_id: uuid.UUID) -> Record:
        record = await self._db.scalar(
            select(Record).where(
                Record.id == record_id,
                Record.project_id == access.project_id,
                Record.is_duplicate.is_(False),
            )
        )
        if record is None:
            raise NotFoundError("That record is not in this review.")
        return record

    async def _items(
        self, access: ProjectAccess, stage: ScreeningStage, records: list[Record]
    ) -> list[ScreeningItem]:
        """The records with what this caller may see of the work on them."""
        if not records:
            return []
        ids = [record.id for record in records]
        me = access.user.id
        see_all = sees_others(access)
        scores: dict[uuid.UUID, float] = dict(
            (
                await self._db.execute(
                    select(RecordScore.record_id, RecordScore.score).where(
                        RecordScore.record_id.in_(ids), RecordScore.stage == stage
                    )
                )
            )
            .tuples()
            .all()
        )

        decisions: defaultdict[uuid.UUID, list[tuple[Decision, str]]] = defaultdict(list)
        decided = (
            select(Decision, User.name)
            .join(User, User.id == Decision.user_id)
            .where(Decision.record_id.in_(ids), Decision.stage == stage)
        )
        if not see_all:
            decided = decided.where(Decision.user_id == me)
        for decision, name in await self._db.execute(decided):
            decisions[decision.record_id].append((decision, name))

        labels: defaultdict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        labelled = select(RecordLabel.record_id, RecordLabel.label_id).where(
            RecordLabel.record_id.in_(ids)
        )
        if not see_all:
            labelled = labelled.where(RecordLabel.user_id == me)
        for record_id, label_id in await self._db.execute(labelled):
            labels[record_id].add(label_id)

        notes: defaultdict[uuid.UUID, list[NoteOut]] = defaultdict(list)
        written = (
            select(Note, User.name)
            .join(User, User.id == Note.user_id)
            .where(
                Note.record_id.in_(ids),
                (Note.visibility == NoteVisibility.TEAM) | (Note.user_id == me),
            )
            .order_by(Note.created_at, Note.id)
        )
        for note, name in await self._db.execute(written):
            notes[note.record_id].append(
                NoteOut(
                    id=note.id,
                    body=note.body,
                    visibility=note.visibility,
                    author=name,
                    mine=note.user_id == me,
                    created_at=note.created_at,
                )
            )

        pdfs: dict[uuid.UUID, Fulltext] = {}
        unretrievable: set[uuid.UUID] = set()
        if stage is ScreeningStage.FULL_TEXT:
            pdfs = {
                row.record_id: row
                for row in await self._db.scalars(
                    select(Fulltext).where(Fulltext.record_id.in_(ids))
                )
            }
            unretrievable = set(
                await self._db.scalars(
                    select(UnretrievableRecord.record_id).where(
                        UnretrievableRecord.record_id.in_(ids)
                    )
                )
            )

        items: list[ScreeningItem] = []
        for record in records:
            own = next((d for d, _ in decisions[record.id] if d.user_id == me), None)
            others = (
                [
                    OtherDecision(
                        user_id=d.user_id,
                        name=name,
                        decision=d.decision,
                        reason_ids=list(d.reason_ids),
                        note=d.note,
                        updated_at=d.updated_at,
                    )
                    for d, name in decisions[record.id]
                    if d.user_id != me
                ]
                if see_all
                else None
            )
            items.append(
                ScreeningItem(
                    id=record.id,
                    title=record.title,
                    authors=record.authors,
                    year=record.year,
                    journal=record.journal,
                    volume=record.volume,
                    issue=record.issue,
                    pages=record.pages,
                    doi=record.doi,
                    pmid=record.pmid,
                    pmcid=record.pmcid,
                    url=record.url,
                    abstract=record.abstract,
                    keywords=record.keywords,
                    publication_type=record.publication_type,
                    relevance_score=scores.get(record.id),
                    fulltext=fulltext_out(pdfs[record.id]) if record.id in pdfs else None,
                    not_retrievable=record.id in unretrievable,
                    my_decision=MyDecision(
                        decision=own.decision,
                        reason_ids=list(own.reason_ids),
                        note=own.note,
                        updated_at=own.updated_at,
                    )
                    if own
                    else None,
                    labels=sorted(labels[record.id], key=lambda item: item.int),
                    notes=notes[record.id],
                    others=others,
                )
            )
        return items


def _start_for(user_id: uuid.UUID) -> float:
    """Where this person's walk through the random order begins: fixed, and spread out."""
    return int(hashlib.sha256(user_id.bytes).hexdigest()[:8], 16) / 0x1_0000_0000

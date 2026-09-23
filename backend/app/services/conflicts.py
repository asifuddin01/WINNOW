"""Conflicts: records the reviewers disagree on, and their resolution (guide 8.7).

Only resolvers reach any of this — owners, admins, and reviewers trusted with
`can_resolve_conflicts`. For them, and only on these records, blind mode is lifted: the
page exists to put the decisions side by side.
"""

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import Settings
from app.email.mailer import Mailer
from app.email.messages import discussion_requested
from app.models import (
    ConflictResolution,
    Decision,
    Note,
    NoteVisibility,
    Record,
    ResolutionSource,
    ScreeningStage,
    User,
)
from app.models.base import uuid7
from app.schemas.screening import (
    ConflictDecision,
    ConflictOut,
    ConflictPage,
    DiscussIn,
    NoteOut,
    ResolveIn,
)
from app.security.permissions import ProjectAccess
from app.services import audit
from app.services.audit import Actor
from app.services.blinding import can_resolve, settings_of
from app.services.errors import ConflictError, ForbiddenError, NotFoundError
from app.services.pagination import decode_cursor, encode_cursor
from app.services.screening import check_reasons
from app.services.status import recompute


class NotResolverError(ForbiddenError):
    code = "not_resolver"
    message = "Resolving conflicts is for owners, admins and reviewers trusted with it."


def _status_column(stage: ScreeningStage) -> Any:
    return Record.ta_final if stage is ScreeningStage.TITLE_ABSTRACT else Record.ft_final


class ConflictService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def page(
        self,
        access: ProjectAccess,
        *,
        stage: ScreeningStage = ScreeningStage.TITLE_ABSTRACT,
        reviewer_a: uuid.UUID | None = None,
        reviewer_b: uuid.UUID | None = None,
        cursor: str | None = None,
        limit: int = 25,
    ) -> ConflictPage:
        """Records in conflict at `stage`, optionally only where two given people differ."""
        self._require(access)
        statement = select(Record).where(
            Record.project_id == access.project_id,
            Record.is_duplicate.is_(False),
            _status_column(stage) == "conflict",
        )
        if reviewer_a is not None and reviewer_b is not None:
            first, second = aliased(Decision), aliased(Decision)
            statement = (
                statement.join(first, first.record_id == Record.id)
                .join(second, second.record_id == Record.id)
                .where(
                    first.stage == stage,
                    second.stage == stage,
                    first.user_id == reviewer_a,
                    second.user_id == reviewer_b,
                    first.decision != second.decision,
                )
            )
        total = await self._db.scalar(
            select(func.count()).select_from(statement.with_only_columns(Record.id).subquery())
        )
        if cursor:
            (last,) = decode_cursor(cursor, 1)
            statement = statement.where(Record.id > uuid.UUID(last))
        records = list(await self._db.scalars(statement.order_by(Record.id).limit(limit + 1)))
        items = await self._items(access, stage, records[:limit])
        next_cursor = encode_cursor(str(records[limit - 1].id)) if len(records) > limit else None
        return ConflictPage(items=items, next_cursor=next_cursor, total=total or 0)

    async def resolve(
        self, access: ProjectAccess, record_id: uuid.UUID, body: ResolveIn, actor: Actor
    ) -> ConflictOut:
        """The final word on one record (guide 8.7); it overrides the reviewers (6.4 rule 1)."""
        self._require(access)
        record = await self._record(access, record_id)
        existing = await self._db.scalar(
            select(ConflictResolution.source).where(
                ConflictResolution.record_id == record.id, ConflictResolution.stage == body.stage
            )
        )
        in_conflict = _status_value(record, body.stage) == "conflict"
        if not in_conflict and existing is not ResolutionSource.CONFLICT:
            raise ConflictError("The reviewers agree on this record; there is nothing to resolve.")
        await check_reasons(self._db, access, body.stage, body.reason_ids)
        values = insert(ConflictResolution).values(
            id=uuid7(),
            project_id=access.project_id,
            record_id=record.id,
            stage=body.stage,
            resolved_by=access.user.id,
            final_decision=body.final_decision,
            reason_ids=body.reason_ids,
            note=body.note,
            source=ResolutionSource.CONFLICT,
        )
        await self._db.execute(
            values.on_conflict_do_update(
                index_elements=[ConflictResolution.record_id, ConflictResolution.stage],
                set_={
                    "resolved_by": values.excluded.resolved_by,
                    "final_decision": values.excluded.final_decision,
                    "reason_ids": values.excluded.reason_ids,
                    "note": values.excluded.note,
                    "source": values.excluded.source,
                    "updated_at": func.now(),
                },
            )
        )
        await recompute(self._db, access.project_id, body.stage, settings_of(access), [record.id])
        audit.record(
            self._db,
            "conflict.resolved",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record.id,
            after={"stage": body.stage.value, "decision": body.final_decision.value},
        )
        await self._db.commit()
        await self._db.refresh(record)
        (item,) = await self._items(access, body.stage, [record])
        return item

    async def discuss(
        self,
        access: ProjectAccess,
        record_id: uuid.UUID,
        body: DiscussIn,
        actor: Actor,
        *,
        mailer: Mailer,
        settings: Settings,
    ) -> NoteOut:
        """Guide 8.7's "Discuss": a team note on the record, and an email to its reviewers."""
        self._require(access)
        record = await self._record(access, record_id)
        note = Note(
            project_id=access.project_id,
            record_id=record.id,
            user_id=access.user.id,
            body=body.body.strip(),
            visibility=NoteVisibility.TEAM,
        )
        self._db.add(note)
        reviewers = list(
            await self._db.scalars(
                select(User.email)
                .join(Decision, Decision.user_id == User.id)
                .where(
                    Decision.record_id == record.id,
                    Decision.stage == body.stage,
                    User.id != access.user.id,
                    User.deleted_at.is_(None),
                )
            )
        )
        audit.record(
            self._db,
            "conflict.discussion",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record.id,
            after={"notified": len(reviewers)},
        )
        await self._db.commit()
        await self._db.refresh(note)
        link = f"{settings.public_origin}/p/{access.project_id}/conflicts?record={record.id}"
        for email in reviewers:
            await mailer.send(
                discussion_requested(
                    email, asker=access.user.name, project_title=access.project.title, link=link
                )
            )
        return NoteOut(
            id=note.id,
            body=note.body,
            visibility=note.visibility,
            author=access.user.name,
            mine=True,
            created_at=note.created_at,
        )

    # --- Internals ---------------------------------------------------------------------

    def _require(self, access: ProjectAccess) -> None:
        if not can_resolve(access):
            raise NotResolverError

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
    ) -> list[ConflictOut]:
        if not records:
            return []
        ids = [record.id for record in records]
        decisions: defaultdict[uuid.UUID, list[ConflictDecision]] = defaultdict(list)
        for decision, name in await self._db.execute(
            select(Decision, User.name)
            .join(User, User.id == Decision.user_id)
            .where(Decision.record_id.in_(ids), Decision.stage == stage)
            .order_by(Decision.created_at, Decision.id)
        ):
            decisions[decision.record_id].append(
                ConflictDecision(
                    user_id=decision.user_id,
                    name=name,
                    decision=decision.decision,
                    reason_ids=list(decision.reason_ids),
                    note=decision.note,
                )
            )
        notes: defaultdict[uuid.UUID, list[NoteOut]] = defaultdict(list)
        for note, name in await self._db.execute(
            select(Note, User.name)
            .join(User, User.id == Note.user_id)
            .where(
                Note.record_id.in_(ids),
                (Note.visibility == NoteVisibility.TEAM) | (Note.user_id == access.user.id),
            )
            .order_by(Note.created_at, Note.id)
        ):
            notes[note.record_id].append(
                NoteOut(
                    id=note.id,
                    body=note.body,
                    visibility=note.visibility,
                    author=name,
                    mine=note.user_id == access.user.id,
                    created_at=note.created_at,
                )
            )
        resolutions: dict[uuid.UUID, Any] = {}
        for record_id, final in await self._db.execute(
            select(ConflictResolution.record_id, ConflictResolution.final_decision).where(
                ConflictResolution.record_id.in_(ids), ConflictResolution.stage == stage
            )
        ):
            resolutions[record_id] = final
        return [
            ConflictOut(
                record_id=record.id,
                title=record.title,
                authors=record.authors,
                year=record.year,
                journal=record.journal,
                abstract=record.abstract,
                doi=record.doi,
                decisions=decisions[record.id],
                notes=notes[record.id],
                resolution=resolutions.get(record.id),
            )
            for record in records
        ]


def _status_value(record: Record, stage: ScreeningStage) -> str:
    status = record.ta_final if stage is ScreeningStage.TITLE_ABSTRACT else record.ft_final
    return status.value

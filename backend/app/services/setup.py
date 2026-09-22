"""Criteria, keyword groups and keywords, exclusion reasons and labels (guide 6.1, 8.2).

Each list is small and capped, so it is returned whole rather than paginated. Every lookup
by id also filters by the verified project, so an id from another review is simply not
found (guide 12.2); keywords are reached through their group's project.
"""

import uuid
from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Criterion,
    CriterionKind,
    ExclusionReason,
    Keyword,
    KeywordGroup,
    Label,
)
from app.schemas.setup import (
    CriterionCreate,
    CriterionUpdate,
    KeywordGroupCreate,
    KeywordGroupOut,
    KeywordGroupUpdate,
    KeywordOut,
    KeywordsCreate,
    KeywordUpdate,
    LabelCreate,
    LabelUpdate,
    ReasonCreate,
    ReasonUpdate,
)
from app.security.patterns import PatternError, check_pattern
from app.security.permissions import ProjectAccess
from app.services import audit
from app.services.audit import Actor
from app.services.errors import (
    DuplicateNameError,
    InvalidPatternError,
    LimitReachedError,
    NotFoundError,
)

MAX_CRITERIA = 100
MAX_KEYWORD_GROUPS = 50
MAX_KEYWORDS = 1_000  # per project, across its groups
MAX_REASONS = 50
MAX_LABELS = 100


class _Ordered(Protocol):
    position: int


def _renumber(items: Sequence[_Ordered]) -> None:
    for position, item in enumerate(items):
        item.position = position


def _move[T: _Ordered](items: list[T], item: T, position: int) -> None:
    """Move `item` to `position` among `items` (which include it) and renumber."""
    items.remove(item)
    items.insert(min(position, len(items)), item)
    _renumber(items)


def _check_term(term: str, is_regex: bool) -> None:
    if not is_regex:
        return
    try:
        check_pattern(term)
    except PatternError as error:
        raise InvalidPatternError(f"“{term}”: {error}") from None


class SetupService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _audit(
        self,
        access: ProjectAccess,
        actor: Actor,
        action: str,
        entity_id: uuid.UUID,
        *,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        entity_type = action.split(".")[1]
        audit.record(
            self._db,
            action,
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
        )

    async def _commit_unique(self, message: str | None = None) -> None:
        """Commit; a unique name taken a moment ago by someone else is a 409, not a 500."""
        try:
            await self._db.commit()
        except IntegrityError:
            await self._db.rollback()
            raise DuplicateNameError(message) from None

    async def _count(self, model: Any, project_id: uuid.UUID) -> int:
        count = await self._db.scalar(
            select(func.count()).select_from(model).where(model.project_id == project_id)
        )
        return count or 0

    # --- Criteria ----------------------------------------------------------------------

    async def criteria(self, access: ProjectAccess) -> list[Criterion]:
        rows = await self._db.scalars(
            select(Criterion)
            .where(Criterion.project_id == access.project_id)
            .order_by(Criterion.kind, Criterion.position)
        )
        return list(rows)

    async def _criteria_of_kind(
        self, access: ProjectAccess, kind: CriterionKind
    ) -> list[Criterion]:
        return [c for c in await self.criteria(access) if c.kind == kind]

    async def _criterion(self, access: ProjectAccess, criterion_id: uuid.UUID) -> Criterion:
        criterion = await self._db.scalar(
            select(Criterion).where(
                Criterion.id == criterion_id, Criterion.project_id == access.project_id
            )
        )
        if criterion is None:
            raise NotFoundError("That criterion no longer exists.")
        return criterion

    async def add_criterion(
        self, access: ProjectAccess, body: CriterionCreate, actor: Actor
    ) -> Criterion:
        if await self._count(Criterion, access.project_id) >= MAX_CRITERIA:
            raise LimitReachedError(f"A review can have up to {MAX_CRITERIA} criteria.")
        siblings = await self._criteria_of_kind(access, body.kind)
        criterion = Criterion(
            project_id=access.project_id, kind=body.kind, text=body.text, position=len(siblings)
        )
        self._db.add(criterion)
        await self._db.flush()
        self._audit(
            access,
            actor,
            "setup.criterion.created",
            criterion.id,
            after={"kind": body.kind.value, "text": body.text},
        )
        await self._db.commit()
        return criterion

    async def update_criterion(
        self, access: ProjectAccess, criterion_id: uuid.UUID, body: CriterionUpdate, actor: Actor
    ) -> Criterion:
        criterion = await self._criterion(access, criterion_id)
        before = {"kind": criterion.kind.value, "text": criterion.text}
        if body.kind is not None and body.kind != criterion.kind:
            old_kind = criterion.kind
            criterion.kind = body.kind
            criterion.position = MAX_CRITERIA  # last among its new siblings, renumbered below
            await self._db.flush()
            _renumber(await self._criteria_of_kind(access, old_kind))
            _renumber(await self._criteria_of_kind(access, body.kind))
        if body.text is not None:
            criterion.text = body.text
        if body.position is not None:
            _move(await self._criteria_of_kind(access, criterion.kind), criterion, body.position)
        after = {"kind": criterion.kind.value, "text": criterion.text}
        if after != before:
            self._audit(
                access, actor, "setup.criterion.updated", criterion.id, before=before, after=after
            )
        await self._db.commit()
        return criterion

    async def delete_criterion(
        self, access: ProjectAccess, criterion_id: uuid.UUID, actor: Actor
    ) -> None:
        criterion = await self._criterion(access, criterion_id)
        await self._db.delete(criterion)
        await self._db.flush()
        _renumber(await self._criteria_of_kind(access, criterion.kind))
        self._audit(
            access,
            actor,
            "setup.criterion.deleted",
            criterion.id,
            before={"kind": criterion.kind.value, "text": criterion.text},
        )
        await self._db.commit()

    # --- Keyword groups and keywords ---------------------------------------------------

    async def keyword_groups(self, access: ProjectAccess) -> list[KeywordGroupOut]:
        groups = list(
            await self._db.scalars(
                select(KeywordGroup)
                .where(KeywordGroup.project_id == access.project_id)
                .order_by(KeywordGroup.id)
            )
        )
        keywords = await self._db.scalars(
            select(Keyword)
            .join(KeywordGroup, KeywordGroup.id == Keyword.group_id)
            .where(KeywordGroup.project_id == access.project_id)
            .order_by(Keyword.term)
        )
        by_group: dict[uuid.UUID, list[KeywordOut]] = {group.id: [] for group in groups}
        for keyword in keywords:
            by_group[keyword.group_id].append(
                KeywordOut.model_validate(keyword, from_attributes=True)
            )
        return [self._group_out(group, by_group[group.id]) for group in groups]

    @staticmethod
    def _group_out(group: KeywordGroup, keywords: list[KeywordOut]) -> KeywordGroupOut:
        return KeywordGroupOut(
            id=group.id,
            name=group.name,
            color=group.color,  # type: ignore[arg-type]  # validated on the way in
            kind=group.kind,
            keywords=keywords,
        )

    async def keyword_group(self, access: ProjectAccess, group_id: uuid.UUID) -> KeywordGroupOut:
        group = await self._group(access, group_id)
        keywords = await self._db.scalars(
            select(Keyword).where(Keyword.group_id == group.id).order_by(Keyword.term)
        )
        return self._group_out(
            group, [KeywordOut.model_validate(k, from_attributes=True) for k in keywords]
        )

    async def _group(self, access: ProjectAccess, group_id: uuid.UUID) -> KeywordGroup:
        group = await self._db.scalar(
            select(KeywordGroup).where(
                KeywordGroup.id == group_id, KeywordGroup.project_id == access.project_id
            )
        )
        if group is None:
            raise NotFoundError("That keyword group no longer exists.")
        return group

    async def add_keyword_group(
        self, access: ProjectAccess, body: KeywordGroupCreate, actor: Actor
    ) -> KeywordGroup:
        if await self._count(KeywordGroup, access.project_id) >= MAX_KEYWORD_GROUPS:
            raise LimitReachedError(f"A review can have up to {MAX_KEYWORD_GROUPS} keyword groups.")
        group = KeywordGroup(
            project_id=access.project_id, name=body.name, color=body.color, kind=body.kind
        )
        self._db.add(group)
        await self._db.flush()
        self._audit(
            access,
            actor,
            "setup.keyword_group.created",
            group.id,
            after={"name": body.name, "kind": body.kind.value},
        )
        await self._db.commit()
        return group

    async def update_keyword_group(
        self, access: ProjectAccess, group_id: uuid.UUID, body: KeywordGroupUpdate, actor: Actor
    ) -> KeywordGroup:
        group = await self._group(access, group_id)
        before = {"name": group.name, "color": group.color, "kind": group.kind.value}
        group.name = body.name or group.name
        group.color = body.color or group.color
        group.kind = body.kind or group.kind
        after = {"name": group.name, "color": group.color, "kind": group.kind.value}
        if after != before:
            self._audit(
                access, actor, "setup.keyword_group.updated", group.id, before=before, after=after
            )
        await self._db.commit()
        return group

    async def delete_keyword_group(
        self, access: ProjectAccess, group_id: uuid.UUID, actor: Actor
    ) -> None:
        group = await self._group(access, group_id)
        await self._db.delete(group)  # its keywords go with it (ON DELETE CASCADE)
        self._audit(
            access, actor, "setup.keyword_group.deleted", group.id, before={"name": group.name}
        )
        await self._db.commit()

    async def add_keywords(self, access: ProjectAccess, body: KeywordsCreate, actor: Actor) -> None:
        group = await self._group(access, body.group_id)
        for term in body.terms:
            _check_term(term, body.is_regex)
        existing = {
            term.lower()
            for term in await self._db.scalars(
                select(Keyword.term).where(Keyword.group_id == group.id)
            )
        }
        new_terms: list[str] = []
        for term in body.terms:
            if term.lower() not in existing:
                existing.add(term.lower())
                new_terms.append(term)
        total = await self._db.scalar(
            select(func.count())
            .select_from(Keyword)
            .join(KeywordGroup, KeywordGroup.id == Keyword.group_id)
            .where(KeywordGroup.project_id == access.project_id)
        )
        if (total or 0) + len(new_terms) > MAX_KEYWORDS:
            raise LimitReachedError(f"A review can have up to {MAX_KEYWORDS} keywords.")
        for term in new_terms:
            keyword = Keyword(
                group_id=group.id, term=term, is_regex=body.is_regex, whole_word=body.whole_word
            )
            self._db.add(keyword)
            await self._db.flush()
            self._audit(
                access,
                actor,
                "setup.keyword.created",
                keyword.id,
                after={"group_id": str(group.id), "term": term, "is_regex": body.is_regex},
            )
        await self._commit_unique("That keyword is already in this group.")

    async def _keyword(self, access: ProjectAccess, keyword_id: uuid.UUID) -> Keyword:
        keyword = await self._db.scalar(
            select(Keyword)
            .join(KeywordGroup, KeywordGroup.id == Keyword.group_id)
            .where(Keyword.id == keyword_id, KeywordGroup.project_id == access.project_id)
        )
        if keyword is None:
            raise NotFoundError("That keyword no longer exists.")
        return keyword

    async def update_keyword(
        self, access: ProjectAccess, keyword_id: uuid.UUID, body: KeywordUpdate, actor: Actor
    ) -> Keyword:
        keyword = await self._keyword(access, keyword_id)
        before = {
            "term": keyword.term,
            "is_regex": keyword.is_regex,
            "whole_word": keyword.whole_word,
        }
        term = body.term if body.term is not None else keyword.term
        is_regex = body.is_regex if body.is_regex is not None else keyword.is_regex
        _check_term(term, is_regex)
        if term.lower() != keyword.term.lower():
            taken = await self._db.scalar(
                select(Keyword.id).where(
                    Keyword.group_id == keyword.group_id, func.lower(Keyword.term) == term.lower()
                )
            )
            if taken is not None:
                raise DuplicateNameError("That keyword is already in this group.")
        keyword.term, keyword.is_regex = term, is_regex
        if body.whole_word is not None:
            keyword.whole_word = body.whole_word
        after = {
            "term": keyword.term,
            "is_regex": keyword.is_regex,
            "whole_word": keyword.whole_word,
        }
        if after != before:
            self._audit(
                access, actor, "setup.keyword.updated", keyword.id, before=before, after=after
            )
        await self._commit_unique("That keyword is already in this group.")
        return keyword

    async def delete_keyword(
        self, access: ProjectAccess, keyword_id: uuid.UUID, actor: Actor
    ) -> None:
        keyword = await self._keyword(access, keyword_id)
        await self._db.delete(keyword)
        self._audit(
            access, actor, "setup.keyword.deleted", keyword.id, before={"term": keyword.term}
        )
        await self._db.commit()

    # --- Exclusion reasons -------------------------------------------------------------

    async def reasons(self, access: ProjectAccess) -> list[ExclusionReason]:
        rows = await self._db.scalars(
            select(ExclusionReason)
            .where(ExclusionReason.project_id == access.project_id)
            .order_by(ExclusionReason.position)
        )
        return list(rows)

    async def _reason(self, access: ProjectAccess, reason_id: uuid.UUID) -> ExclusionReason:
        reason = await self._db.scalar(
            select(ExclusionReason).where(
                ExclusionReason.id == reason_id, ExclusionReason.project_id == access.project_id
            )
        )
        if reason is None:
            raise NotFoundError("That exclusion reason no longer exists.")
        return reason

    async def _check_reason_label(
        self, access: ProjectAccess, label: str, exclude_id: uuid.UUID | None = None
    ) -> None:
        query = select(ExclusionReason.id).where(
            ExclusionReason.project_id == access.project_id,
            func.lower(ExclusionReason.label) == label.lower(),
        )
        if exclude_id is not None:
            query = query.where(ExclusionReason.id != exclude_id)
        if await self._db.scalar(query) is not None:
            raise DuplicateNameError("There is already an exclusion reason with that name.")

    async def add_reason(
        self, access: ProjectAccess, body: ReasonCreate, actor: Actor
    ) -> ExclusionReason:
        existing = await self.reasons(access)
        if len(existing) >= MAX_REASONS:
            raise LimitReachedError(f"A review can have up to {MAX_REASONS} exclusion reasons.")
        await self._check_reason_label(access, body.label)
        reason = ExclusionReason(
            project_id=access.project_id, label=body.label, stage=body.stage, position=len(existing)
        )
        self._db.add(reason)
        await self._db.flush()
        self._audit(
            access,
            actor,
            "setup.exclusion_reason.created",
            reason.id,
            after={"label": body.label, "stage": body.stage.value},
        )
        await self._commit_unique("There is already an exclusion reason with that name.")
        return reason

    async def update_reason(
        self, access: ProjectAccess, reason_id: uuid.UUID, body: ReasonUpdate, actor: Actor
    ) -> ExclusionReason:
        reason = await self._reason(access, reason_id)
        before = {"label": reason.label, "stage": reason.stage.value}
        if body.label is not None and body.label != reason.label:
            await self._check_reason_label(access, body.label, exclude_id=reason.id)
            reason.label = body.label
        if body.stage is not None:
            reason.stage = body.stage
        if body.position is not None:
            _move(await self.reasons(access), reason, body.position)
        after = {"label": reason.label, "stage": reason.stage.value}
        if after != before:
            self._audit(
                access,
                actor,
                "setup.exclusion_reason.updated",
                reason.id,
                before=before,
                after=after,
            )
        await self._commit_unique("There is already an exclusion reason with that name.")
        return reason

    async def delete_reason(
        self, access: ProjectAccess, reason_id: uuid.UUID, actor: Actor
    ) -> None:
        reason = await self._reason(access, reason_id)
        await self._db.delete(reason)
        await self._db.flush()
        _renumber(await self.reasons(access))
        self._audit(
            access,
            actor,
            "setup.exclusion_reason.deleted",
            reason.id,
            before={"label": reason.label},
        )
        await self._db.commit()

    # --- Labels ------------------------------------------------------------------------

    async def labels(self, access: ProjectAccess) -> list[Label]:
        rows = await self._db.scalars(
            select(Label).where(Label.project_id == access.project_id).order_by(Label.id)
        )
        return list(rows)

    async def _label(self, access: ProjectAccess, label_id: uuid.UUID) -> Label:
        label = await self._db.scalar(
            select(Label).where(Label.id == label_id, Label.project_id == access.project_id)
        )
        if label is None:
            raise NotFoundError("That label no longer exists.")
        return label

    async def _check_label_name(
        self, access: ProjectAccess, name: str, exclude_id: uuid.UUID | None = None
    ) -> None:
        query = select(Label.id).where(
            Label.project_id == access.project_id, func.lower(Label.name) == name.lower()
        )
        if exclude_id is not None:
            query = query.where(Label.id != exclude_id)
        if await self._db.scalar(query) is not None:
            raise DuplicateNameError("There is already a label with that name.")

    async def add_label(self, access: ProjectAccess, body: LabelCreate, actor: Actor) -> Label:
        if await self._count(Label, access.project_id) >= MAX_LABELS:
            raise LimitReachedError(f"A review can have up to {MAX_LABELS} labels.")
        await self._check_label_name(access, body.name)
        label = Label(project_id=access.project_id, name=body.name, color=body.color)
        self._db.add(label)
        await self._db.flush()
        self._audit(access, actor, "setup.label.created", label.id, after={"name": body.name})
        await self._commit_unique("There is already a label with that name.")
        return label

    async def update_label(
        self, access: ProjectAccess, label_id: uuid.UUID, body: LabelUpdate, actor: Actor
    ) -> Label:
        label = await self._label(access, label_id)
        before = {"name": label.name, "color": label.color}
        if body.name is not None and body.name != label.name:
            await self._check_label_name(access, body.name, exclude_id=label.id)
            label.name = body.name
        label.color = body.color or label.color
        after = {"name": label.name, "color": label.color}
        if after != before:
            self._audit(access, actor, "setup.label.updated", label.id, before=before, after=after)
        await self._commit_unique("There is already a label with that name.")
        return label

    async def delete_label(self, access: ProjectAccess, label_id: uuid.UUID, actor: Actor) -> None:
        label = await self._label(access, label_id)
        await self._db.delete(label)
        self._audit(access, actor, "setup.label.deleted", label.id, before={"name": label.name})
        await self._db.commit()

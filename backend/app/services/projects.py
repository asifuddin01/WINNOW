"""Projects: creating, listing, editing, deleting, transferring and copying a review's setup.

Every method that touches an existing project takes a ProjectAccess, which exists only
after the membership check, and scopes its queries by `access.project_id` (guide 12.2).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.llm.providers import is_configured as llm_configured
from app.models import (
    AuditLog,
    Criterion,
    ExclusionReason,
    Keyword,
    KeywordGroup,
    Label,
    Project,
    ProjectMember,
    ProjectRole,
    ReasonStage,
    ScreeningStage,
    User,
)
from app.schemas.projects import (
    MembershipOut,
    PersonOut,
    Pico,
    ProjectCreate,
    ProjectOut,
    ProjectPage,
    ProjectSettings,
    ProjectSummary,
    ProjectUpdate,
    settings_from_json,
)
from app.security.permissions import Capability, ProjectAccess, can
from app.services import audit
from app.services.audit import Actor
from app.services.errors import (
    ConflictError,
    EmailUnverifiedError,
    FeatureUnavailableError,
    ForbiddenError,
    InvalidCursorError,
    NotFoundError,
    OwnerTwoFactorRequiredError,
)
from app.services.pagination import decode_cursor, encode_cursor
from app.services.status import recompute

# Guide 8.2: every new review starts with these, in this order.
DEFAULT_EXCLUSION_REASONS: tuple[tuple[str, ReasonStage], ...] = (
    ("Wrong population", ReasonStage.BOTH),
    ("Wrong intervention", ReasonStage.BOTH),
    ("Wrong comparator", ReasonStage.BOTH),
    ("Wrong outcome", ReasonStage.BOTH),
    ("Wrong study design", ReasonStage.BOTH),
    ("Wrong publication type", ReasonStage.BOTH),
    ("Not in an included language", ReasonStage.BOTH),
    ("Duplicate", ReasonStage.BOTH),
    ("Full text unavailable", ReasonStage.FULL_TEXT),
)
_BASIC_FIELDS = ("title", "review_type", "description", "research_question", "status")


def _now() -> datetime:
    return datetime.now(UTC)


def _member_count() -> Any:
    """How many members a project has, as a column for the projects query. It correlates
    only to projects: the outer query joins project_members itself."""
    return (
        select(func.count())
        .select_from(ProjectMember)
        .where(ProjectMember.project_id == Project.id)
        .correlate(Project)
        .scalar_subquery()
    )


def _json(value: Any) -> Any:
    """A value as it should appear in an audit entry's JSON."""
    if isinstance(value, Pico):
        return value.model_dump()
    return value


class ProjectService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    # --- Creating ----------------------------------------------------------------------

    def default_settings(self) -> ProjectSettings:
        # Alone on the instance, nobody could be the second reviewer.
        if self._settings.winnow_single_user:
            return ProjectSettings(reviewers_per_record_ta=1, reviewers_per_record_ft=1)
        return ProjectSettings()

    def check_can_own(self, user: User) -> None:
        """Owning a review needs a confirmed email, and 2FA if the instance requires it."""
        if not user.email_verified:
            raise EmailUnverifiedError
        if self._settings.require_owner_2fa and not user.totp_enabled:
            raise OwnerTwoFactorRequiredError

    async def create(self, user: User, body: ProjectCreate, actor: Actor) -> ProjectOut:
        self.check_can_own(user)
        access = await self._new_project(
            user,
            title=body.title,
            review_type=body.review_type,
            description=body.description,
            research_question=body.research_question,
            pico=body.pico,
            settings=self.default_settings(),
        )
        project = access.project
        for position, (label, stage) in enumerate(DEFAULT_EXCLUSION_REASONS):
            self._db.add(
                ExclusionReason(project_id=project.id, label=label, stage=stage, position=position)
            )
        audit.record(
            self._db,
            "project.created",
            actor,
            user_id=user.id,
            project_id=project.id,
            entity_type="project",
            entity_id=project.id,
            after={"title": project.title, "review_type": project.review_type.value},
        )
        await self._db.commit()
        return await self.detail(access)

    async def _new_project(
        self,
        owner: User,
        *,
        title: str,
        review_type: Any,
        description: str | None,
        research_question: str | None,
        pico: Pico | None,
        settings: ProjectSettings,
    ) -> ProjectAccess:
        project = Project(
            owner_id=owner.id,
            title=title,
            review_type=review_type,
            description=description,
            research_question=research_question,
            pico=None if pico is None or pico.is_empty() else pico.model_dump(),
            settings=settings.model_dump(mode="json"),
        )
        self._db.add(project)
        await self._db.flush()
        member = ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectRole.OWNER)
        self._db.add(member)
        await self._db.flush()
        return ProjectAccess(user=owner, project=project, member=member)

    # --- Reading -----------------------------------------------------------------------

    async def list_for_user(self, user: User, cursor: str | None, limit: int) -> ProjectPage:
        """The caller's reviews, newest first (ids are time-ordered UUIDv7)."""
        last_activity = (
            select(func.max(AuditLog.created_at))
            .where(AuditLog.project_id == Project.id)
            .correlate(Project)
            .scalar_subquery()
        )
        query = (
            select(
                Project,
                ProjectMember.role,
                _member_count(),
                func.coalesce(last_activity, Project.updated_at),
            )
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user.id, Project.deleted_at.is_(None))
            .order_by(Project.id.desc())
            .limit(limit + 1)
        )
        if cursor is not None:
            (after,) = decode_cursor(cursor, 1)
            query = query.where(Project.id < _uuid(after))
        rows = (await self._db.execute(query)).all()
        items = [
            ProjectSummary(
                id=project.id,
                title=project.title,
                review_type=project.review_type,
                status=project.status,
                role=role,
                member_count=count,
                last_activity_at=max(activity, project.updated_at),
                created_at=project.created_at,
            )
            for project, role, count, activity in rows[:limit]
        ]
        next_cursor = encode_cursor(str(items[-1].id)) if len(rows) > limit else None
        return ProjectPage(items=items, next_cursor=next_cursor)

    async def detail(self, access: ProjectAccess) -> ProjectOut:
        project, member = access.project, access.member
        owner = await self._db.get_one(User, project.owner_id)
        count = (
            await self._db.scalar(
                select(func.count())
                .select_from(ProjectMember)
                .where(ProjectMember.project_id == project.id)
            )
            or 0
        )
        return ProjectOut(
            id=project.id,
            title=project.title,
            description=project.description,
            review_type=project.review_type,
            research_question=project.research_question,
            pico=Pico.model_validate(project.pico) if project.pico else None,
            status=project.status,
            settings=settings_from_json(project.settings),
            owner=PersonOut(
                id=owner.id,
                name=owner.name,
                email=owner.email if access.can(Capability.MANAGE_MEMBERS) else None,
            ),
            membership=MembershipOut(
                role=member.role,
                can_resolve_conflicts=member.can_resolve_conflicts,
                stages=[ScreeningStage(stage) for stage in member.stages],
                keep_blind=member.keep_blind,
            ),
            permissions=[capability for capability in Capability if can(member, capability)],
            member_count=count,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    # --- Changing ----------------------------------------------------------------------

    async def update(self, access: ProjectAccess, body: ProjectUpdate, actor: Actor) -> None:
        project = access.project
        before: dict[str, Any] = {}
        after: dict[str, Any] = {}
        for field in _BASIC_FIELDS:
            if field in body.model_fields_set:
                value = getattr(body, field)
                if getattr(project, field) != value:
                    before[field] = _json(getattr(project, field))
                    after[field] = _json(value)
                    setattr(project, field, value)
        if "pico" in body.model_fields_set:
            pico = None if body.pico is None or body.pico.is_empty() else body.pico.model_dump()
            if project.pico != pico:
                before["pico"], after["pico"] = project.pico, pico
                project.pico = pico
        if before:
            audit.record(
                self._db,
                "project.updated",
                actor,
                user_id=access.user.id,
                project_id=project.id,
                entity_type="project",
                entity_id=project.id,
                before=before,
                after=after,
            )
        if body.settings is not None:
            changed = self._change_settings(
                access, body.settings.model_dump(exclude_unset=True), actor
            )
            await self._recompute_if_needed(access, changed)
        await self._db.commit()
        # updated_at is set by the database, so read the row back before reporting it.
        await self._db.refresh(access.project)

    async def _recompute_if_needed(self, access: ProjectAccess, changed: list[str]) -> None:
        """How many reviewers a record needs, and what a maybe counts as, decide every
        record's status (guide 6.4): when they change, every status is worked out again."""
        stages = []
        if {"reviewers_per_record_ta", "maybe_counts_as"} & set(changed):
            stages.append(ScreeningStage.TITLE_ABSTRACT)
        if {"reviewers_per_record_ft", "maybe_counts_as"} & set(changed):
            stages.append(ScreeningStage.FULL_TEXT)
        settings = settings_from_json(access.project.settings)
        for stage in stages:
            await recompute(self._db, access.project_id, stage, settings)

    def _change_settings(
        self, access: ProjectAccess, changes: dict[str, Any], actor: Actor
    ) -> list[str]:
        project = access.project
        current = settings_from_json(project.settings)
        updated = ProjectSettings.model_validate({**current.model_dump(), **changes})
        if (
            updated.llm_assist_enabled
            and not current.llm_assist_enabled
            and not llm_configured(self._settings)
        ):
            raise FeatureUnavailableError(
                "AI suggestions need an AI provider set up on this Winnow instance first."
            )
        if (
            updated.llm_assist_enabled
            and not current.llm_assist_enabled
            and access.role is not ProjectRole.OWNER
        ):
            # Guide 8.11: sending records to a provider is the owner's decision. Anyone who
            # may change the settings may turn it off again.
            raise ForbiddenError("Only the review's owner can turn AI suggestions on.")
        old, new = current.model_dump(mode="json"), updated.model_dump(mode="json")
        changed = [key for key in new if old[key] != new[key]]
        if not changed:
            return []
        project.settings = new
        audit.record(
            self._db,
            "project.settings_changed",
            actor,
            user_id=access.user.id,
            project_id=project.id,
            entity_type="project",
            entity_id=project.id,
            before={key: old[key] for key in changed},
            after={key: new[key] for key in changed},
        )
        if "blind_mode" in changed:  # guide 8.6 and 12.8 call this one out
            audit.record(
                self._db,
                "project.blind_mode_changed",
                actor,
                user_id=access.user.id,
                project_id=project.id,
                entity_type="project",
                entity_id=project.id,
                before={"blind_mode": old["blind_mode"]},
                after={"blind_mode": new["blind_mode"]},
            )
        return changed

    async def delete(self, access: ProjectAccess, actor: Actor) -> None:
        """Soft delete: the review disappears for everyone; its rows stay for recovery."""
        access.project.deleted_at = _now()
        audit.record(
            self._db,
            "project.deleted",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="project",
            entity_id=access.project_id,
            before={"title": access.project.title},
        )
        await self._db.commit()

    async def transfer(self, access: ProjectAccess, new_owner_id: uuid.UUID, actor: Actor) -> None:
        """Hand the review to another member; the old owner stays on as an admin."""
        if new_owner_id == access.user.id:
            raise ConflictError("You already own this review.")
        row = (
            await self._db.execute(
                select(ProjectMember, User)
                .join(User, User.id == ProjectMember.user_id)
                .where(
                    ProjectMember.project_id == access.project_id,
                    ProjectMember.user_id == new_owner_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Only a member of this review can become its owner.")
        target, target_user = row
        if self._settings.require_owner_2fa and not target_user.totp_enabled:
            raise OwnerTwoFactorRequiredError(
                f"{target_user.name} must turn on two-factor authentication before they can "
                "own a review on this Winnow instance."
            )
        # Demote first: the one-owner index is checked row by row.
        access.member.role = ProjectRole.ADMIN
        await self._db.flush()
        target.role = ProjectRole.OWNER
        access.project.owner_id = new_owner_id
        audit.record(
            self._db,
            "project.transferred",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="project",
            entity_id=access.project_id,
            before={"owner_id": str(access.user.id)},
            after={"owner_id": str(new_owner_id)},
        )
        await self._db.commit()
        await self._db.refresh(access.project)
        await self._db.refresh(access.member)

    # --- Copying a setup ---------------------------------------------------------------

    async def duplicate_setup(self, access: ProjectAccess, title: str, actor: Actor) -> ProjectOut:
        """A new review, owned by the caller, with this one's settings, criteria, keywords,
        exclusion reasons and labels, but no members, records or decisions."""
        user, source = access.user, access.project
        self.check_can_own(user)
        copy = await self._new_project(
            user,
            title=title,
            review_type=source.review_type,
            description=source.description,
            research_question=source.research_question,
            pico=Pico.model_validate(source.pico) if source.pico else None,
            settings=settings_from_json(source.settings),
        )
        project = copy.project
        pid = source.id
        for criterion in await self._all(Criterion, pid, Criterion.position):
            self._db.add(
                Criterion(
                    project_id=project.id,
                    kind=criterion.kind,
                    text=criterion.text,
                    position=criterion.position,
                )
            )
        for reason in await self._all(ExclusionReason, pid, ExclusionReason.position):
            self._db.add(
                ExclusionReason(
                    project_id=project.id,
                    label=reason.label,
                    stage=reason.stage,
                    position=reason.position,
                )
            )
        for label in await self._all(Label, pid, Label.id):
            self._db.add(Label(project_id=project.id, name=label.name, color=label.color))
        for group in await self._all(KeywordGroup, pid, KeywordGroup.id):
            group_copy = KeywordGroup(
                project_id=project.id, name=group.name, color=group.color, kind=group.kind
            )
            self._db.add(group_copy)
            await self._db.flush()
            keywords = await self._db.scalars(
                select(Keyword).where(Keyword.group_id == group.id).order_by(Keyword.term)
            )
            for keyword in keywords:
                self._db.add(
                    Keyword(
                        group_id=group_copy.id,
                        term=keyword.term,
                        is_regex=keyword.is_regex,
                        whole_word=keyword.whole_word,
                    )
                )
        audit.record(
            self._db,
            "project.created",
            actor,
            user_id=user.id,
            project_id=project.id,
            entity_type="project",
            entity_id=project.id,
            after={"title": title, "copied_setup_from": str(pid)},
        )
        await self._db.commit()
        return await self.detail(copy)

    async def _all[T: (Criterion, ExclusionReason, Label, KeywordGroup)](
        self, model: type[T], project_id: uuid.UUID, order: Any
    ) -> list[T]:
        rows = await self._db.scalars(
            select(model).where(model.project_id == project_id).order_by(order)
        )
        return list(rows)


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise InvalidCursorError from None

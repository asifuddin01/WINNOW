"""Members and invitations (guide 7, 8.2).

Owners and admins manage members, but nobody changes the owner here: ownership moves only
by transfer. An invitation works once, for a week, and only for someone signed in with
the invited, confirmed email address, so a forwarded link is useless to anyone else.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import Settings
from app.email import messages
from app.email.mailer import Mailer
from app.models import (
    NotificationKind,
    Project,
    ProjectInvite,
    ProjectMember,
    ProjectRole,
    ScreeningStage,
    User,
)
from app.schemas.projects import (
    InviteCreate,
    InviteOut,
    InvitePreview,
    MemberOut,
    MemberPage,
    MembershipOut,
    MembershipUpdate,
    MemberUpdate,
    PersonOut,
)
from app.security.permissions import Capability, ProjectAccess
from app.security.tokens import hash_token, new_token
from app.services import audit
from app.services.audit import Actor
from app.services.errors import (
    AlreadyMemberError,
    ConflictError,
    EmailUnverifiedError,
    InvalidCursorError,
    InvalidTokenError,
    InviteEmailMismatchError,
    InvitesUnavailableError,
    LimitReachedError,
    NotFoundError,
    OwnerProtectedError,
)
from app.services.notifications import notify
from app.services.pagination import decode_cursor, encode_cursor

INVITE_TTL = timedelta(days=7)
MAX_PENDING_INVITES = 100
ROLE_NAMES = {
    ProjectRole.OWNER: "owner",
    ProjectRole.ADMIN: "admin",
    ProjectRole.REVIEWER: "reviewer",
    ProjectRole.VIEWER: "viewer",
}


def _now() -> datetime:
    return datetime.now(UTC)


def mask_email(email: str) -> str:
    """Enough of an address to recognise it: "a•••@example.org"."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}•••@{domain}"


def _invite_matches(email: str) -> Any:
    return func.lower(ProjectInvite.email) == email.strip().lower()


def _pending() -> Any:
    return and_(ProjectInvite.accepted_at.is_(None), ProjectInvite.expires_at > _now())


@dataclass(frozen=True, slots=True)
class NewInvite:
    invite: InviteOut
    link: str
    emailed: bool


class MemberService:
    def __init__(self, db: AsyncSession, settings: Settings, mailer: Mailer) -> None:
        self._db = db
        self._settings = settings
        self._mailer = mailer

    # --- Members -----------------------------------------------------------------------

    async def list_members(
        self, access: ProjectAccess, cursor: str | None, limit: int
    ) -> MemberPage:
        """Members in the order they joined, so the owner comes first."""
        query = (
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == access.project_id)
            .order_by(ProjectMember.joined_at, ProjectMember.user_id)
            .limit(limit + 1)
        )
        if cursor is not None:
            joined, user_id = decode_cursor(cursor, 2)
            try:
                key = (datetime.fromisoformat(joined), uuid.UUID(user_id))
            except ValueError:
                raise InvalidCursorError from None
            query = query.where(tuple_(ProjectMember.joined_at, ProjectMember.user_id) > key)
        rows = list((await self._db.execute(query)).tuples().all())
        show_email = access.can(Capability.MANAGE_MEMBERS)
        items = [self._member_out(member, user, show_email) for member, user in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1][0]
            next_cursor = encode_cursor(last.joined_at.isoformat(), str(last.user_id))
        return MemberPage(items=items, next_cursor=next_cursor)

    @staticmethod
    def _member_out(member: ProjectMember, user: User, show_email: bool) -> MemberOut:
        return MemberOut(
            user=PersonOut(id=user.id, name=user.name, email=user.email if show_email else None),
            role=member.role,
            can_resolve_conflicts=member.can_resolve_conflicts,
            stages=[ScreeningStage(stage) for stage in member.stages],
            joined_at=member.joined_at,
        )

    async def _member(
        self, access: ProjectAccess, user_id: uuid.UUID
    ) -> tuple[ProjectMember, User]:
        row = (
            await self._db.execute(
                select(ProjectMember, User)
                .join(User, User.id == ProjectMember.user_id)
                .where(
                    ProjectMember.project_id == access.project_id,
                    ProjectMember.user_id == user_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("That person is not a member of this review.")
        member, user = row
        return member, user

    async def update(
        self, access: ProjectAccess, user_id: uuid.UUID, body: MemberUpdate, actor: Actor
    ) -> MemberOut:
        member, user = await self._member(access, user_id)
        if member.role == ProjectRole.OWNER:
            raise OwnerProtectedError
        new_role = ProjectRole(body.role) if body.role is not None else None
        if user_id == access.user.id and new_role is not None and new_role != member.role:
            raise ConflictError("You cannot change your own role. Ask the owner or another admin.")
        before: dict[str, Any] = {}
        after: dict[str, Any] = {}
        changes: dict[str, Any] = {
            "role": new_role,
            "can_resolve_conflicts": body.can_resolve_conflicts,
            "stages": [stage.value for stage in body.stages] if body.stages is not None else None,
        }
        for field, value in changes.items():
            if value is not None and getattr(member, field) != value:
                before[field], after[field] = getattr(member, field), value
                setattr(member, field, value)
        if before:
            audit.record(
                self._db,
                "member.role_changed" if "role" in before else "member.updated",
                actor,
                user_id=access.user.id,
                project_id=access.project_id,
                entity_type="user",
                entity_id=user_id,
                before=before,
                after=after,
            )
        await self._db.commit()
        return self._member_out(member, user, show_email=True)

    async def remove(self, access: ProjectAccess, user_id: uuid.UUID, actor: Actor) -> None:
        member, _ = await self._member(access, user_id)
        if member.role == ProjectRole.OWNER:
            raise OwnerProtectedError("The owner cannot be removed. Transfer ownership first.")
        await self._db.delete(member)
        audit.record(
            self._db,
            "member.left" if user_id == access.user.id else "member.removed",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="user",
            entity_id=user_id,
            before={"role": member.role.value},
        )
        await self._db.commit()

    async def leave(self, access: ProjectAccess, actor: Actor) -> None:
        if access.role == ProjectRole.OWNER:
            raise OwnerProtectedError("Transfer ownership to another member before you leave.")
        await self.remove(access, access.user.id, actor)

    async def update_membership(
        self, access: ProjectAccess, body: MembershipUpdate, actor: Actor
    ) -> MembershipOut:
        """The caller's own preferences in this review."""
        member = access.member
        if member.keep_blind != body.keep_blind:
            audit.record(
                self._db,
                "member.keep_blind_changed",
                actor,
                user_id=access.user.id,
                project_id=access.project_id,
                entity_type="user",
                entity_id=access.user.id,
                before={"keep_blind": member.keep_blind},
                after={"keep_blind": body.keep_blind},
            )
            member.keep_blind = body.keep_blind
        await self._db.commit()
        return MembershipOut(
            role=member.role,
            can_resolve_conflicts=member.can_resolve_conflicts,
            stages=[ScreeningStage(stage) for stage in member.stages],
            keep_blind=member.keep_blind,
        )

    # --- Invitations -------------------------------------------------------------------

    async def list_invites(self, access: ProjectAccess) -> list[InviteOut]:
        inviter = aliased(User)
        rows = await self._db.execute(
            select(ProjectInvite, inviter.name)
            .outerjoin(inviter, inviter.id == ProjectInvite.invited_by)
            .where(
                ProjectInvite.project_id == access.project_id, ProjectInvite.accepted_at.is_(None)
            )
            .order_by(ProjectInvite.id.desc())
        )
        return [self._invite_out(invite, name) for invite, name in rows.tuples()]

    @staticmethod
    def _invite_out(invite: ProjectInvite, inviter_name: str | None) -> InviteOut:
        return InviteOut(
            id=invite.id,
            email=invite.email,
            role=invite.role,
            invited_by=inviter_name,
            created_at=invite.created_at,
            expires_at=invite.expires_at,
            expired=invite.expires_at <= _now(),
        )

    async def invite(self, access: ProjectAccess, body: InviteCreate, actor: Actor) -> NewInvite:
        if self._settings.winnow_single_user:
            raise InvitesUnavailableError
        email = str(body.email).strip()
        is_member = await self._db.scalar(
            select(func.count())
            .select_from(ProjectMember)
            .join(User, User.id == ProjectMember.user_id)
            .where(
                ProjectMember.project_id == access.project_id,
                func.lower(User.email) == email.lower(),
            )
        )
        if is_member:
            raise AlreadyMemberError
        # Inviting the same address again replaces its open invitation.
        await self._db.execute(
            delete(ProjectInvite).where(
                ProjectInvite.project_id == access.project_id,
                ProjectInvite.accepted_at.is_(None),
                _invite_matches(email),
            )
        )
        open_invites = await self._db.scalar(
            select(func.count())
            .select_from(ProjectInvite)
            .where(ProjectInvite.project_id == access.project_id, _pending())
        )
        if (open_invites or 0) >= MAX_PENDING_INVITES:
            raise LimitReachedError(
                f"This review has {MAX_PENDING_INVITES} open invitations. Withdraw some first."
            )
        token = new_token()
        invite = ProjectInvite(
            project_id=access.project_id,
            email=email,
            role=ProjectRole(body.role),
            token_hash=hash_token(token),
            invited_by=access.user.id,
            expires_at=_now() + INVITE_TTL,
        )
        self._db.add(invite)
        await self._db.flush()
        audit.record(
            self._db,
            "member.invited",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="invite",
            entity_id=invite.id,
            after={"email": email, "role": invite.role.value},
        )
        invitee = await self._db.scalar(
            select(User.id).where(
                func.lower(User.email) == email.lower(), User.deleted_at.is_(None)
            )
        )
        if invitee is not None:
            # Not tied to the review: the invitee cannot open it until they accept.
            await notify(
                self._db,
                [invitee],
                NotificationKind.INVITE,
                data={
                    "project_title": access.project.title,
                    "by": access.user.name,
                    "role": ROLE_NAMES[invite.role],
                },
            )
        await self._db.commit()
        await self._db.refresh(invite)
        link = f"{self._settings.public_origin}/invite/{token}"
        await self._mailer.send(
            messages.project_invite(
                email,
                inviter=access.user.name,
                project_title=access.project.title,
                role=ROLE_NAMES[invite.role],
                link=link,
                days=INVITE_TTL.days,
            )
        )
        return NewInvite(
            invite=self._invite_out(invite, access.user.name),
            link=link,
            emailed=self._settings.email_enabled,
        )

    async def revoke_invite(
        self, access: ProjectAccess, invite_id: uuid.UUID, actor: Actor
    ) -> None:
        revoked = await self._db.scalar(
            delete(ProjectInvite)
            .where(
                ProjectInvite.id == invite_id,
                ProjectInvite.project_id == access.project_id,
                ProjectInvite.accepted_at.is_(None),
            )
            .returning(ProjectInvite.email)
        )
        if revoked is None:
            raise NotFoundError("That invitation was already accepted or withdrawn.")
        audit.record(
            self._db,
            "member.invite_revoked",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="invite",
            entity_id=invite_id,
            before={"email": revoked},
        )
        await self._db.commit()

    async def _invite_by_token(self, token: str) -> tuple[ProjectInvite, Project]:
        row = (
            await self._db.execute(
                select(ProjectInvite, Project)
                .join(Project, Project.id == ProjectInvite.project_id)
                .where(ProjectInvite.token_hash == hash_token(token), Project.deleted_at.is_(None))
            )
        ).one_or_none()
        if row is None:
            raise InvalidTokenError(
                "This invitation link is not valid. It may have been withdrawn."
            )
        invite, project = row
        return invite, project

    async def preview_invite(self, token: str) -> InvitePreview:
        """What the invitation page shows before anyone signs in."""
        invite, project = await self._invite_by_token(token)
        inviter = await self._db.get(User, invite.invited_by) if invite.invited_by else None
        state: Any = (
            "accepted"
            if invite.accepted_at is not None
            else "expired"
            if invite.expires_at <= _now()
            else "pending"
        )
        return InvitePreview(
            project_title=project.title,
            inviter_name=inviter.name if inviter else None,
            role=invite.role,
            email_hint=mask_email(invite.email),
            expires_at=invite.expires_at,
            state=state,
        )

    async def accept_invite(self, user: User, token: str, actor: Actor) -> uuid.UUID:
        """Join the project; returns its id. Accepting again as a member is harmless."""
        invite, project = await self._invite_by_token(token)
        if invite.email.lower() != user.email.lower():
            raise InviteEmailMismatchError(
                f"This invitation is for {mask_email(invite.email)}. Sign in with that address "
                "to accept it."
            )
        if not user.email_verified:
            raise EmailUnverifiedError
        already = await self._db.get(ProjectMember, (project.id, user.id))
        if already is not None:
            return project.id
        claimed = await self._db.scalar(
            update(ProjectInvite)
            .where(ProjectInvite.id == invite.id, _pending())
            .values(accepted_at=_now(), accepted_by=user.id)
            .returning(ProjectInvite.id)
        )
        if claimed is None:
            raise InvalidTokenError(
                "This invitation has expired or was already used. Ask for a new one."
            )
        self._db.add(ProjectMember(project_id=project.id, user_id=user.id, role=invite.role))
        audit.record(
            self._db,
            "member.joined",
            actor,
            user_id=user.id,
            project_id=project.id,
            entity_type="invite",
            entity_id=invite.id,
            after={"role": invite.role.value},
        )
        await self._db.commit()
        return project.id


async def invite_allows_registration(db: AsyncSession, token: str | None, email: str) -> bool:
    """For invite-only instances: an open invitation for this address lets it register."""
    if not token:
        return False
    found = await db.scalar(
        select(ProjectInvite.id)
        .join(Project, Project.id == ProjectInvite.project_id)
        .where(
            ProjectInvite.token_hash == hash_token(token),
            _invite_matches(email),
            _pending(),
            Project.deleted_at.is_(None),
        )
    )
    return found is not None

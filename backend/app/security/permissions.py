"""Project roles and what each may do (guide 7), and the membership check behind every
project route.

The table lives here once. Routes enforce it through `require_project_role` (in
app.api.deps); the project response reports it to the frontend, which only hides controls.
"""

import enum
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, ProjectMember, ProjectRole, User
from app.services.errors import ForbiddenError, NotFoundError

RANK: dict[ProjectRole, int] = {
    ProjectRole.VIEWER: 0,
    ProjectRole.REVIEWER: 1,
    ProjectRole.ADMIN: 2,
    ProjectRole.OWNER: 3,
}

# A per-member flag that grants an action to a reviewer who is below its minimum role.
MemberFlag = Literal["can_resolve_conflicts"]


class Capability(enum.StrEnum):
    VIEW = "view"
    SCREEN = "screen"
    SEE_OTHERS_WHILE_BLIND = "see_others_while_blind"
    RESOLVE_CONFLICTS = "resolve_conflicts"
    IMPORT = "import"  # import records, run deduplication
    EDIT_SETUP = "edit_setup"  # criteria, keywords, reasons, labels, forms
    MANAGE_MEMBERS = "manage_members"  # invite, remove, change roles (never the owner's)
    EDIT_SETTINGS = "edit_settings"  # blind mode and the other project settings
    EXPORT = "export"
    DELETE_PROJECT = "delete_project"  # delete or transfer


@dataclass(frozen=True, slots=True)
class Rule:
    min_role: ProjectRole
    flag: MemberFlag | None = None


# Guide 7, row by row.
RULES: dict[Capability, Rule] = {
    Capability.VIEW: Rule(ProjectRole.VIEWER),
    Capability.SCREEN: Rule(ProjectRole.REVIEWER),
    Capability.SEE_OTHERS_WHILE_BLIND: Rule(ProjectRole.ADMIN),
    Capability.RESOLVE_CONFLICTS: Rule(ProjectRole.ADMIN, flag="can_resolve_conflicts"),
    Capability.IMPORT: Rule(ProjectRole.ADMIN),
    Capability.EDIT_SETUP: Rule(ProjectRole.ADMIN),
    Capability.MANAGE_MEMBERS: Rule(ProjectRole.ADMIN),
    Capability.EDIT_SETTINGS: Rule(ProjectRole.ADMIN),
    Capability.EXPORT: Rule(ProjectRole.VIEWER),
    Capability.DELETE_PROJECT: Rule(ProjectRole.OWNER),
}


def allows(member: ProjectMember, min_role: ProjectRole, flag: MemberFlag | None = None) -> bool:
    """Whether this member may act at `min_role`. A flag lets a reviewer (never a viewer)
    in below the minimum, e.g. a reviewer trusted to resolve conflicts."""
    if RANK[member.role] >= RANK[min_role]:
        return True
    return (
        flag is not None
        and bool(getattr(member, flag))
        and RANK[member.role] >= RANK[ProjectRole.REVIEWER]
    )


def can(member: ProjectMember, capability: Capability) -> bool:
    rule = RULES[capability]
    return allows(member, rule.min_role, rule.flag)


@dataclass(frozen=True, slots=True)
class ProjectAccess:
    """A verified membership. Services take this, and scope every query by `project_id`."""

    user: User
    project: Project
    member: ProjectMember

    @property
    def project_id(self) -> uuid.UUID:
        return self.project.id

    @property
    def role(self) -> ProjectRole:
        return self.member.role

    def can(self, capability: Capability) -> bool:
        return can(self.member, capability)


def parse_project_id(raw: str) -> uuid.UUID:
    """The id from the URL. A malformed id is just another project you cannot see."""
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise NotFoundError from None


async def check_project_role(
    db: AsyncSession,
    user: User,
    project_id: uuid.UUID,
    min_role: ProjectRole,
    *,
    flag: MemberFlag | None = None,
) -> ProjectAccess:
    """Load the project through the caller's membership, in one query.

    Not a member, or the project is deleted or does not exist: 404, the same answer in
    every case, so outsiders cannot learn which projects exist. A member without the
    role gets 403: they already know the project is there.
    """
    row = (
        await db.execute(
            select(Project, ProjectMember)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(
                Project.id == project_id,
                Project.deleted_at.is_(None),
                ProjectMember.user_id == user.id,
            )
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError
    project, member = row
    if not allows(member, min_role, flag):
        raise ForbiddenError
    return ProjectAccess(user=user, project=project, member=member)

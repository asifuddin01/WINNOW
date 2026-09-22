"""Projects, members and invitations: /api/v1/projects (guide 10).

Every /projects/{pid} route depends on require_project_role (guide 7), through the
Viewer/Admin/OwnerAccess aliases, and passes the verified access to the service.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import (
    ActorDep,
    AdminAccess,
    AuthDep,
    LimiterDep,
    MembersDep,
    OwnerAccess,
    ProjectsDep,
    ViewerAccess,
    enforce_limit,
)
from app.api.responses import CONFLICT, PROJECT, RATE_LIMITED, UNAUTHORIZED
from app.schemas.problem import problem_content
from app.schemas.projects import (
    DuplicateSetupRequest,
    InviteCreate,
    InviteCreated,
    InviteOut,
    MemberOut,
    MemberPage,
    MembershipOut,
    MembershipUpdate,
    MemberUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectPage,
    ProjectUpdate,
    TransferRequest,
)
from app.security import rate_limit as limits
from app.services.pagination import DEFAULT_LIMIT, MAX_LIMIT

router = APIRouter(prefix="/projects", tags=["projects"])

Cursor = Annotated[str | None, Query(max_length=512, description="From the previous page")]
Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]


# --- Projects ----------------------------------------------------------------------------


@router.get("", responses={**UNAUTHORIZED, 400: problem_content()})
async def list_projects(
    auth: AuthDep, projects: ProjectsDep, cursor: Cursor = None, limit: Limit = DEFAULT_LIMIT
) -> ProjectPage:
    """The reviews you are a member of, newest first."""
    return await projects.list_for_user(auth.user, cursor, limit)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={**UNAUTHORIZED, 403: problem_content(), **RATE_LIMITED},
)
async def create_project(
    body: ProjectCreate,
    auth: AuthDep,
    projects: ProjectsDep,
    limiter: LimiterDep,
    actor: ActorDep,
) -> ProjectOut:
    """Start a review. You become its owner; the standard exclusion reasons are added."""
    await enforce_limit(limiter, limits.PROJECT_CREATE_PER_USER, str(auth.user.id))
    return await projects.create(auth.user, body, actor)


@router.get("/{pid}", responses=PROJECT)
async def get_project(access: ViewerAccess, projects: ProjectsDep) -> ProjectOut:
    return await projects.detail(access)


@router.patch("/{pid}", responses={**PROJECT, **CONFLICT})
async def update_project(
    body: ProjectUpdate, access: AdminAccess, projects: ProjectsDep, actor: ActorDep
) -> ProjectOut:
    """Change the basics, status or settings. Send only what changes."""
    await projects.update(access, body, actor)
    return await projects.detail(access)


@router.delete("/{pid}", status_code=status.HTTP_204_NO_CONTENT, responses=PROJECT)
async def delete_project(access: OwnerAccess, projects: ProjectsDep, actor: ActorDep) -> None:
    """Delete the review for everyone. Owner only."""
    await projects.delete(access, actor)


@router.post("/{pid}/transfer", responses={**PROJECT, **CONFLICT})
async def transfer_project(
    body: TransferRequest, access: OwnerAccess, projects: ProjectsDep, actor: ActorDep
) -> ProjectOut:
    """Make another member the owner. You stay on as an admin."""
    await projects.transfer(access, body.user_id, actor)
    return await projects.detail(access)


@router.post(
    "/{pid}/duplicate-setup",
    status_code=status.HTTP_201_CREATED,
    responses={**PROJECT, **RATE_LIMITED},
)
async def duplicate_setup(
    body: DuplicateSetupRequest,
    access: ViewerAccess,
    projects: ProjectsDep,
    limiter: LimiterDep,
    actor: ActorDep,
) -> ProjectOut:
    """A new review of your own with this one's settings, criteria, keywords, reasons and
    labels. Nothing else is copied."""
    await enforce_limit(limiter, limits.PROJECT_CREATE_PER_USER, str(access.user.id))
    return await projects.duplicate_setup(access, body.title, actor)


# --- Members -----------------------------------------------------------------------------


@router.get("/{pid}/members", responses={**PROJECT, 400: problem_content()})
async def list_members(
    access: ViewerAccess, members: MembersDep, cursor: Cursor = None, limit: Limit = DEFAULT_LIMIT
) -> MemberPage:
    """Everyone in the review, in the order they joined. Emails only for those who manage
    members."""
    return await members.list_members(access, cursor, limit)


@router.patch("/{pid}/members/{uid}", responses={**PROJECT, **CONFLICT})
async def update_member(
    uid: uuid.UUID, body: MemberUpdate, access: AdminAccess, members: MembersDep, actor: ActorDep
) -> MemberOut:
    """Change a member's role, stages or conflict-resolving. Never the owner's."""
    return await members.update(access, uid, body, actor)


@router.delete(
    "/{pid}/members/{uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**PROJECT, **CONFLICT},
)
async def remove_member(
    uid: uuid.UUID, access: AdminAccess, members: MembersDep, actor: ActorDep
) -> None:
    """Remove someone from the review. Their past work stays; the owner cannot be removed."""
    await members.remove(access, uid, actor)


@router.patch("/{pid}/membership", responses=PROJECT)
async def update_my_membership(
    body: MembershipUpdate, access: ViewerAccess, members: MembersDep, actor: ActorDep
) -> MembershipOut:
    """Your own preferences in this review."""
    return await members.update_membership(access, body, actor)


@router.delete(
    "/{pid}/membership", status_code=status.HTTP_204_NO_CONTENT, responses={**PROJECT, **CONFLICT}
)
async def leave_project(access: ViewerAccess, members: MembersDep, actor: ActorDep) -> None:
    """Leave the review. The owner must transfer ownership first."""
    await members.leave(access, actor)


# --- Invitations -------------------------------------------------------------------------


@router.get("/{pid}/invites", responses=PROJECT)
async def list_invites(access: AdminAccess, members: MembersDep) -> list[InviteOut]:
    """Invitations not yet accepted, newest first."""
    return await members.list_invites(access)


@router.post(
    "/{pid}/invites",
    status_code=status.HTTP_201_CREATED,
    responses={**PROJECT, **CONFLICT, **RATE_LIMITED},
)
async def invite_member(
    body: InviteCreate,
    access: AdminAccess,
    members: MembersDep,
    limiter: LimiterDep,
    actor: ActorDep,
) -> InviteCreated:
    """Invite someone by email. Inviting the same address again replaces the old link."""
    await enforce_limit(limiter, limits.INVITES_PER_USER, str(access.user.id))
    created = await members.invite(access, body, actor)
    return InviteCreated(**created.invite.model_dump(), link=created.link, emailed=created.emailed)


@router.delete("/{pid}/invites/{iid}", status_code=status.HTTP_204_NO_CONTENT, responses=PROJECT)
async def revoke_invite(
    iid: uuid.UUID, access: AdminAccess, members: MembersDep, actor: ActorDep
) -> None:
    """Withdraw an invitation; its link stops working."""
    await members.revoke_invite(access, iid, actor)

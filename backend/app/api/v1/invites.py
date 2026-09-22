"""Invitation links: /api/v1/invites/{token} (guide 10).

The token is the secret, so the preview is public; accepting is not. An invitation only
ever works for someone signed in with the invited, confirmed address.
"""

from typing import Annotated

from fastapi import APIRouter, Path

from app.api.deps import ActorDep, AuthDep, LimiterDep, MembersDep, enforce_limit
from app.api.responses import RATE_LIMITED, UNAUTHORIZED
from app.schemas.problem import problem_content
from app.schemas.projects import InviteAccepted, InvitePreview
from app.security import rate_limit as limits

router = APIRouter(prefix="/invites", tags=["projects"])

Token = Annotated[str, Path(min_length=16, max_length=128)]


@router.get("/{token}", responses={400: problem_content(), **RATE_LIMITED})
async def preview_invite(
    token: Token, members: MembersDep, limiter: LimiterDep, actor: ActorDep
) -> InvitePreview:
    """What the invitation is for, before signing in. The address is shown masked."""
    await enforce_limit(limiter, limits.INVITE_LINK_PER_IP, actor.ip or "unknown")
    return await members.preview_invite(token)


@router.post(
    "/{token}/accept",
    responses={**UNAUTHORIZED, 400: problem_content(), 403: problem_content(), **RATE_LIMITED},
)
async def accept_invite(
    token: Token, auth: AuthDep, members: MembersDep, limiter: LimiterDep, actor: ActorDep
) -> InviteAccepted:
    """Join the review. Your confirmed email must be the invited one."""
    await enforce_limit(limiter, limits.INVITE_LINK_PER_IP, actor.ip or "unknown")
    return InviteAccepted(project_id=await members.accept_invite(auth.user, token, actor))

"""Who is screening right now (guide 8.17)."""

from fastapi import APIRouter, status

from app.api.deps import ReviewerAccess, ViewerAccess
from app.api.responses import PROJECT
from app.redis_client import RedisDep
from app.schemas.presence import PresenceIn, PresentMember
from app.services import presence

router = APIRouter(prefix="/projects/{pid}/presence", tags=["presence"])


@router.get("", responses=PROJECT)
async def who_is_screening(access: ViewerAccess, redis: RedisDep) -> list[PresentMember]:
    """Other members screening in the last minute, and which stage; never which record."""
    return await presence.present(redis, access)


@router.put("", status_code=status.HTTP_204_NO_CONTENT, responses=PROJECT)
async def i_am_screening(body: PresenceIn, access: ReviewerAccess, redis: RedisDep) -> None:
    """Sent by a screening page every 30 seconds while it is open."""
    await presence.here(redis, access, body.stage)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, responses=PROJECT)
async def i_have_stopped(access: ReviewerAccess, redis: RedisDep) -> None:
    await presence.gone(redis, access)

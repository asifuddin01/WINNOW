"""My notifications (guide 8.17): what happened that needs me, across my reviews."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AuthDep, NotificationsDep
from app.api.responses import UNAUTHORIZED
from app.schemas.notifications import NotificationPage, NotificationSettings, UnreadCount
from app.schemas.problem import problem_content

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", responses=UNAUTHORIZED)
async def my_notifications(
    auth: AuthDep,
    notifications: NotificationsDep,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NotificationPage:
    """Newest activity first, from reviews I still belong to."""
    return await notifications.page(auth.user, cursor, limit)


@router.get("/unread", responses=UNAUTHORIZED)
async def unread_notifications(auth: AuthDep, notifications: NotificationsDep) -> UnreadCount:
    return UnreadCount(unread=await notifications.unread(auth.user))


@router.post(
    "/{nid}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**UNAUTHORIZED, 404: problem_content()},
)
async def read_notification(nid: uuid.UUID, auth: AuthDep, notifications: NotificationsDep) -> None:
    await notifications.mark_read(auth.user, nid)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT, responses=UNAUTHORIZED)
async def read_all_notifications(auth: AuthDep, notifications: NotificationsDep) -> None:
    await notifications.mark_all_read(auth.user)


@router.get("/settings", responses=UNAUTHORIZED)
async def notification_settings(
    auth: AuthDep, notifications: NotificationsDep
) -> NotificationSettings:
    return notifications.settings(auth.user)


@router.put("/settings", responses=UNAUTHORIZED)
async def update_notification_settings(
    body: NotificationSettings, auth: AuthDep, notifications: NotificationsDep
) -> NotificationSettings:
    """A daily email of what is unread, off by default."""
    return await notifications.update_settings(auth.user, body)

"""The instance administrator's panel (guide 8.18). Anyone else gets 404."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ActorDep, AdminDep, InstanceAdminDep
from app.api.responses import CONFLICT, UNAUTHORIZED, Responses
from app.schemas.admin import (
    AdminUserOut,
    AdminUserPage,
    HealthOut,
    InstanceSettingsOut,
    InstanceSettingsPatch,
)
from app.schemas.problem import problem_content

router = APIRouter(prefix="/admin", tags=["admin"])

HIDDEN: Responses = {**UNAUTHORIZED, 404: problem_content()}


@router.get("/users", responses=HIDDEN)
async def admin_users(
    admin: InstanceAdminDep,
    service: AdminDep,
    q: Annotated[str, Query(max_length=200)] = "",
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AdminUserPage:
    """Everyone with an account, newest first, searchable by name or email."""
    return await service.users(q, cursor, limit)


@router.post("/users/{uid}/disable", responses={**HIDDEN, **CONFLICT})
async def disable_user(
    uid: uuid.UUID, admin: InstanceAdminDep, service: AdminDep, actor: ActorDep
) -> AdminUserOut:
    """The account cannot sign in until enabled again, and its sessions end now. Its reviews
    and work are untouched."""
    return await service.disable(admin, uid, actor)


@router.post("/users/{uid}/enable", responses=HIDDEN)
async def enable_user(
    uid: uuid.UUID, admin: InstanceAdminDep, service: AdminDep, actor: ActorDep
) -> AdminUserOut:
    return await service.enable(admin, uid, actor)


@router.post("/users/{uid}/reset-2fa", responses={**HIDDEN, **CONFLICT})
async def reset_two_factor(
    uid: uuid.UUID, admin: InstanceAdminDep, service: AdminDep, actor: ActorDep
) -> AdminUserOut:
    """For someone who lost their authenticator and recovery codes: they sign in with their
    password alone and set it up again. They are emailed."""
    return await service.reset_two_factor(admin, uid, actor)


@router.post("/users/{uid}/sign-out", responses=HIDDEN)
async def sign_out_user(
    uid: uuid.UUID, admin: InstanceAdminDep, service: AdminDep, actor: ActorDep
) -> dict[str, int]:
    """End every session of the account, on every device."""
    return {"ended": await service.sign_out(admin, uid, actor)}


@router.get("/settings", responses=HIDDEN)
async def admin_settings(admin: InstanceAdminDep, service: AdminDep) -> InstanceSettingsOut:
    """The instance's settings; secrets are never shown, only whether they are set."""
    return await service.instance_settings()


@router.patch("/settings", responses=HIDDEN)
async def update_admin_settings(
    body: InstanceSettingsPatch, admin: InstanceAdminDep, service: AdminDep, actor: ActorDep
) -> InstanceSettingsOut:
    """Change the registration mode or the Unpaywall email while Winnow runs."""
    return await service.update_settings(admin, body, actor)


@router.get("/health", responses=HIDDEN)
async def admin_health(admin: InstanceAdminDep, service: AdminDep) -> HealthOut:
    """Queue, worker, disk, database and the last backup."""
    return await service.health()

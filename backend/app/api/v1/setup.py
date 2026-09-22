"""A review's setup: criteria, keyword groups and keywords, exclusion reasons and labels.

Members read it; admins and owners change it (guide 7). Every id is looked up inside the
verified project, so ids from another review are not found.
"""

import uuid

from fastapi import APIRouter, status

from app.api.deps import ActorDep, AdminAccess, SetupDep, ViewerAccess
from app.api.responses import CONFLICT, PROJECT
from app.schemas.setup import (
    CriterionCreate,
    CriterionOut,
    CriterionUpdate,
    KeywordGroupCreate,
    KeywordGroupOut,
    KeywordGroupUpdate,
    KeywordOut,
    KeywordsCreate,
    KeywordUpdate,
    LabelCreate,
    LabelOut,
    LabelUpdate,
    ReasonCreate,
    ReasonOut,
    ReasonUpdate,
)

router = APIRouter(prefix="/projects/{pid}", tags=["setup"])
CREATED = status.HTTP_201_CREATED
NO_CONTENT = status.HTTP_204_NO_CONTENT


# --- Criteria ----------------------------------------------------------------------------


@router.get("/criteria", responses=PROJECT)
async def list_criteria(access: ViewerAccess, setup: SetupDep) -> list[CriterionOut]:
    """Inclusion criteria first, each list in its own order."""
    return [
        CriterionOut.model_validate(row, from_attributes=True)
        for row in await setup.criteria(access)
    ]


@router.post("/criteria", status_code=CREATED, responses={**PROJECT, **CONFLICT})
async def add_criterion(
    body: CriterionCreate, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> CriterionOut:
    return CriterionOut.model_validate(
        await setup.add_criterion(access, body, actor), from_attributes=True
    )


@router.patch("/criteria/{cid}", responses={**PROJECT, **CONFLICT})
async def update_criterion(
    cid: uuid.UUID, body: CriterionUpdate, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> CriterionOut:
    """Edit the text, move it between inclusion and exclusion, or reorder it."""
    return CriterionOut.model_validate(
        await setup.update_criterion(access, cid, body, actor), from_attributes=True
    )


@router.delete("/criteria/{cid}", status_code=NO_CONTENT, responses=PROJECT)
async def delete_criterion(
    cid: uuid.UUID, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> None:
    await setup.delete_criterion(access, cid, actor)


# --- Keyword groups and keywords ---------------------------------------------------------


@router.get("/keyword-groups", responses=PROJECT)
async def list_keyword_groups(access: ViewerAccess, setup: SetupDep) -> list[KeywordGroupOut]:
    """Each group with its keywords."""
    return await setup.keyword_groups(access)


@router.post("/keyword-groups", status_code=CREATED, responses={**PROJECT, **CONFLICT})
async def add_keyword_group(
    body: KeywordGroupCreate, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> KeywordGroupOut:
    group = await setup.add_keyword_group(access, body, actor)
    return await setup.keyword_group(access, group.id)


@router.patch("/keyword-groups/{gid}", responses={**PROJECT, **CONFLICT})
async def update_keyword_group(
    gid: uuid.UUID, body: KeywordGroupUpdate, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> KeywordGroupOut:
    await setup.update_keyword_group(access, gid, body, actor)
    return await setup.keyword_group(access, gid)


@router.delete("/keyword-groups/{gid}", status_code=NO_CONTENT, responses=PROJECT)
async def delete_keyword_group(
    gid: uuid.UUID, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> None:
    """Deletes the group and its keywords."""
    await setup.delete_keyword_group(access, gid, actor)


@router.post("/keywords", status_code=CREATED, responses={**PROJECT, **CONFLICT})
async def add_keywords(
    body: KeywordsCreate, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> KeywordGroupOut:
    """Add terms to a group; ones it already has are skipped. Patterns are checked."""
    await setup.add_keywords(access, body, actor)
    return await setup.keyword_group(access, body.group_id)


@router.patch("/keywords/{kid}", responses={**PROJECT, **CONFLICT})
async def update_keyword(
    kid: uuid.UUID, body: KeywordUpdate, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> KeywordOut:
    return KeywordOut.model_validate(
        await setup.update_keyword(access, kid, body, actor), from_attributes=True
    )


@router.delete("/keywords/{kid}", status_code=NO_CONTENT, responses=PROJECT)
async def delete_keyword(
    kid: uuid.UUID, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> None:
    await setup.delete_keyword(access, kid, actor)


# --- Exclusion reasons -------------------------------------------------------------------


@router.get("/exclusion-reasons", responses=PROJECT)
async def list_exclusion_reasons(access: ViewerAccess, setup: SetupDep) -> list[ReasonOut]:
    """The reasons offered when excluding a record, in the order they are shown."""
    return [
        ReasonOut.model_validate(row, from_attributes=True) for row in await setup.reasons(access)
    ]


@router.post("/exclusion-reasons", status_code=CREATED, responses={**PROJECT, **CONFLICT})
async def add_exclusion_reason(
    body: ReasonCreate, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> ReasonOut:
    return ReasonOut.model_validate(
        await setup.add_reason(access, body, actor), from_attributes=True
    )


@router.patch("/exclusion-reasons/{rid}", responses={**PROJECT, **CONFLICT})
async def update_exclusion_reason(
    rid: uuid.UUID, body: ReasonUpdate, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> ReasonOut:
    return ReasonOut.model_validate(
        await setup.update_reason(access, rid, body, actor), from_attributes=True
    )


@router.delete("/exclusion-reasons/{rid}", status_code=NO_CONTENT, responses=PROJECT)
async def delete_exclusion_reason(
    rid: uuid.UUID, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> None:
    await setup.delete_reason(access, rid, actor)


# --- Labels ------------------------------------------------------------------------------


@router.get("/labels", responses=PROJECT)
async def list_labels(access: ViewerAccess, setup: SetupDep) -> list[LabelOut]:
    return [
        LabelOut.model_validate(row, from_attributes=True) for row in await setup.labels(access)
    ]


@router.post("/labels", status_code=CREATED, responses={**PROJECT, **CONFLICT})
async def add_label(
    body: LabelCreate, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> LabelOut:
    return LabelOut.model_validate(await setup.add_label(access, body, actor), from_attributes=True)


@router.patch("/labels/{lid}", responses={**PROJECT, **CONFLICT})
async def update_label(
    lid: uuid.UUID, body: LabelUpdate, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> LabelOut:
    return LabelOut.model_validate(
        await setup.update_label(access, lid, body, actor), from_attributes=True
    )


@router.delete("/labels/{lid}", status_code=NO_CONTENT, responses=PROJECT)
async def delete_label(
    lid: uuid.UUID, access: AdminAccess, setup: SetupDep, actor: ActorDep
) -> None:
    await setup.delete_label(access, lid, actor)

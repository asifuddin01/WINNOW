"""Data extraction (guide 8.12, 10): forms, entries, consensus.

Owners and admins build and publish forms; reviewers extract, each on their own and
blinded like screening; those who resolve conflicts reconcile two extractions into one.
"""

import uuid

from fastapi import APIRouter, status

from app.api.deps import (
    ActorDep,
    AdminAccess,
    ExtractionDep,
    ResolverAccess,
    ReviewerAccess,
    ViewerAccess,
)
from app.api.responses import CONFLICT, PROJECT, Responses
from app.schemas.extraction import (
    ConsensusIn,
    ConsensusOut,
    ConsensusView,
    EntryIn,
    EntryOut,
    FormIn,
    FormOut,
    FormPatch,
    RecordExtraction,
    StudyExtraction,
)
from app.schemas.problem import problem_content

router = APIRouter(prefix="/projects/{pid}/extraction-forms", tags=["extraction"])

INVALID: Responses = {422: problem_content()}


@router.get("", responses=PROJECT)
async def extraction_forms(access: ViewerAccess, extraction: ExtractionDep) -> list[FormOut]:
    """Every version of every form, oldest first."""
    return await extraction.forms(access)


@router.post("", status_code=status.HTTP_201_CREATED, responses={**PROJECT, **INVALID})
async def create_form(
    body: FormIn, access: AdminAccess, extraction: ExtractionDep, actor: ActorDep
) -> FormOut:
    """A new form, as a draft: nobody extracts with it until it is published."""
    return await extraction.create_form(access, body, actor)


@router.patch("/{fid}", responses={**PROJECT, **CONFLICT, **INVALID})
async def update_form(
    fid: uuid.UUID, body: FormPatch, access: AdminAccess, extraction: ExtractionDep, actor: ActorDep
) -> FormOut:
    return await extraction.update_form(access, fid, body, actor)


@router.delete("/{fid}", status_code=status.HTTP_204_NO_CONTENT, responses={**PROJECT, **CONFLICT})
async def delete_form(
    fid: uuid.UUID, access: AdminAccess, extraction: ExtractionDep, actor: ActorDep
) -> None:
    """Only a draft; a published version keeps the data extracted with it."""
    await extraction.delete_form(access, fid, actor)


@router.post("/{fid}/publish", responses={**PROJECT, **CONFLICT, **INVALID})
async def publish_form(
    fid: uuid.UUID, access: AdminAccess, extraction: ExtractionDep, actor: ActorDep
) -> FormOut:
    """Publish and lock this version; changing it later starts the next version."""
    return await extraction.publish(access, fid, actor)


@router.post(
    "/{fid}/versions", status_code=status.HTTP_201_CREATED, responses={**PROJECT, **CONFLICT}
)
async def new_form_version(
    fid: uuid.UUID, access: AdminAccess, extraction: ExtractionDep, actor: ActorDep
) -> FormOut:
    return await extraction.new_version(access, fid, actor)


@router.get("/{fid}/studies", responses=PROJECT)
async def extraction_studies(
    fid: uuid.UUID, access: ViewerAccess, extraction: ExtractionDep
) -> list[StudyExtraction]:
    """The studies included at full text, and where each one's extraction stands."""
    return await extraction.studies(access, fid)


@router.get("/{fid}/entries/{rid}", responses={**PROJECT, **CONFLICT})
async def extraction_entries(
    fid: uuid.UUID, rid: uuid.UUID, access: ViewerAccess, extraction: ExtractionDep
) -> RecordExtraction:
    """This study's extraction: mine, and others' and the consensus unless blind."""
    return await extraction.record(access, fid, rid)


@router.put("/{fid}/entries/{rid}", responses={**PROJECT, **CONFLICT, **INVALID})
async def save_extraction(
    fid: uuid.UUID,
    rid: uuid.UUID,
    body: EntryIn,
    access: ReviewerAccess,
    extraction: ExtractionDep,
    actor: ActorDep,
) -> EntryOut:
    """Save my extraction of this study: a draft, or submitted when complete."""
    return await extraction.save_entry(access, fid, rid, body, actor)


@router.get("/{fid}/consensus/{rid}", responses={**PROJECT, **CONFLICT})
async def extraction_consensus(
    fid: uuid.UUID, rid: uuid.UUID, access: ResolverAccess, extraction: ExtractionDep
) -> ConsensusView:
    """The submitted extractions side by side, where they differ, and the consensus."""
    return await extraction.consensus_view(access, fid, rid)


@router.put("/{fid}/consensus/{rid}", responses={**PROJECT, **CONFLICT, **INVALID})
async def save_consensus(
    fid: uuid.UUID,
    rid: uuid.UUID,
    body: ConsensusIn,
    access: ResolverAccess,
    extraction: ExtractionDep,
    actor: ActorDep,
) -> ConsensusOut:
    return await extraction.save_consensus(access, fid, rid, body, actor)

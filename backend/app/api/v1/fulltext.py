"""Full texts (guide 8.8, 10): a record's PDF, links to read it, annotations, free copies,
"not retrievable", and ZIPs of PDFs.

Anyone in the review may read a PDF once the scanner has cleared it; anyone who screens
may add one, look for a free copy, annotate, or mark a record's full text not retrievable.
A ZIP of many PDFs is an owner's or admin's upload, like a search export.
"""

import re
import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Path, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    ActorDep,
    AdminAccess,
    AuthDep,
    FulltextDep,
    LimiterDep,
    ReviewerAccess,
    ViewerAccess,
    enforce_limit,
)
from app.api.responses import CONFLICT, PROJECT, RATE_LIMITED, UNAUTHORIZED
from app.schemas.fulltext import (
    AnnotationIn,
    AnnotationOut,
    AnnotationPatch,
    BatchApplied,
    BatchConfirm,
    BatchOut,
    FetchIn,
    FulltextOut,
    FulltextRecord,
    FulltextSummary,
    OpenAccessFinds,
    RecordFulltext,
    SignedLink,
    UnretrievableIn,
)
from app.schemas.problem import problem_content
from app.security import rate_limit as limits

router = APIRouter(prefix="/projects/{pid}", tags=["fulltext"])
files = APIRouter(tags=["fulltext"])

UPLOAD_ERRORS = {413: problem_content(), 415: problem_content(), **RATE_LIMITED}


@router.get("/fulltext/summary", responses=PROJECT)
async def summary(access: ViewerAccess, fulltext: FulltextDep) -> FulltextSummary:
    """How many records at full text have their PDF, are waiting, or cannot be found."""
    return await fulltext.summary(access)


@router.get("/fulltext/records", responses=PROJECT)
async def records(access: ViewerAccess, fulltext: FulltextDep) -> list[FulltextRecord]:
    """Every record at full text with its PDF, for finding the ones still missing."""
    return await fulltext.records(access)


@router.get("/records/{rid}/fulltext", responses=PROJECT)
async def record_fulltext(
    rid: uuid.UUID, access: ViewerAccess, fulltext: FulltextDep
) -> RecordFulltext:
    return await fulltext.for_record(access, rid)


@router.post(
    "/records/{rid}/fulltext",
    status_code=status.HTTP_201_CREATED,
    responses={**PROJECT, **UPLOAD_ERRORS},
)
async def upload(
    rid: uuid.UUID,
    access: ReviewerAccess,
    fulltext: FulltextDep,
    limiter: LimiterDep,
    actor: ActorDep,
    file: Annotated[UploadFile, File(description="The record's PDF")],
) -> FulltextOut:
    """Attach a PDF to the record, replacing the one it had. It can be opened once the
    virus scanner has cleared it, usually within seconds."""
    await enforce_limit(limiter, limits.PDF_UPLOADS_PER_USER, str(access.user.id))
    return await fulltext.upload(access, rid, file, actor)


@router.delete("/records/{rid}/fulltext", status_code=status.HTTP_204_NO_CONTENT, responses=PROJECT)
async def remove(
    rid: uuid.UUID, access: ReviewerAccess, fulltext: FulltextDep, actor: ActorDep
) -> None:
    await fulltext.remove(access, rid, actor)


@router.get("/records/{rid}/fulltext/url", responses={**PROJECT, **CONFLICT})
async def signed_url(
    rid: uuid.UUID,
    access: ViewerAccess,
    fulltext: FulltextDep,
    download: Annotated[bool, Query()] = False,
) -> SignedLink:
    """A link to the PDF that works for five minutes, for you only."""
    return await fulltext.link(access, rid, download=download)


@router.post("/records/{rid}/fulltext/find-oa", responses={**PROJECT, **RATE_LIMITED})
async def find_open_access(
    rid: uuid.UUID, access: ReviewerAccess, fulltext: FulltextDep, limiter: LimiterDep
) -> OpenAccessFinds:
    """Ask Unpaywall (by DOI) and PubMed Central (by PMCID) for a free, legal copy."""
    await enforce_limit(limiter, limits.OPEN_ACCESS_PER_USER, str(access.user.id))
    return await fulltext.find_open_access(access, rid)


@router.post(
    "/records/{rid}/fulltext/fetch-oa",
    status_code=status.HTTP_201_CREATED,
    responses={**PROJECT, **UPLOAD_ERRORS, 502: problem_content()},
)
async def fetch_open_access(
    rid: uuid.UUID,
    body: FetchIn,
    access: ReviewerAccess,
    fulltext: FulltextDep,
    limiter: LimiterDep,
    actor: ActorDep,
) -> FulltextOut:
    """Download one of the copies just found and attach it, as if it had been uploaded."""
    await enforce_limit(limiter, limits.OPEN_ACCESS_PER_USER, str(access.user.id))
    return await fulltext.fetch_open_access(access, rid, body.candidate, actor)


@router.post("/records/{rid}/fulltext/not-retrievable", responses={**PROJECT, **CONFLICT})
async def mark_not_retrievable(
    rid: uuid.UUID,
    body: UnretrievableIn,
    access: ReviewerAccess,
    fulltext: FulltextDep,
    actor: ActorDep,
) -> RecordFulltext:
    """No full text could be found: the record leaves the full-text queue and is counted
    in PRISMA's "reports not retrieved"."""
    return await fulltext.mark_unretrievable(access, rid, body.note, actor)


@router.delete("/records/{rid}/fulltext/not-retrievable", responses={**PROJECT, **CONFLICT})
async def unmark_not_retrievable(
    rid: uuid.UUID, access: ReviewerAccess, fulltext: FulltextDep, actor: ActorDep
) -> RecordFulltext:
    return await fulltext.unmark_unretrievable(access, rid, actor)


@router.get("/fulltext/{fid}/annotations", responses=PROJECT)
async def annotations(
    fid: uuid.UUID, access: ViewerAccess, fulltext: FulltextDep
) -> list[AnnotationOut]:
    """Highlights and comments on this PDF. Under blind mode, only your own."""
    return await fulltext.annotations(access, fid)


@router.post("/fulltext/{fid}/annotations", status_code=status.HTTP_201_CREATED, responses=PROJECT)
async def add_annotation(
    fid: uuid.UUID, body: AnnotationIn, access: ReviewerAccess, fulltext: FulltextDep
) -> AnnotationOut:
    return await fulltext.add_annotation(access, fid, body)


@router.patch("/fulltext/{fid}/annotations/{aid}", responses=PROJECT)
async def update_annotation(
    fid: uuid.UUID,
    aid: uuid.UUID,
    body: AnnotationPatch,
    access: ReviewerAccess,
    fulltext: FulltextDep,
) -> AnnotationOut:
    return await fulltext.update_annotation(access, fid, aid, body)


@router.delete(
    "/fulltext/{fid}/annotations/{aid}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=PROJECT,
)
async def delete_annotation(
    fid: uuid.UUID, aid: uuid.UUID, access: ReviewerAccess, fulltext: FulltextDep
) -> None:
    await fulltext.delete_annotation(access, fid, aid)


@router.post(
    "/fulltext/bulk",
    status_code=status.HTTP_201_CREATED,
    responses={**PROJECT, **UPLOAD_ERRORS, 422: problem_content()},
)
async def upload_zip(
    access: AdminAccess,
    fulltext: FulltextDep,
    limiter: LimiterDep,
    actor: ActorDep,
    file: Annotated[UploadFile, File(description="A ZIP of PDFs")],
) -> BatchOut:
    """Upload a ZIP of PDFs. It is checked before anything is unpacked (a ZIP bomb, too
    many files, or names that point outside the folder are refused), then each PDF is
    matched to a record by the name of its file, for you to confirm."""
    await enforce_limit(limiter, limits.UPLOADS_PER_USER, str(access.user.id))
    return await fulltext.start_batch(access, file, actor)


@router.get("/fulltext/bulk/{bid}", responses=PROJECT)
async def batch(bid: uuid.UUID, access: AdminAccess, fulltext: FulltextDep) -> BatchOut:
    return await fulltext.batch(access, bid)


@router.post("/fulltext/bulk/{bid}/confirm", responses={**PROJECT, **CONFLICT})
async def confirm_batch(
    bid: uuid.UUID,
    body: BatchConfirm,
    access: AdminAccess,
    fulltext: FulltextDep,
    actor: ActorDep,
) -> BatchApplied:
    """Attach the PDFs to the records chosen for them; the rest are thrown away."""
    return await fulltext.confirm_batch(
        access, bid, body.choices, replace=body.replace, actor=actor
    )


@router.delete("/fulltext/bulk/{bid}", status_code=status.HTTP_204_NO_CONTENT, responses=PROJECT)
async def discard_batch(
    bid: uuid.UUID, access: AdminAccess, fulltext: FulltextDep, actor: ActorDep
) -> None:
    await fulltext.discard_batch(access, bid, actor)


@files.get(
    "/files/{token}",
    response_class=Response,
    responses={
        **UNAUTHORIZED,
        404: problem_content(),
        200: {"content": {"application/pdf": {}}},
    },
)
async def open_file(
    token: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{20,100}$")],
    auth: AuthDep,
    fulltext: FulltextDep,
) -> StreamingResponse:
    """The PDF behind a link from `…/fulltext/url`, for whoever asked for the link."""
    opened = await fulltext.open_link(token, auth.user.id)
    disposition = "inline" if opened.inline else "attachment"
    fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", opened.filename)[:150] or "full-text.pdf"
    return StreamingResponse(
        fulltext.stream(opened.key),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{fallback}"; '
            f"filename*=UTF-8''{quote(opened.filename[:150])}",
            "Content-Length": str(opened.size),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )

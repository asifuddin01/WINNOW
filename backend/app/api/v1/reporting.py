"""PRISMA 2020 and screening statistics (guide 8.14, 8.15, 10).

Anyone in the review may see and download the PRISMA diagram (guide 7: "Export data,
PRISMA"); owners and admins set the counts Winnow cannot know. Statistics about other
reviewers follow blind mode (guide 8.6).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from app.api.deps import ActorDep, AdminAccess, ReportingDep, ViewerAccess
from app.api.responses import PROJECT, Responses
from app.images import svg_to_pdf, svg_to_png
from app.schemas.problem import problem_content
from app.schemas.reporting import PrismaManualIn, PrismaOut, StatsOut

router = APIRouter(prefix="/projects/{pid}", tags=["reporting"])

INCONSISTENT: Responses = {422: problem_content()}
MEDIA = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "pdf": "application/pdf",
}


@router.get("/prisma", responses={**PROJECT, **INCONSISTENT})
async def prisma(access: ViewerAccess, reporting: ReportingDep) -> PrismaOut:
    """The PRISMA 2020 flow, counted from the review (guide 9.4)."""
    return await reporting.prisma(access)


@router.patch("/prisma/manual", responses={**PROJECT, **INCONSISTENT})
async def update_prisma_manual(
    body: PrismaManualIn, access: AdminAccess, reporting: ReportingDep, actor: ActorDep
) -> PrismaOut:
    """Records found outside the imported databases, and records removed before screening
    for other reasons: what Winnow cannot count itself."""
    return await reporting.update_manual(access, body, actor)


@router.get(
    "/prisma.{kind}",
    response_class=Response,
    responses={
        **PROJECT,
        **INCONSISTENT,
        200: {"content": {media: {} for media in MEDIA.values()}},
    },
)
async def prisma_file(
    kind: Literal["svg", "png", "pdf"],
    access: ViewerAccess,
    reporting: ReportingDep,
    inline: Annotated[bool, Query(description="Shown in the app rather than downloaded")] = False,
) -> Response:
    """The diagram as SVG, PNG at 300 dpi or PDF."""
    svg = await reporting.prisma_svg(access)
    data = (
        svg.encode()
        if kind == "svg"
        else await svg_to_png(svg)
        if kind == "png"
        else await svg_to_pdf(svg)
    )
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=MEDIA[kind],
        headers={
            "Content-Disposition": f'{disposition}; filename="prisma-2020.{kind}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/stats", responses=PROJECT)
async def screening_stats(access: ViewerAccess, reporting: ReportingDep) -> StatsOut:
    """Progress per reviewer and stage, time per record, decisions per day, and
    inter-rater agreement (guide 8.15, 9.3)."""
    return await reporting.stats(access)

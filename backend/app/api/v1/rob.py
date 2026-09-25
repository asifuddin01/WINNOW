"""Risk of bias (guide 8.13, 10): the tools, each person's assessments, and the review's
traffic-light and summary plots.

Anyone who screens may assess an included study; everyone in the review may read the
summary, which under blind mode holds only the reader's own assessments.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app import rob
from app.api.deps import ActorDep, ResolverAccess, ReviewerAccess, RobDep, ViewerAccess
from app.api.responses import CONFLICT, PROJECT, Responses
from app.images import svg_to_png
from app.plots.rob import summary_bars, traffic_light
from app.schemas.problem import problem_content
from app.schemas.rob import (
    AssessmentIn,
    AssessmentOut,
    FinalIn,
    PlotKind,
    RecordRob,
    RobSummary,
    StudyStatus,
    ToolOut,
)
from app.services.errors import NotFoundError
from app.services.rob import template_for

router = APIRouter(prefix="/projects/{pid}/rob", tags=["risk of bias"])

INVALID: Responses = {422: problem_content()}
Tool = Annotated[
    str, Query(pattern=r"^[a-z][a-z0-9_]{0,63}$", description="rob2, robins_i, nos, quadas2")
]


@router.get("/tools", responses=PROJECT)
async def rob_tools(access: ViewerAccess, assessments: RobDep) -> list[ToolOut]:
    """The built-in tools, with their domains, signalling questions and judgements."""
    return assessments.tools()


@router.get("/studies", responses=PROJECT)
async def rob_studies(tool: Tool, access: ViewerAccess, assessments: RobDep) -> list[StudyStatus]:
    """The studies included at full text, and where each one's assessment stands."""
    return await assessments.studies(access, tool)


@router.get("/summary", responses=PROJECT)
async def rob_summary(tool: Tool, access: ViewerAccess, assessments: RobDep) -> RobSummary:
    """Per-domain counts and the traffic-light rows, from one final assessment per study."""
    return await assessments.summary(access, tool)


@router.get(
    "/summary.{kind}",
    response_class=Response,
    responses={**PROJECT, 200: {"content": {"image/svg+xml": {}, "image/png": {}}}},
)
async def rob_summary_plot(
    kind: Literal["svg", "png"],
    tool: Tool,
    access: ViewerAccess,
    assessments: RobDep,
    plot: Annotated[PlotKind, Query()] = "traffic-light",
    variant: Annotated[str | None, Query(max_length=64)] = None,
    inline: Annotated[bool, Query()] = False,
) -> Response:
    """The traffic-light table or the summary bar plot, as SVG or PNG at 300 dpi."""
    result = await assessments.summary(access, tool)
    template = template_for(tool)
    wanted = variant or next(
        (v.variant_key for v in result.variants if v.studies), template.variants[0].key
    )
    shown = next((v for v in result.variants if v.variant_key == wanted), None)
    form: rob.TemplateVariant | None = next((v for v in template.variants if v.key == wanted), None)
    if shown is None or form is None:
        raise NotFoundError(f"{template.name} has no form called {wanted!r}.")
    svg = (
        traffic_light(template, form, shown.studies)
        if plot == "traffic-light"
        else summary_bars(template, form, shown.domains)
    )
    data = svg.encode() if kind == "svg" else await svg_to_png(svg)
    return Response(
        content=data,
        media_type="image/svg+xml" if kind == "svg" else "image/png",
        headers={
            "Content-Disposition": f"{'inline' if inline else 'attachment'}; "
            f'filename="{tool}-{plot}.{kind}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{rid}", responses={**PROJECT, **CONFLICT})
async def record_assessments(
    rid: uuid.UUID, access: ViewerAccess, assessments: RobDep
) -> RecordRob:
    """This study's assessments: mine, and others' unless blind mode hides them."""
    return await assessments.for_record(access, rid)


@router.put("/{rid}", responses={**PROJECT, **CONFLICT, **INVALID})
async def save_assessment(
    rid: uuid.UUID, body: AssessmentIn, access: ReviewerAccess, assessments: RobDep, actor: ActorDep
) -> AssessmentOut:
    """Save my assessment of this study with one tool: a draft, or submitted when every
    domain is judged."""
    return await assessments.save(access, rid, body, actor)


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT, responses=PROJECT)
async def delete_assessment(
    rid: uuid.UUID, tool: Tool, access: ReviewerAccess, assessments: RobDep
) -> None:
    await assessments.delete(access, rid, tool)


@router.post("/{rid}/final", responses={**PROJECT, **CONFLICT})
async def choose_final(
    rid: uuid.UUID, body: FinalIn, access: ResolverAccess, assessments: RobDep, actor: ActorDep
) -> AssessmentOut:
    """Where several people assessed a study, the assessment the plots use."""
    return await assessments.mark_final(access, rid, body.assessment_id, actor)

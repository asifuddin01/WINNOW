"""The records table and one record: /api/v1/projects/{pid}/records (guide 10).

Any member may read records; what they may see of other people's decisions is settled in
the screening phase. Every query is scoped to the verified project.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import RecordsDep, ViewerAccess
from app.api.responses import PROJECT
from app.models import FullTextStatus, TitleAbstractStatus
from app.schemas.problem import problem_content
from app.schemas.records import RecordDetail, RecordFacets, RecordPage, Sort
from app.services.pagination import DEFAULT_LIMIT, MAX_LIMIT

router = APIRouter(prefix="/projects/{pid}", tags=["records"])

Search = Annotated[
    str,
    Query(
        max_length=500,
        description='Words, "exact phrases", -exclusions, author:, journal:, keyword:, '
        "year:2018..2024, a DOI or a PubMed id (guide 8.9)",
    ),
]


@router.get("/records", responses={**PROJECT, 400: problem_content()})
async def list_records(
    access: ViewerAccess,
    records: RecordsDep,
    q: Search = "",
    status: TitleAbstractStatus | None = None,
    full_text: FullTextStatus | None = None,
    batch: uuid.UUID | None = None,
    duplicates: bool = False,
    sort: Sort = "added",
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> RecordPage:
    """The records table: filtered, sorted and paged."""
    return await records.page(
        access,
        search=q,
        ta=status,
        ft=full_text,
        batch_id=batch,
        duplicates=duplicates,
        sort=sort,
        cursor=cursor,
        limit=limit,
    )


@router.get("/records/facets", responses=PROJECT)
async def record_facets(access: ViewerAccess, records: RecordsDep) -> RecordFacets:
    """How many records sit behind each filter."""
    return await records.facets(access)


@router.get("/records/{rid}", responses=PROJECT)
async def get_record(rid: uuid.UUID, access: ViewerAccess, records: RecordsDep) -> RecordDetail:
    return await records.detail(access, rid)

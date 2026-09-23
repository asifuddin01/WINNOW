"""Reading records: the table, one record, and the counts beside the filters (guide 10).

Every query starts from the verified project and, unless asked otherwise, hides records
already merged as duplicates.
"""

import uuid
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import Select, and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Decision,
    DecisionValue,
    FullTextStatus,
    ImportBatch,
    Label,
    Record,
    RecordLabel,
    ScreeningStage,
    TitleAbstractStatus,
)
from app.schemas.records import Count, RecordDetail, RecordFacets, RecordOut, RecordPage, Sort
from app.security.permissions import ProjectAccess
from app.services.blinding import sees_others
from app.services.errors import InvalidCursorError, NotFoundError
from app.services.pagination import decode_cursor, encode_cursor
from app.services.search import Query, parse_query

# Counting every matching row on a 100k-record project costs more than it tells anyone.
COUNT_CEILING = 10_000
FACET_TTL_SECONDS = 5
FACET_KEY = "facets:{project_id}"
TOP_YEARS = 12


# --- Blind mode -------------------------------------------------------------------------

OwnStatuses = dict[tuple[uuid.UUID, ScreeningStage], DecisionValue]

_OWN_TA = {
    DecisionValue.INCLUDE: TitleAbstractStatus.INCLUDED,
    DecisionValue.EXCLUDE: TitleAbstractStatus.EXCLUDED,
    DecisionValue.MAYBE: TitleAbstractStatus.MAYBE,
}
_OWN_FT = {
    DecisionValue.INCLUDE: FullTextStatus.INCLUDED,
    DecisionValue.EXCLUDE: FullTextStatus.EXCLUDED,
    DecisionValue.MAYBE: FullTextStatus.PENDING,
}


def _mine_is(access: ProjectAccess, stage: ScreeningStage, status: Any) -> Any:
    """For a blinded caller, "status X" means "I decided X" (and pending, that I have not
    decided). There is no conflict they could know of."""
    mine = select(Decision.decision).where(
        Decision.record_id == Record.id,
        Decision.user_id == access.user.id,
        Decision.stage == stage,
    )
    value = status.value if hasattr(status, "value") else str(status)
    if value in {"pending", "not_eligible"}:
        return ~mine.exists()
    wanted = {"included": "include", "excluded": "exclude", "maybe": "maybe"}.get(value)
    if wanted is None:
        return false()
    return mine.where(Decision.decision == DecisionValue(wanted)).exists()


class RecordService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self._db = db
        self._redis = redis

    # --- The table ---------------------------------------------------------------------

    def _filtered(
        self,
        access: ProjectAccess,
        *,
        query: Query,
        ta: TitleAbstractStatus | None,
        ft: FullTextStatus | None,
        batch_id: uuid.UUID | None,
        duplicates: bool,
    ) -> Select[Any]:
        statement = select(Record).where(Record.project_id == access.project_id)
        if not duplicates:
            statement = statement.where(Record.is_duplicate.is_(False))
        blind = not sees_others(access)
        if ta is not None:
            statement = statement.where(
                _mine_is(access, ScreeningStage.TITLE_ABSTRACT, ta)
                if blind
                else Record.ta_final == ta
            )
        if ft is not None:
            statement = statement.where(
                _mine_is(access, ScreeningStage.FULL_TEXT, ft) if blind else Record.ft_final == ft
            )
        if batch_id is not None:
            statement = statement.where(Record.import_batch_id == batch_id)
        return apply_search(statement, query, label_owner=access.user.id if blind else None)

    async def page(
        self,
        access: ProjectAccess,
        *,
        search: str = "",
        ta: TitleAbstractStatus | None = None,
        ft: FullTextStatus | None = None,
        batch_id: uuid.UUID | None = None,
        duplicates: bool = False,
        sort: Sort = "added",
        cursor: str | None = None,
        limit: int = 50,
    ) -> RecordPage:
        """One page of the records table, newest first unless another order is asked for."""
        query = parse_query(search)
        base = self._filtered(
            access, query=query, ta=ta, ft=ft, batch_id=batch_id, duplicates=duplicates
        )
        statement = _ordered(base, sort)
        if cursor is not None:
            statement = statement.where(_after(sort, cursor))
        rows = list(await self._db.scalars(statement.limit(limit + 1)))
        own = await self._own_statuses(access, [record.id for record in rows[:limit]])
        items = [_out(record, own) for record in rows[:limit]]
        next_cursor = _cursor_for(sort, rows[limit - 1]) if len(rows) > limit else None
        total, exact = await self._count(base)
        return RecordPage(items=items, next_cursor=next_cursor, total=total, total_is_exact=exact)

    async def _count(self, base: Select[Any]) -> tuple[int, bool]:
        capped = base.with_only_columns(Record.id).limit(COUNT_CEILING + 1).subquery()
        total = await self._db.scalar(select(func.count()).select_from(capped)) or 0
        return min(total, COUNT_CEILING), total <= COUNT_CEILING

    async def detail(self, access: ProjectAccess, record_id: uuid.UUID) -> RecordDetail:
        row = (
            await self._db.execute(
                select(Record, ImportBatch.source_name)
                .outerjoin(ImportBatch, ImportBatch.id == Record.import_batch_id)
                .where(Record.id == record_id, Record.project_id == access.project_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("That record is not in this review.")
        record, source = row
        own = await self._own_statuses(access, [record.id])
        return RecordDetail(**_out(record, own).model_dump(), **_extra(record), source=source)

    async def _own_statuses(
        self, access: ProjectAccess, record_ids: list[uuid.UUID]
    ) -> OwnStatuses | None:
        """For a blinded caller, their own decisions, which stand in for the final status;
        None when the caller may see the real one (guide 8.6)."""
        if sees_others(access) or not record_ids:
            return None
        own: OwnStatuses = {}
        rows = await self._db.execute(
            select(Decision.record_id, Decision.stage, Decision.decision).where(
                Decision.record_id.in_(record_ids), Decision.user_id == access.user.id
            )
        )
        for record_id, stage, decision in rows:
            own[(record_id, stage)] = decision
        return own

    # --- The filter panel ---------------------------------------------------------------

    async def facets(self, access: ProjectAccess) -> RecordFacets:
        """Counts for each filter. Cached for a few seconds: they move together."""
        key = FACET_KEY.format(project_id=access.project_id)
        if not sees_others(access):
            key = f"{key}:{access.user.id}"
        cached = await self._redis.get(key)
        if cached:
            return RecordFacets.model_validate_json(cached)
        facets = await self._compute_facets(access)
        await self._redis.set(key, facets.model_dump_json(), ex=FACET_TTL_SECONDS)
        return facets

    async def _compute_facets(self, access: ProjectAccess) -> RecordFacets:
        live = and_(Record.project_id == access.project_id, Record.is_duplicate.is_(False))
        if sees_others(access):
            ta_counts = await self._grouped(Record.ta_final, live)
            ft_counts = await self._grouped(Record.ft_final, live)
        else:
            ta_counts = await self._own_counts(access, live)
            ft_counts = []
        years = await self._db.execute(
            select(Record.year, func.count())
            .where(live, Record.year.is_not(None))
            .group_by(Record.year)
            .order_by(func.count().desc())
            .limit(TOP_YEARS)
        )
        imports = await self._db.execute(
            select(ImportBatch.id, ImportBatch.source_name, func.count(Record.id))
            .join(Record, Record.import_batch_id == ImportBatch.id)
            .where(ImportBatch.project_id == access.project_id, Record.is_duplicate.is_(False))
            .group_by(ImportBatch.id, ImportBatch.source_name)
            .order_by(ImportBatch.id.desc())
            .limit(50)
        )
        duplicates = await self._db.scalar(
            select(func.count())
            .select_from(Record)
            .where(Record.project_id == access.project_id, Record.is_duplicate.is_(True))
        )
        total = sum(count.count for count in ta_counts)
        return RecordFacets(
            title_abstract=ta_counts,
            full_text=ft_counts,
            years=[
                Count(value=str(year), label=str(year), count=count) for year, count in years.all()
            ],
            imports=[
                Count(value=str(batch_id), label=name, count=count)
                for batch_id, name, count in imports.all()
            ],
            duplicates=duplicates or 0,
            total=total,
        )

    async def _own_counts(self, access: ProjectAccess, live: Any) -> list[Count]:
        """A blinded caller's filter counts: their own decisions, and what they have not
        decided — never the review's final statuses, which come from everyone's."""
        total = await self._db.scalar(select(func.count()).select_from(Record).where(live)) or 0
        rows = await self._db.execute(
            select(Decision.decision, func.count())
            .join(Record, Record.id == Decision.record_id)
            .where(
                live,
                Decision.user_id == access.user.id,
                Decision.stage == ScreeningStage.TITLE_ABSTRACT,
            )
            .group_by(Decision.decision)
        )
        counts: list[Count] = []
        decided = 0
        for decision, count in rows:
            status = _OWN_TA[decision]
            counts.append(Count(value=status.value, label=status.value, count=count))
            decided += count
        pending = TitleAbstractStatus.PENDING.value
        return [Count(value=pending, label=pending, count=total - decided), *counts]

    async def _grouped(self, column: Any, condition: Any) -> list[Count]:
        rows = await self._db.execute(
            select(column, func.count()).where(condition).group_by(column)
        )
        return [
            Count(value=str(value), label=str(value).replace("_", " "), count=count)
            for value, count in rows.all()
        ]


# --- Search -----------------------------------------------------------------------------


def apply_search(
    statement: Select[Any], query: Query, *, label_owner: uuid.UUID | None = None
) -> Select[Any]:
    """The guide 8.9 search syntax as conditions on `records`, for any query over it.

    `label:` matches labels anyone applied, or only `label_owner`'s when that is given —
    a blinded reviewer sees and filters by their own labels only.
    """
    if query.text:
        statement = statement.where(
            Record.search_vector.op("@@")(func.websearch_to_tsquery("english", query.text))
        )
    for author in query.authors:
        statement = statement.where(Record.authors_text.ilike(f"%{author}%"))
    for journal in query.journals:
        statement = statement.where(Record.journal.ilike(f"%{journal}%"))
    for keyword in query.keywords:
        # Keywords carry weight C in the search vector, so this uses the same index.
        statement = statement.where(
            Record.search_vector.op("@@")(func.plainto_tsquery("english", keyword))
        )
    if query.year_from is not None:
        statement = statement.where(Record.year >= query.year_from)
    if query.year_to is not None:
        statement = statement.where(Record.year <= query.year_to)
    if query.doi:
        statement = statement.where(Record.doi_norm == query.doi)
    if query.pmid:
        statement = statement.where(Record.pmid == query.pmid)
    for kind in query.types:
        statement = statement.where(
            func.array_to_string(Record.publication_type, " ").ilike(f"%{kind}%")
        )
    for name in query.labels:
        labelled = (
            select(RecordLabel.record_id)
            .join(Label, Label.id == RecordLabel.label_id)
            .where(
                RecordLabel.record_id == Record.id,
                Label.project_id == Record.project_id,
                Label.name == name,
            )
        )
        if label_owner is not None:
            labelled = labelled.where(RecordLabel.user_id == label_owner)
        statement = statement.where(labelled.exists())
    return statement


# --- Ordering and cursors ---------------------------------------------------------------


def _ordered(statement: Select[Any], sort: Sort) -> Select[Any]:
    """Every order ends with the id, so a page boundary is never ambiguous."""
    if sort == "oldest":
        return statement.order_by(Record.id.asc())
    if sort == "year":
        return statement.order_by(Record.year.desc().nullslast(), Record.id.desc())
    if sort == "year_asc":
        return statement.order_by(Record.year.asc().nullslast(), Record.id.desc())
    if sort == "title":
        return statement.order_by(Record.title_norm.asc().nullslast(), Record.id.desc())
    if sort == "relevance":
        return statement.order_by(Record.relevance_score.desc().nullslast(), Record.id.desc())
    return statement.order_by(Record.id.desc())


def _cursor_for(sort: Sort, record: Record) -> str:
    if sort in {"added", "oldest"}:
        return encode_cursor(str(record.id))
    return encode_cursor(_sort_value(sort, record), str(record.id))


def _sort_value(sort: Sort, record: Record) -> str:
    if sort in {"year", "year_asc"}:
        return "" if record.year is None else str(record.year)
    if sort == "title":
        return record.title_norm or ""
    return "" if record.relevance_score is None else f"{record.relevance_score:.6f}"


def _after(sort: Sort, cursor: str) -> Any:
    """The keyset condition for the page after `cursor`, in this order."""
    if sort in {"added", "oldest"}:
        (last_id,) = decode_cursor(cursor, 1)
        record_id = _uuid(last_id)
        return Record.id > record_id if sort == "oldest" else Record.id < record_id
    value, last_id = decode_cursor(cursor, 2)
    record_id = _uuid(last_id)
    column, ascending = _sort_column(sort)
    if value == "":  # already past the rows that have a value
        return and_(column.is_(None), Record.id < record_id)
    typed: Any = value
    if sort in {"year", "year_asc"}:
        typed = int(value) if value.isdigit() else None
    elif sort == "relevance":
        typed = float(value)
    ahead = column > typed if ascending else column < typed
    return or_(ahead, and_(column == typed, Record.id < record_id), column.is_(None))


def _sort_column(sort: Sort) -> tuple[Any, bool]:
    if sort in {"year", "year_asc"}:
        return Record.year, sort == "year_asc"
    if sort == "title":
        return Record.title_norm, True
    return Record.relevance_score, False


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise InvalidCursorError from None


def _out(record: Record, own: OwnStatuses | None = None) -> RecordOut:
    ta_final, ft_final = record.ta_final, record.ft_final
    if own is not None:  # a blinded caller: their own decision is the status they see
        mine_ta = own.get((record.id, ScreeningStage.TITLE_ABSTRACT))
        mine_ft = own.get((record.id, ScreeningStage.FULL_TEXT))
        ta_final = _OWN_TA[mine_ta] if mine_ta else TitleAbstractStatus.PENDING
        ft_final = _OWN_FT[mine_ft] if mine_ft else FullTextStatus.NOT_ELIGIBLE
    return RecordOut(
        id=record.id,
        title=record.title,
        authors=record.authors,
        year=record.year,
        journal=record.journal,
        doi=record.doi,
        pmid=record.pmid,
        ta_final=ta_final,
        ft_final=ft_final,
        is_duplicate=record.is_duplicate,
        relevance_score=record.relevance_score,
        import_batch_id=record.import_batch_id,
        created_at=record.created_at,
    )


def _extra(record: Record) -> dict[str, Any]:
    return {
        "abstract": record.abstract,
        "volume": record.volume,
        "issue": record.issue,
        "pages": record.pages,
        "pmcid": record.pmcid,
        "isbn": record.isbn,
        "url": record.url,
        "keywords": record.keywords,
        "language": record.language,
        "publication_type": record.publication_type,
        "duplicate_of": record.duplicate_of,
        "raw": record.raw,
    }

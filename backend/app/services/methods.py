"""The facts behind a review's methods text (guide 8.15), read from the review.

What people did together (agreement, how disagreements were settled, work done in
duplicate) is told only to members who may see others' decisions, as the statistics are;
a blinded reader's text leaves those sentences out.
"""

from datetime import date

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import rob
from app.models import (
    ConflictResolution,
    Decision,
    ImportBatch,
    ImportStatus,
    LlmSuggestion,
    RankingModel,
    RobAssessment,
    RobStatus,
    ScreeningStage,
)
from app.reporting import (
    Agreement,
    AiUse,
    Count,
    DatabaseSearch,
    MethodsFacts,
    Resolutions,
    methods_text,
)
from app.schemas.reporting import Agreement as AgreementOut
from app.schemas.reporting import MethodsOut, PrismaOut
from app.security.permissions import ProjectAccess
from app.services.blinding import sees_others, settings_of
from app.services.reporting import PrismaDoesNotAddUpError, ReportingService, canonical


def agreement_of(out: AgreementOut) -> Agreement | None:
    """The statistics' agreement as the methods text states it."""
    if out.raters >= 3 and out.fleiss_kappa is not None:
        return Agreement(kappa=out.fleiss_kappa, band=out.fleiss_band, fleiss=True)
    judged = [pair for pair in out.pairs if pair.kappa is not None or pair.percent is not None]
    if len(judged) == 1:
        pair = judged[0]
        return Agreement(kappa=pair.kappa, band=pair.band, percent=pair.percent)
    kappas = [pair.kappa for pair in judged if pair.kappa is not None]
    if len(kappas) > 1:
        return Agreement(kappa_range=(min(kappas), max(kappas)), pairs=len(kappas))
    return None


class MethodsService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def methods(self, access: ProjectAccess) -> MethodsOut:
        facts, complete = await self.facts(access)
        return MethodsOut(
            text=methods_text(facts), complete=complete, blind=not sees_others(access)
        )

    async def facts(self, access: ProjectAccess) -> tuple[MethodsFacts, bool]:
        """The review's facts, and whether screening is finished (else they are a snapshot)."""
        reporting = ReportingService(self._db)
        try:
            flow: PrismaOut | None = await reporting.prisma(access)
        except PrismaDoesNotAddUpError:
            flow = None
        settings = settings_of(access)
        told = sees_others(access)
        stages = (ScreeningStage.TITLE_ABSTRACT, ScreeningStage.FULL_TEXT)
        agreements = {
            stage: agreement_of(await reporting.agreement(access, stage)) if told else None
            for stage in stages
        }
        resolutions = await self._resolutions(access) if told else {}
        tools, duplicate = await self._rob(access)
        facts = MethodsFacts(
            databases=await self._databases(access, flow),
            other_sources=tuple(Count(s.name, s.count) for s in flow.other_sources) if flow else (),
            duplicates_removed=flow.duplicates_removed if flow else None,
            records_screened=flow.records_screened if flow else None,
            reviewers_ta=settings.reviewers_per_record_ta,
            reviewers_ft=settings.reviewers_per_record_ft,
            blind=settings.blind_mode,
            agreement_ta=agreements[ScreeningStage.TITLE_ABSTRACT],
            agreement_ft=agreements[ScreeningStage.FULL_TEXT],
            resolutions_ta=resolutions.get(ScreeningStage.TITLE_ABSTRACT),
            resolutions_ft=resolutions.get(ScreeningStage.FULL_TEXT),
            ranked=settings.ranking_enabled and await self._ranked(access),
            ai=await self._ai(access),
            reports_sought=flow.reports_sought if flow else None,
            reports_not_retrieved=flow.reports_not_retrieved if flow else None,
            reports_assessed=flow.reports_assessed if flow else None,
            reports_excluded=tuple(Count(r.reason, r.count) for r in flow.reports_excluded)
            if flow
            else (),
            studies_included=flow.studies_included if flow else None,
            rob_tools=tools,
            rob_duplicate=duplicate if told else None,
        )
        complete = flow is not None and flow.awaiting_title_abstract + flow.awaiting_full_text == 0
        return facts, complete

    async def _databases(
        self, access: ProjectAccess, flow: PrismaOut | None
    ) -> tuple[DatabaseSearch, ...]:
        if flow is None:
            return ()
        searched: dict[str, date] = {}
        for name, when in await self._db.execute(
            select(ImportBatch.database_name, func.max(ImportBatch.search_date))
            .where(
                ImportBatch.project_id == access.project_id,
                ImportBatch.status == ImportStatus.DONE,
            )
            .group_by(ImportBatch.database_name)
        ):
            key = canonical(name)
            if when is not None and (key not in searched or when > searched[key]):
                searched[key] = when
        return tuple(
            DatabaseSearch(source.name, source.count, searched.get(canonical(source.name)))
            for source in flow.database_sources
        )

    async def _resolutions(self, access: ProjectAccess) -> dict[ScreeningStage, Resolutions]:
        """How disagreements were settled: by one of the record's own reviewers (discussion)
        or by someone who had not decided it (a third reviewer)."""
        own = exists().where(
            Decision.record_id == ConflictResolution.record_id,
            Decision.stage == ConflictResolution.stage,
            Decision.user_id == ConflictResolution.resolved_by,
        )
        rows = await self._db.execute(
            select(ConflictResolution.stage, func.count(), func.count().filter(own))
            .where(ConflictResolution.project_id == access.project_id)
            .group_by(ConflictResolution.stage)
        )
        return {
            stage: Resolutions(total=total, by_discussion=mine, by_third_reviewer=total - mine)
            for stage, total, mine in rows
        }

    async def _ranked(self, access: ProjectAccess) -> bool:
        return bool(
            await self._db.scalar(
                select(
                    exists().where(
                        RankingModel.project_id == access.project_id,
                        RankingModel.stage == ScreeningStage.TITLE_ABSTRACT,
                    )
                )
            )
        )

    async def _ai(self, access: ProjectAccess) -> AiUse | None:
        records = await self._db.scalar(
            select(func.count(func.distinct(LlmSuggestion.record_id))).where(
                LlmSuggestion.project_id == access.project_id
            )
        )
        if not records:
            return None
        models = await self._db.scalars(
            select(LlmSuggestion.model)
            .where(LlmSuggestion.project_id == access.project_id)
            .distinct()
            .order_by(LlmSuggestion.model)
        )
        return AiUse(records=records, models=tuple(models))

    async def _rob(self, access: ProjectAccess) -> tuple[tuple[str, ...], bool]:
        """The tools studies were assessed with, and whether any study was assessed by
        more than one person."""
        per_study = (
            select(RobAssessment.tool_key, func.count().label("people"))
            .where(
                RobAssessment.project_id == access.project_id,
                RobAssessment.status == RobStatus.SUBMITTED,
            )
            .group_by(RobAssessment.tool_key, RobAssessment.record_id)
            .subquery()
        )
        rows = await self._db.execute(
            select(per_study.c.tool_key, func.max(per_study.c.people))
            .group_by(per_study.c.tool_key)
            .order_by(per_study.c.tool_key)
        )
        tools, duplicate = [], False
        for key, most in rows:
            tools.append(rob.get_template(key).name)
            duplicate = duplicate or most > 1
        return tuple(tools), duplicate

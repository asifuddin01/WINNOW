"""PRISMA 2020 counts and screening statistics for one review (guide 8.14, 8.15, 9.3, 9.4).

The arithmetic and the diagram are `app.prisma`'s, the agreement measures `app.stats`'s
(pure modules); this adapter reads the review's numbers for them. Everything is scoped by
the verified `project_id`, and duplicates are left out of every count after
identification.
"""

import unicodedata
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Date, cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import stats
from app.models import (
    ConflictResolution,
    Decision,
    DecisionValue,
    ExclusionReason,
    FinalDecision,
    FullTextStatus,
    ImportBatch,
    ImportStatus,
    PrismaManual,
    Record,
    ScreeningStage,
    TitleAbstractStatus,
    User,
)
from app.prisma import ExclusionCount, PrismaInputs, SourceCount, counts, render_svg
from app.schemas.reporting import (
    Agreement,
    DayCount,
    PairAgreement,
    PrismaManualIn,
    PrismaManualOut,
    PrismaOut,
    ReasonCount,
    ReviewerProgress,
    SourceOut,
    StageStats,
    StatsOut,
)
from app.security.permissions import ProjectAccess
from app.services import audit
from app.services.audit import Actor
from app.services.blinding import can_resolve, sees_others, settings_of
from app.services.errors import ConflictError, DomainError

NO_REASON = "Reason not recorded"
PER_DAY = 60  # days of decisions-per-day shown


class PrismaDoesNotAddUpError(DomainError):
    status = 422
    code = "prisma_inconsistent"


def canonical(name: str) -> str:
    return unicodedata.normalize("NFKC", name).strip().casefold()


class ReportingService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # --- PRISMA ------------------------------------------------------------------------

    async def prisma(self, access: ProjectAccess) -> PrismaOut:
        inputs, manual, awaiting = await self._prisma_inputs(access)
        try:
            flow = counts(inputs)
        except ValueError as error:
            raise PrismaDoesNotAddUpError(
                f"The PRISMA numbers do not add up ({error}). Check the manual counts."
            ) from error
        return PrismaOut(
            database_sources=[SourceOut(name=s.name, count=s.count) for s in flow.database_sources],
            other_sources=[SourceOut(name=s.name, count=s.count) for s in flow.other_sources],
            records_identified=flow.records_identified_total,
            duplicates_removed=flow.duplicates_removed,
            records_removed_other_reasons=flow.records_removed_other_reasons,
            records_screened=flow.records_screened,
            records_excluded=flow.records_excluded,
            reports_sought=flow.reports_sought,
            reports_not_retrieved=flow.reports_not_retrieved,
            reports_assessed=flow.reports_assessed,
            reports_excluded=[
                ReasonCount(reason=r.reason, count=r.count)
                for r in flow.reports_excluded_with_reasons
            ],
            reports_excluded_total=flow.reports_excluded_total,
            studies_included=flow.studies_included,
            awaiting_title_abstract=awaiting[0],
            awaiting_full_text=awaiting[1],
            manual=manual,
        )

    async def prisma_svg(self, access: ProjectAccess) -> str:
        inputs, _, _ = await self._prisma_inputs(access)
        try:
            return render_svg(counts(inputs))
        except ValueError as error:
            raise PrismaDoesNotAddUpError(
                f"The PRISMA numbers do not add up ({error}). Check the manual counts."
            ) from error

    async def update_manual(
        self, access: ProjectAccess, body: PrismaManualIn, actor: Actor
    ) -> PrismaOut:
        names = [canonical(source.name) for source in body.other_sources]
        if len(set(names)) != len(names):
            raise ConflictError("Each other source may be listed once.")
        values = {
            "other_sources": [source.model_dump() for source in body.other_sources],
            "removed_other_reasons": body.removed_other_reasons,
            "updated_by": access.user.id,
            "updated_at": func.now(),
        }
        await self._db.execute(
            insert(PrismaManual)
            .values(project_id=access.project_id, **values)
            .on_conflict_do_update(index_elements=[PrismaManual.project_id], set_=values)
        )
        audit.record(
            self._db,
            "prisma.manual_changed",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="project",
            entity_id=access.project_id,
            after={
                "other_sources": len(body.other_sources),
                "removed_other_reasons": body.removed_other_reasons,
            },
        )
        # Refuse numbers that cannot stand, before they are kept.
        await self._db.flush()
        result = await self.prisma(access)
        await self._db.commit()
        return result

    async def _prisma_inputs(
        self, access: ProjectAccess
    ) -> tuple[PrismaInputs, PrismaManualOut, tuple[int, int]]:
        pid = access.project_id
        # Identification: records imported, per database, however its name was typed.
        imported = await self._db.execute(
            select(ImportBatch.database_name, ImportBatch.imported)
            .where(ImportBatch.project_id == pid, ImportBatch.status == ImportStatus.DONE)
            .order_by(ImportBatch.created_at, ImportBatch.id)
        )
        databases: dict[str, list[Any]] = {}
        for name, count in imported:
            key = canonical(name)
            if key in databases:
                databases[key][1] += count
            else:
                databases[key] = [name.strip(), count]
        manual_row = await self._db.get(PrismaManual, pid)
        manual = PrismaManualOut(
            other_sources=[
                SourceOut(**source) for source in (manual_row.other_sources if manual_row else [])
            ],
            removed_other_reasons=manual_row.removed_other_reasons if manual_row else 0,
            updated_at=manual_row.updated_at if manual_row else None,
        )

        live = [Record.project_id == pid, Record.is_duplicate.is_(False)]
        duplicates = await self._db.scalar(
            select(func.count()).where(Record.project_id == pid, Record.is_duplicate.is_(True))
        )
        ta = dict(
            (
                await self._db.execute(
                    select(Record.ta_final, func.count()).where(*live).group_by(Record.ta_final)
                )
            )
            .tuples()
            .all()
        )
        # Full-text outcomes of records still included at title and abstract: a record
        # excluded there later keeps any full-text work done on it, but is no longer sought.
        at_full_text = [*live, Record.ta_final == TitleAbstractStatus.INCLUDED]
        ft = dict(
            (
                await self._db.execute(
                    select(Record.ft_final, func.count())
                    .where(*at_full_text)
                    .group_by(Record.ft_final)
                )
            )
            .tuples()
            .all()
        )
        excluded_reasons = await self._primary_reasons(access, at_full_text)

        inputs = PrismaInputs(
            database_sources=tuple(
                SourceCount(name=name, count=count) for name, count in databases.values()
            ),
            other_sources=tuple(
                SourceCount(name=s.name, count=s.count) for s in manual.other_sources
            ),
            duplicates_removed=duplicates or 0,
            records_removed_other_reasons=manual.removed_other_reasons,
            non_duplicate_records=sum(ta.values()),
            title_abstract_excluded=ta.get(TitleAbstractStatus.EXCLUDED, 0),
            title_abstract_included=ta.get(TitleAbstractStatus.INCLUDED, 0),
            reports_not_retrieved=ft.get(FullTextStatus.NOT_RETRIEVABLE, 0),
            full_text_exclusions=tuple(
                ExclusionCount(reason=reason, count=count) for reason, count in excluded_reasons
            ),
            full_text_included=ft.get(FullTextStatus.INCLUDED, 0),
        )
        awaiting = (
            ta.get(TitleAbstractStatus.PENDING, 0) + ta.get(TitleAbstractStatus.CONFLICT, 0),
            ft.get(FullTextStatus.PENDING, 0) + ft.get(FullTextStatus.CONFLICT, 0),
        )
        return inputs, manual, awaiting

    async def _primary_reasons(
        self, access: ProjectAccess, at_full_text: list[Any]
    ) -> list[tuple[str, int]]:
        """One reason per excluded report (PRISMA counts reports, not reasons): the reason
        a resolution gave, else the excluding reviewers' reasons; of those, the one listed
        first in the review's reasons."""
        excluded = list(
            await self._db.scalars(
                select(Record.id).where(*at_full_text, Record.ft_final == FullTextStatus.EXCLUDED)
            )
        )
        if not excluded:
            return []
        reasons = {
            reason.id: reason
            for reason in await self._db.scalars(
                select(ExclusionReason)
                .where(ExclusionReason.project_id == access.project_id)
                .order_by(ExclusionReason.position, ExclusionReason.id)
            )
        }
        given: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        resolved = await self._db.execute(
            select(ConflictResolution.record_id, ConflictResolution.reason_ids).where(
                ConflictResolution.project_id == access.project_id,
                ConflictResolution.stage == ScreeningStage.FULL_TEXT,
                ConflictResolution.final_decision == FinalDecision.EXCLUDE,
                ConflictResolution.record_id.in_(excluded),
            )
        )
        settled: set[uuid.UUID] = set()
        for record_id, reason_ids in resolved:
            settled.add(record_id)
            given[record_id].update(reason_ids)
        decided = await self._db.execute(
            select(Decision.record_id, Decision.reason_ids).where(
                Decision.project_id == access.project_id,
                Decision.stage == ScreeningStage.FULL_TEXT,
                Decision.decision == DecisionValue.EXCLUDE,
                Decision.record_id.in_(excluded),
            )
        )
        for record_id, reason_ids in decided:
            if record_id not in settled:
                given[record_id].update(reason_ids)

        order = {reason_id: index for index, reason_id in enumerate(reasons)}
        counts: dict[str, int] = defaultdict(int)
        for record_id in excluded:
            known = [r for r in given.get(record_id, ()) if r in order]
            label = str(reasons[min(known, key=order.__getitem__)].label) if known else NO_REASON
            counts[label] += 1
        ranked = [str(reason.label) for reason in reasons.values()]
        return sorted(
            counts.items(),
            key=lambda item: (
                item[0] == NO_REASON,
                ranked.index(item[0]) if item[0] in ranked else 0,
            ),
        )

    # --- Statistics --------------------------------------------------------------------

    async def stats(self, access: ProjectAccess) -> StatsOut:
        told = sees_others(access) or can_resolve(access)
        stages = [await self._stage_stats(access, stage, told) for stage in ScreeningStage]
        return StatsOut(stages=stages, blind=not told)

    async def _stage_stats(
        self, access: ProjectAccess, stage: ScreeningStage, told: bool
    ) -> StageStats:
        pid = access.project_id
        me = access.user.id
        eligible: list[Any] = [Record.project_id == pid, Record.is_duplicate.is_(False)]
        if stage is ScreeningStage.FULL_TEXT:
            eligible.append(Record.ta_final == TitleAbstractStatus.INCLUDED)
        column = Record.ta_final if stage is ScreeningStage.TITLE_ABSTRACT else Record.ft_final
        records = await self._db.scalar(select(func.count()).where(*eligible)) or 0
        undecided = ("pending", "conflict")
        decided = await self._db.scalar(
            select(func.count()).where(*eligible, column.not_in(undecided))
        )
        conflicts = (
            await self._db.scalar(select(func.count()).where(*eligible, column == "conflict"))
            if told
            else None
        )

        scope = [Decision.project_id == pid, Decision.stage == stage]
        if not told:
            scope.append(Decision.user_id == me)
        per_reviewer = await self._db.execute(
            select(
                Decision.user_id,
                User.name,
                func.count(),
                func.count().filter(Decision.decision == DecisionValue.INCLUDE),
                func.count().filter(Decision.decision == DecisionValue.EXCLUDE),
                func.count().filter(Decision.decision == DecisionValue.MAYBE),
                func.percentile_cont(0.5).within_group(Decision.time_spent_ms),
            )
            .join(User, User.id == Decision.user_id)
            .where(*scope)
            .group_by(Decision.user_id, User.name)
            .order_by(User.name, Decision.user_id)
        )
        reviewers = [
            ReviewerProgress(
                user_id=user_id,
                name=name,
                mine=user_id == me,
                decided=total,
                included=included,
                excluded=excluded,
                maybe=maybe,
                median_seconds=None if median is None else round(float(median) / 1000, 1),
            )
            for user_id, name, total, included, excluded, maybe, median in per_reviewer
        ]

        since = datetime.now(UTC) - timedelta(days=PER_DAY)
        day = cast(Decision.created_at, Date)
        per_day = [
            DayCount(day=value, decisions=count)
            for value, count in await self._db.execute(
                select(day, func.count())
                .where(*scope, Decision.created_at >= since)
                .group_by(day)
                .order_by(day)
            )
        ]

        agreement = await self.agreement(access, stage) if told else None
        return StageStats(
            stage=stage,
            records=records,
            decided=decided or 0,
            conflicts=conflicts,
            reviewers=reviewers,
            per_day=per_day,
            agreement=agreement,
        )

    async def agreement(self, access: ProjectAccess, stage: ScreeningStage) -> Agreement:
        rows = await self._db.execute(
            select(Decision.record_id, Decision.user_id, Decision.decision, User.name)
            .join(User, User.id == Decision.user_id)
            .join(Record, Record.id == Decision.record_id)
            .where(
                Decision.project_id == access.project_id,
                Decision.stage == stage,
                Record.is_duplicate.is_(False),
            )
        )
        decisions: list[stats.Decision] = []
        names: dict[uuid.UUID, str] = {}
        by_record: dict[uuid.UUID, int] = defaultdict(int)
        for record_id, user_id, value, name in rows:
            decisions.append(
                stats.Decision(record_id=record_id, reviewer_id=user_id, decision=value.value)
            )
            names[user_id] = name
            by_record[record_id] += 1
        # At full text a "maybe" is not an answer, so it stays a category of its own.
        maybe: stats.MaybeCountsAs = (
            settings_of(access).maybe_counts_as
            if stage is ScreeningStage.TITLE_ABSTRACT
            else "maybe"
        )
        reviewers = sorted(names, key=lambda user_id: (names[user_id], str(user_id)))
        pairs = []
        for index, a in enumerate(reviewers):
            for b in reviewers[index + 1 :]:
                both = {d.record_id for d in decisions if d.reviewer_id == a} & {
                    d.record_id for d in decisions if d.reviewer_id == b
                }
                if not both:
                    continue
                kappa = stats.cohens_kappa(decisions, a, b, maybe_counts_as=maybe)
                pairs.append(
                    PairAgreement(
                        reviewer_a=names[a],
                        reviewer_b=names[b],
                        records=len(both),
                        percent=stats.percent_agreement(decisions, a, b, maybe_counts_as=maybe),
                        kappa=kappa,
                        band=None if kappa is None else stats.landis_koch(kappa),
                    )
                )

        settings = settings_of(access)
        raters = (
            settings.reviewers_per_record_ta
            if stage is ScreeningStage.TITLE_ABSTRACT
            else settings.reviewers_per_record_ft
        )
        fleiss = None
        cohort: set[uuid.UUID] = set()
        if raters >= 3:
            cohort = {record_id for record_id, count in by_record.items() if count == raters}
            if cohort:
                fleiss = stats.fleiss_kappa(
                    [d for d in decisions if d.record_id in cohort], maybe_counts_as=maybe
                )
        return Agreement(
            pairs=pairs,
            fleiss_kappa=fleiss,
            fleiss_band=None if fleiss is None else stats.landis_koch(fleiss),
            fleiss_records=len(cohort),
            raters=raters,
        )

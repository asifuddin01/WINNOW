"""Risk of bias (guide 8.13) on Codex's `app.rob` templates.

Each person assesses a study on their own, blinded like screening decisions (guide 8.6).
The review's plots use one final assessment per study and tool: the only submitted one,
or, where several people assessed it, the one an owner or admin marks final.
"""

import uuid
from collections import defaultdict

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import rob
from app.models import FullTextStatus, Record, RobAssessment, RobStatus, User
from app.schemas.rob import (
    AssessmentIn,
    AssessmentOut,
    AxisOut,
    ChoiceOut,
    DomainOut,
    DomainSummaryOut,
    JudgementCountOut,
    QuestionOut,
    RecordRob,
    RobSummary,
    StudyRow,
    ToolOut,
    VariantOut,
    VariantSummary,
)
from app.security.permissions import Capability, ProjectAccess
from app.services import audit
from app.services.audit import Actor
from app.services.blinding import sees_others
from app.services.errors import ConflictError, DomainError, ForbiddenError, NotFoundError


class InvalidAssessmentError(DomainError):
    status = 422
    code = "invalid_assessment"


def tool_out(template: rob.ToolTemplate) -> ToolOut:
    return ToolOut(
        key=template.key,
        name=template.name,
        version=template.version,
        source_url=template.source_url,
        note=template.content_note,
        variants=[
            VariantOut(
                key=variant.key,
                name=variant.name,
                domains=[
                    DomainOut(
                        key=domain.key,
                        name=domain.name,
                        questions=[
                            QuestionOut(
                                key=question.key,
                                prompt=question.prompt,
                                answers=list(question.allowed_answers),
                            )
                            for question in domain.signalling_questions
                        ],
                        axes=[
                            AxisOut(
                                key=axis.key,
                                name=axis.name,
                                judgements=[
                                    ChoiceOut(key=choice.key, label=choice.label)
                                    for choice in axis.allowed_judgements
                                ],
                            )
                            for axis in domain.judgement_axes
                        ],
                    )
                    for domain in variant.domains
                ],
            )
            for variant in template.variants
        ],
    )


def template_for(tool_key: str) -> rob.ToolTemplate:
    try:
        return rob.get_template(tool_key)
    except (KeyError, ValueError) as error:
        raise NotFoundError("Winnow has no such risk-of-bias tool.") from error


def variant_for(template: rob.ToolTemplate, variant_key: str) -> rob.TemplateVariant:
    for variant in template.variants:
        if variant.key == variant_key:
            return variant
    raise InvalidAssessmentError(f"{template.name} has no form called {variant_key!r}.")


def check(template: rob.ToolTemplate, body: AssessmentIn) -> list[str]:
    """Every problem with the assessment, in words; none means it fits the tool."""
    variant = variant_for(template, body.variant_key)
    domains = {domain.key: domain for domain in variant.domains}
    problems: list[str] = []
    for part in (body.answers, body.judgements, body.support):
        problems += [
            f"{template.name} has no domain {key!r}." for key in part if key not in domains
        ]
    for domain_key, answers in body.answers.items():
        domain = domains.get(domain_key)
        if domain is None:
            continue
        questions = {question.key: question for question in domain.signalling_questions}
        for question_key, answer in answers.items():
            question = questions.get(question_key)
            if question is None:
                problems.append(f"{domain.name} has no question {question_key!r}.")
            elif answer not in question.allowed_answers:
                problems.append(f"{answer!r} is not an answer to {question.prompt!r}.")
    for domain_key, judged in body.judgements.items():
        domain = domains.get(domain_key)
        if domain is None:
            continue
        axes = {axis.key: axis for axis in domain.judgement_axes}
        for axis_key, judgement in judged.items():
            axis = axes.get(axis_key)
            if axis is None:
                problems.append(f"{domain.name} is not judged on {axis_key!r}.")
            elif judgement not in {choice.key for choice in axis.allowed_judgements}:
                problems.append(f"{judgement!r} is not a judgement of {axis.name} ({domain.name}).")
    overall_choices = {
        choice.key
        for domain in variant.domains
        for axis in domain.judgement_axes[:1]
        for choice in axis.allowed_judgements
    }
    if body.overall is not None and body.overall not in overall_choices:
        problems.append(f"{body.overall!r} is not an overall judgement in {template.name}.")
    if body.status is RobStatus.SUBMITTED:
        for domain in variant.domains:
            for axis in domain.judgement_axes:
                if axis.key not in body.judgements.get(domain.key, {}):
                    problems.append(f"{domain.name}: {axis.name} needs a judgement.")
    return problems


class RobService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def tools(self) -> list[ToolOut]:
        return [tool_out(template) for template in rob.BUILTIN_TEMPLATES]

    async def for_record(self, access: ProjectAccess, record_id: uuid.UUID) -> RecordRob:
        record = await self._included(access, record_id)
        statement = (
            select(RobAssessment, User.name)
            .outerjoin(User, User.id == RobAssessment.user_id)
            .where(
                RobAssessment.project_id == access.project_id,
                RobAssessment.record_id == record.id,
            )
            .order_by(RobAssessment.tool_key, RobAssessment.created_at)
        )
        if not sees_others(access):
            statement = statement.where(RobAssessment.user_id == access.user.id)
        rows = await self._db.execute(statement)
        return RecordRob(
            record_id=record.id,
            title=record.title,
            assessments=[_out(row, name, access.user.id) for row, name in rows],
        )

    async def save(
        self, access: ProjectAccess, record_id: uuid.UUID, body: AssessmentIn, actor: Actor
    ) -> AssessmentOut:
        record = await self._included(access, record_id)
        template = template_for(body.tool_key)
        problems = check(template, body)
        if problems:
            raise InvalidAssessmentError(" ".join(problems[:10]))
        values = {
            "tool_version": template.version,
            "variant_key": body.variant_key,
            "answers": body.answers,
            "judgements": body.judgements,
            "support": {key: text for key, text in body.support.items() if text},
            "overall": body.overall,
            "status": body.status,
        }
        saved = (
            await self._db.execute(
                insert(RobAssessment)
                .values(
                    project_id=access.project_id,
                    record_id=record.id,
                    user_id=access.user.id,
                    tool_key=body.tool_key,
                    **values,
                )
                .on_conflict_do_update(
                    index_elements=[
                        RobAssessment.record_id,
                        RobAssessment.user_id,
                        RobAssessment.tool_key,
                    ],
                    # A changed assessment is no longer the one chosen as final.
                    set_={**values, "final": False, "updated_at": func.now()},
                )
                .returning(RobAssessment)
            )
        ).scalar_one()
        audit.record(
            self._db,
            "rob.saved",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record.id,
            after={"tool": body.tool_key, "status": body.status.value},
        )
        await self._db.commit()
        await self._db.refresh(saved)
        return _out(saved, access.user.name, access.user.id)

    async def delete(self, access: ProjectAccess, record_id: uuid.UUID, tool_key: str) -> None:
        row = await self._db.scalar(
            select(RobAssessment).where(
                RobAssessment.project_id == access.project_id,
                RobAssessment.record_id == record_id,
                RobAssessment.user_id == access.user.id,
                RobAssessment.tool_key == tool_key,
            )
        )
        if row is None:
            raise NotFoundError("You have no such assessment of this record.")
        await self._db.delete(row)
        await self._db.commit()

    async def mark_final(
        self, access: ProjectAccess, record_id: uuid.UUID, assessment_id: uuid.UUID, actor: Actor
    ) -> AssessmentOut:
        if not access.can(Capability.RESOLVE_CONFLICTS):
            raise ForbiddenError("Only those who resolve conflicts choose the final assessment.")
        chosen = await self._db.scalar(
            select(RobAssessment).where(
                RobAssessment.id == assessment_id,
                RobAssessment.project_id == access.project_id,
                RobAssessment.record_id == record_id,
            )
        )
        if chosen is None:
            raise NotFoundError("That assessment is not in this review.")
        if chosen.status is not RobStatus.SUBMITTED:
            raise ConflictError("Only a submitted assessment can be the final one.")
        await self._db.execute(
            update(RobAssessment)
            .where(
                RobAssessment.project_id == access.project_id,
                RobAssessment.record_id == record_id,
                RobAssessment.tool_key == chosen.tool_key,
            )
            .values(final=RobAssessment.id == chosen.id)
        )
        audit.record(
            self._db,
            "rob.final_chosen",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record_id,
            after={"tool": chosen.tool_key, "assessment": str(chosen.id)},
        )
        await self._db.commit()
        await self._db.refresh(chosen)
        name = await self._db.scalar(select(User.name).where(User.id == chosen.user_id))
        return _out(chosen, name, access.user.id)

    async def summary(self, access: ProjectAccess, tool_key: str) -> RobSummary:
        template = template_for(tool_key)
        own_only = not sees_others(access)
        statement = (
            select(RobAssessment, Record.authors, Record.year, Record.title)
            .join(Record, Record.id == RobAssessment.record_id)
            .where(
                RobAssessment.project_id == access.project_id,
                RobAssessment.tool_key == tool_key,
                RobAssessment.status == RobStatus.SUBMITTED,
                Record.is_duplicate.is_(False),
            )
            .order_by(Record.year.nulls_last(), Record.id, RobAssessment.created_at)
        )
        if own_only:
            statement = statement.where(RobAssessment.user_id == access.user.id)
        per_record: dict[uuid.UUID, list[RobAssessment]] = defaultdict(list)
        labels: dict[uuid.UUID, str] = {}
        for row, authors, year, title in await self._db.execute(statement):
            per_record[row.record_id].append(row)
            labels[row.record_id] = _study_label(authors, year, title)

        finals: list[RobAssessment] = []
        awaiting: list[uuid.UUID] = []
        for record_id, rows in per_record.items():
            chosen = [row for row in rows if row.final]
            if chosen:
                finals.append(chosen[0])
            elif len(rows) == 1:
                finals.append(rows[0])
            else:
                awaiting.append(record_id)

        variants: list[VariantSummary] = []
        for variant in template.variants:
            cohort = [row for row in finals if row.variant_key == variant.key]
            cells = [
                rob.DomainAssessment(
                    # A plain UUID: the driver's own subclass is not one to app.rob.
                    record_id=uuid.UUID(int=row.record_id.int),
                    tool_key=template.key,
                    variant_key=variant.key,
                    domain_key=domain.key,
                    axis_key=axis.key,
                    judgement=row.judgements[domain.key][axis.key],
                )
                for row in cohort
                for domain in variant.domains
                for axis in domain.judgement_axes
            ]
            summaries = rob.summary(cells) if cells else ()
            variants.append(
                VariantSummary(
                    variant_key=variant.key,
                    variant_name=variant.name,
                    domains=[
                        DomainSummaryOut(
                            domain_key=item.domain_key,
                            domain_name=item.domain_name,
                            axis_key=item.axis_key,
                            axis_name=item.axis_name,
                            counts=[
                                JudgementCountOut(
                                    judgement=count.judgement, label=count.label, count=count.count
                                )
                                for count in item.counts
                            ],
                            total=item.total,
                        )
                        for item in summaries
                    ],
                    studies=[
                        StudyRow(
                            record_id=row.record_id,
                            label=labels[row.record_id],
                            cells={
                                f"{domain}.{axis}": judgement
                                for domain, judged in row.judgements.items()
                                for axis, judgement in judged.items()
                            },
                            overall=row.overall,
                        )
                        for row in cohort
                    ],
                )
            )
        return RobSummary(
            tool_key=template.key,
            tool_name=template.name,
            tool_version=template.version,
            variants=variants,
            awaiting_final=awaiting,
            own_only=own_only,
        )

    async def _included(self, access: ProjectAccess, record_id: uuid.UUID) -> Record:
        """Risk of bias is judged for studies included at full text."""
        record = await self._db.scalar(
            select(Record).where(
                Record.id == record_id,
                Record.project_id == access.project_id,
                Record.is_duplicate.is_(False),
            )
        )
        if record is None:
            raise NotFoundError("That record is not in this review.")
        if record.ft_final is not FullTextStatus.INCLUDED:
            raise ConflictError("Risk of bias is assessed for studies included at full text.")
        return record


def _study_label(authors: list[str], year: int | None, title: str | None) -> str:
    """ "Smith 2019", or the start of the title when there is no author."""
    if authors:
        first = authors[0].strip()
        surname = first.split(",")[0].strip() if "," in first else first.rsplit(" ", 1)[-1]
        return f"{surname} {year}" if year else surname
    return (title or "Untitled")[:40]


def _out(row: RobAssessment, assessor: str | None, me: uuid.UUID) -> AssessmentOut:
    return AssessmentOut(
        id=row.id,
        record_id=row.record_id,
        tool_key=row.tool_key,
        tool_version=row.tool_version,
        variant_key=row.variant_key,
        answers=row.answers,
        judgements=row.judgements,
        support=row.support,
        overall=row.overall,
        status=row.status,
        final=row.final,
        assessor=assessor,
        mine=row.user_id == me,
        updated_at=row.updated_at,
    )

"""AI suggestions (guide 8.11): ask the configured provider about one record, keep what it
said, and hand it back as advice. Off unless the instance has a provider and the review's
owner has opted in; a suggestion never records a decision.

Suggestions belong to the person who asked. Under blind mode nobody else sees them while
screening; the review's owners and admins can export them all for the methods section.
"""

import csv
import io
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.prompt import (
    PROMPT_VERSION,
    SCHEMA,
    Criterion,
    RecordText,
    ReviewContext,
    UnreadableAnswerError,
    parse_answer,
    system_prompt,
    user_message,
)
from app.llm.providers import Provider, ProviderError
from app.models import (
    CriterionKind,
    Decision,
    DecisionValue,
    LlmSuggestion,
    Record,
    ScreeningStage,
    User,
)
from app.models.setup import Criterion as CriterionRow
from app.schemas.llm import CriterionVerdictOut, SuggestionOut
from app.security.permissions import ProjectAccess
from app.services import audit
from app.services.audit import Actor
from app.services.blinding import screens, settings_of
from app.services.errors import DomainError, FeatureUnavailableError, NotFoundError
from app.services.screening import NotScreeningError
from app.spreadsheet import safe_cell


class LlmFailedError(DomainError):
    status = 502
    code = "llm_failed"
    message = "The AI provider could not give a suggestion."


class LlmService:
    def __init__(self, db: AsyncSession, provider: Provider | None) -> None:
        self._db = db
        self._provider = provider

    async def latest(
        self, access: ProjectAccess, record_id: uuid.UUID, stage: ScreeningStage
    ) -> SuggestionOut | None:
        """My most recent suggestion for this record, without asking again."""
        row = await self._db.scalar(
            select(LlmSuggestion)
            .where(
                LlmSuggestion.project_id == access.project_id,
                LlmSuggestion.record_id == record_id,
                LlmSuggestion.user_id == access.user.id,
                LlmSuggestion.stage == stage,
            )
            .order_by(LlmSuggestion.created_at.desc(), LlmSuggestion.id.desc())
            .limit(1)
        )
        return None if row is None else _out(row)

    def check_available(self, access: ProjectAccess, stage: ScreeningStage) -> Provider:
        if self._provider is None:
            raise FeatureUnavailableError("No AI provider is set up on this Winnow instance.")
        if not settings_of(access).llm_assist_enabled:
            raise FeatureUnavailableError(
                "AI suggestions are off for this review; its owner can turn them on."
            )
        if not screens(access, stage.value):
            raise NotScreeningError
        return self._provider

    async def suggest(
        self,
        access: ProjectAccess,
        record_id: uuid.UUID,
        stage: ScreeningStage,
        actor: Actor,
    ) -> SuggestionOut:
        """Ask the provider now, and keep the answer."""
        provider = self.check_available(access, stage)
        record = await self._db.scalar(
            select(Record).where(
                Record.id == record_id,
                Record.project_id == access.project_id,
                Record.is_duplicate.is_(False),
            )
        )
        if record is None:
            raise NotFoundError("That record is not in this review.")
        rows = list(
            await self._db.scalars(
                select(CriterionRow)
                .where(CriterionRow.project_id == access.project_id)
                .order_by(CriterionRow.kind, CriterionRow.position, CriterionRow.id)
            )
        )
        numbered = {index + 1: row for index, row in enumerate(rows)}
        context = _context(access, numbered)
        text = RecordText(
            title=record.title,
            abstract=record.abstract,
            keywords=tuple(record.keywords or ()),
            year=record.year,
            journal=record.journal,
            publication_type=tuple(record.publication_type or ()),
        )
        try:
            raw = await provider.complete(
                system_prompt(context), user_message(context, text), SCHEMA
            )
            answer = parse_answer(raw, context.criteria)
        except ProviderError as error:
            raise LlmFailedError(str(error)) from error
        except UnreadableAnswerError as error:
            raise LlmFailedError("The AI provider's answer could not be read.") from error

        row = LlmSuggestion(
            project_id=access.project_id,
            record_id=record.id,
            user_id=access.user.id,
            stage=stage,
            provider=provider.name,
            model=provider.model,
            prompt_version=PROMPT_VERSION,
            decision=DecisionValue(answer.decision),
            confidence=answer.confidence,
            criteria=[
                {
                    "criterion_id": str(numbered[verdict.criterion].id),
                    "kind": numbered[verdict.criterion].kind.value,
                    "text": numbered[verdict.criterion].text,
                    "verdict": verdict.verdict,
                }
                for verdict in answer.criteria
            ],
            rationale=answer.rationale,
            created_at=datetime.now(UTC),
        )
        self._db.add(row)
        audit.record(
            self._db,
            "llm.suggested",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record.id,
            after={"stage": stage.value, "provider": row.provider, "model": row.model},
        )
        await self._db.commit()
        return _out(row)

    async def export_csv(self, access: ProjectAccess) -> str:
        """Every suggestion in the review, with the asker's own decision beside it, for
        reporting the use of AI in the methods (guide 8.11)."""
        mine = (
            select(Decision.decision)
            .where(
                Decision.record_id == LlmSuggestion.record_id,
                Decision.user_id == LlmSuggestion.user_id,
                Decision.stage == LlmSuggestion.stage,
            )
            .scalar_subquery()
        )
        rows = await self._db.execute(
            select(LlmSuggestion, Record.title, Record.doi, Record.pmid, User.name, mine)
            .join(Record, Record.id == LlmSuggestion.record_id)
            .join(User, User.id == LlmSuggestion.user_id)
            .where(LlmSuggestion.project_id == access.project_id)
            .order_by(LlmSuggestion.created_at, LlmSuggestion.id)
        )
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            [
                "asked_at",
                "stage",
                "reviewer",
                "title",
                "doi",
                "pmid",
                "provider",
                "model",
                "prompt_version",
                "suggested",
                "confidence",
                "criteria",
                "rationale",
                "reviewer_decision",
            ]
        )
        for suggestion, title, doi, pmid, name, decision in rows:
            verdicts = "; ".join(
                f"{item['text']}: {item['verdict'].replace('_', ' ')}"
                for item in suggestion.criteria
            )
            writer.writerow(
                [
                    safe_cell(value)
                    for value in (
                        suggestion.created_at.isoformat(),
                        suggestion.stage.value,
                        name,
                        title,
                        doi,
                        pmid,
                        suggestion.provider,
                        suggestion.model,
                        suggestion.prompt_version,
                        suggestion.decision.value,
                        f"{suggestion.confidence:.2f}",
                        verdicts,
                        suggestion.rationale,
                        decision.value if decision is not None else "",
                    )
                ]
            )
        return out.getvalue()


def _context(access: ProjectAccess, numbered: dict[int, CriterionRow]) -> ReviewContext:
    project = access.project
    pico = {key: value for key, value in (project.pico or {}).items() if isinstance(value, str)}
    return ReviewContext(
        review_type=project.review_type.value,
        title=project.title,
        research_question=project.research_question,
        pico=pico,
        criteria=tuple(
            Criterion(
                number=number,
                kind="inclusion" if row.kind is CriterionKind.INCLUSION else "exclusion",
                text=row.text,
            )
            for number, row in numbered.items()
        ),
    )


def _out(row: LlmSuggestion) -> SuggestionOut:
    return SuggestionOut(
        id=row.id,
        record_id=row.record_id,
        stage=row.stage,
        decision=row.decision,
        confidence=row.confidence,
        criteria=[CriterionVerdictOut.model_validate(item) for item in row.criteria],
        rationale=row.rationale,
        provider=row.provider,
        model=row.model,
        created_at=row.created_at,
    )

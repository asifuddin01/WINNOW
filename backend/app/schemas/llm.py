"""AI suggestions (guide 8.11): advice for one person about one record, never a decision."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models import DecisionValue, ScreeningStage


class CriterionVerdictOut(BaseModel):
    criterion_id: uuid.UUID
    kind: Literal["inclusion", "exclusion"]
    text: str
    verdict: Literal["met", "not_met", "unclear"]


class SuggestionOut(BaseModel):
    id: uuid.UUID
    record_id: uuid.UUID
    stage: ScreeningStage
    decision: DecisionValue
    confidence: float
    criteria: list[CriterionVerdictOut]
    rationale: str
    provider: str
    model: str
    created_at: datetime


class MaybeSuggestion(BaseModel):
    """My latest suggestion for a record, if I have asked for one."""

    suggestion: SuggestionOut | None

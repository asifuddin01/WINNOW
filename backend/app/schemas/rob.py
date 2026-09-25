"""Risk of bias (guide 8.13): the tools, one person's assessment, and the review's summary."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models import RobStatus

Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
Support = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5_000)]


class ChoiceOut(BaseModel):
    key: str
    label: str


class QuestionOut(BaseModel):
    key: str
    prompt: str
    answers: list[str]


class AxisOut(BaseModel):
    key: str
    name: str
    judgements: list[ChoiceOut]


class DomainOut(BaseModel):
    key: str
    name: str
    questions: list[QuestionOut]
    axes: list[AxisOut]


class VariantOut(BaseModel):
    key: str
    name: str
    domains: list[DomainOut]


class ToolOut(BaseModel):
    key: str
    name: str
    version: str
    source_url: str
    note: str
    variants: list[VariantOut]


class AssessmentIn(BaseModel):
    tool_key: Key
    variant_key: Key
    answers: dict[Key, dict[Key, Key]] = Field(default_factory=dict)
    judgements: dict[Key, dict[Key, Key]] = Field(default_factory=dict)
    support: dict[Key, Support] = Field(default_factory=dict)
    overall: Key | None = None
    # A draft may be partial; submitting needs a judgement on every domain and axis.
    status: RobStatus = RobStatus.DRAFT


class AssessmentOut(BaseModel):
    id: uuid.UUID
    record_id: uuid.UUID
    tool_key: str
    tool_version: str
    variant_key: str
    answers: dict[str, dict[str, str]]
    judgements: dict[str, dict[str, str]]
    support: dict[str, str]
    overall: str | None
    status: RobStatus
    final: bool
    assessor: str | None
    mine: bool
    updated_at: datetime


class RecordRob(BaseModel):
    record_id: uuid.UUID
    title: str | None
    assessments: list[AssessmentOut]


class JudgementCountOut(BaseModel):
    judgement: str
    label: str
    count: int


class DomainSummaryOut(BaseModel):
    domain_key: str
    domain_name: str
    axis_key: str
    axis_name: str
    counts: list[JudgementCountOut]
    total: int


class StudyRow(BaseModel):
    """One row of the traffic-light table."""

    record_id: uuid.UUID
    label: str
    # {"domain.axis": judgement}
    cells: dict[str, str]
    overall: str | None


class VariantSummary(BaseModel):
    variant_key: str
    variant_name: str
    domains: list[DomainSummaryOut]
    studies: list[StudyRow]


class RobSummary(BaseModel):
    tool_key: str
    tool_name: str
    tool_version: str
    variants: list[VariantSummary]
    # Records several people assessed, none of whose assessments is marked final yet.
    awaiting_final: list[uuid.UUID]
    # Blind mode: only the viewer's own assessments were summarised.
    own_only: bool


class FinalIn(BaseModel):
    assessment_id: uuid.UUID


PlotKind = Literal["traffic-light", "summary"]

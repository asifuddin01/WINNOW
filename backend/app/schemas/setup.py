"""Request and response bodies for criteria, keywords, exclusion reasons and labels."""

import uuid

from pydantic import BaseModel, Field

from app.models import CriterionKind, KeywordKind, ReasonStage
from app.schemas.common import Color, CriterionText, Name, Term


class CriterionCreate(BaseModel):
    kind: CriterionKind
    text: CriterionText


class CriterionUpdate(BaseModel):
    kind: CriterionKind | None = None
    text: CriterionText | None = None
    # Zero-based; a position past the end moves the item to the end.
    position: int | None = Field(default=None, ge=0)


class CriterionOut(BaseModel):
    id: uuid.UUID
    kind: CriterionKind
    text: str
    position: int


class KeywordGroupCreate(BaseModel):
    name: Name
    color: Color = "amber"
    kind: KeywordKind = KeywordKind.INCLUDE


class KeywordGroupUpdate(BaseModel):
    name: Name | None = None
    color: Color | None = None
    kind: KeywordKind | None = None


class KeywordOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    term: str
    is_regex: bool
    whole_word: bool


class KeywordGroupOut(BaseModel):
    id: uuid.UUID
    name: str
    color: Color
    kind: KeywordKind
    keywords: list[KeywordOut]


class KeywordsCreate(BaseModel):
    """Add several terms to a group at once; terms it already has are skipped."""

    group_id: uuid.UUID
    terms: list[Term] = Field(min_length=1, max_length=100)
    is_regex: bool = False
    whole_word: bool = True


class KeywordUpdate(BaseModel):
    term: Term | None = None
    is_regex: bool | None = None
    whole_word: bool | None = None


class ReasonCreate(BaseModel):
    label: Name
    stage: ReasonStage = ReasonStage.BOTH


class ReasonUpdate(BaseModel):
    label: Name | None = None
    stage: ReasonStage | None = None
    # Zero-based; a position past the end moves the item to the end.
    position: int | None = Field(default=None, ge=0)


class ReasonOut(BaseModel):
    id: uuid.UUID
    label: str
    stage: ReasonStage
    position: int


class LabelCreate(BaseModel):
    name: Name
    color: Color = "blue"


class LabelUpdate(BaseModel):
    name: Name | None = None
    color: Color | None = None


class LabelOut(BaseModel):
    id: uuid.UUID
    name: str
    color: Color

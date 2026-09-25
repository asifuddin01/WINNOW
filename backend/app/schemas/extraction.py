"""Data extraction (guide 8.12): forms, entries, consensus."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models import EntryStatus

FormName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class FormIn(BaseModel):
    name: FormName
    # app.extraction's schema: {"fields": [...]}. Checked field by field by the service.
    schema_: dict[str, Any] = Field(default_factory=lambda: {"fields": []}, alias="schema")
    dual: bool = False


class FormPatch(BaseModel):
    """Only a draft version can change; a published one is locked."""

    name: FormName | None = None
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    dual: bool | None = None


class FormOut(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    name: str
    version: int
    schema_: dict[str, Any] = Field(serialization_alias="schema")
    dual: bool
    published: bool
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # How many people's entries use this version (drafts included).
    entries: int
    # The newest version of its form.
    latest: bool


class EntryIn(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    # A draft may be partial; submitting checks every required field.
    status: Literal["draft", "submitted"] = "draft"


class EntryOut(BaseModel):
    id: uuid.UUID
    record_id: uuid.UUID
    form_id: uuid.UUID
    data: dict[str, Any]
    status: EntryStatus
    extractor: str | None
    mine: bool
    updated_at: datetime


class ConsensusOut(BaseModel):
    data: dict[str, Any]
    resolved_by: str | None
    updated_at: datetime


class RecordExtraction(BaseModel):
    """A study's extraction with one form version: mine, and others' unless blind."""

    record_id: uuid.UUID
    title: str | None
    label: str
    entries: list[EntryOut]
    consensus: ConsensusOut | None


class DifferenceOut(BaseModel):
    path: str
    label: str
    # One value per entry, in the order of `entries`.
    values: list[Any]


class ConsensusView(BaseModel):
    record_id: uuid.UUID
    title: str | None
    label: str
    entries: list[EntryOut]
    differences: list[DifferenceOut]
    # Where every submitted entry agrees: the consensus to start from.
    agreed: dict[str, Any]
    consensus: ConsensusOut | None


class ConsensusIn(BaseModel):
    data: dict[str, Any]


class StudyExtraction(BaseModel):
    record_id: uuid.UUID
    label: str
    title: str | None
    mine: Literal["none", "draft", "submitted", "verified"]
    # Unless blind mode hides others' work.
    submitted: int | None
    consensus: bool | None

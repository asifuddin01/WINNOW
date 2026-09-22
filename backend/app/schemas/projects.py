"""Request and response bodies for projects, members and invitations."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import ProjectRole, ProjectStatus, ReviewType, ScreeningStage
from app.schemas.common import OptionalLongText, OptionalPicoText, Title
from app.security.permissions import Capability

# --- Settings (guide 6.2) --------------------------------------------------------------


class StoppingRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["none", "consecutive_excludes"] = "consecutive_excludes"
    n: int = Field(default=200, ge=10, le=100_000)


class ProjectSettings(BaseModel):
    """How screening runs. Stored as JSON; defaults fill keys added in later versions."""

    model_config = ConfigDict(extra="forbid")

    blind_mode: bool = True
    reviewers_per_record_ta: int = Field(default=2, ge=1, le=5)
    reviewers_per_record_ft: int = Field(default=2, ge=1, le=5)
    # "include": a maybe moves on like an include. "maybe": it stays maybe for the team.
    maybe_counts_as: Literal["include", "maybe"] = "include"
    require_reason_on_exclude_ta: bool = False
    require_reason_on_exclude_ft: bool = True
    ranking_enabled: bool = True
    llm_assist_enabled: bool = False
    stopping_rule: StoppingRule = StoppingRule()
    # "all": every reviewer screens every record. "split": records are shared out so each
    # gets the required number of reviewers.
    assignment: Literal["all", "split"] = "all"
    highlight_keywords: bool = True


class ProjectSettingsPatch(BaseModel):
    """Only the settings to change."""

    model_config = ConfigDict(extra="forbid")

    blind_mode: bool | None = None
    reviewers_per_record_ta: int | None = Field(default=None, ge=1, le=5)
    reviewers_per_record_ft: int | None = Field(default=None, ge=1, le=5)
    maybe_counts_as: Literal["include", "maybe"] | None = None
    require_reason_on_exclude_ta: bool | None = None
    require_reason_on_exclude_ft: bool | None = None
    ranking_enabled: bool | None = None
    llm_assist_enabled: bool | None = None
    stopping_rule: StoppingRule | None = None
    assignment: Literal["all", "split"] | None = None
    highlight_keywords: bool | None = None


# --- Projects --------------------------------------------------------------------------


class Pico(BaseModel):
    population: OptionalPicoText = None
    intervention: OptionalPicoText = None
    comparator: OptionalPicoText = None
    outcome: OptionalPicoText = None

    def is_empty(self) -> bool:
        return not any(self.model_dump().values())


class ProjectCreate(BaseModel):
    title: Title
    review_type: ReviewType = ReviewType.SYSTEMATIC
    description: OptionalLongText = None
    research_question: OptionalLongText = None
    pico: Pico | None = None


# Fields a PATCH may leave out but never set to null.
_REQUIRED_WHEN_SENT = ("title", "review_type", "status", "settings")


class ProjectUpdate(BaseModel):
    """Send only what changes. Optional text sent as "" or null is cleared."""

    title: Title | None = None
    review_type: ReviewType | None = None
    description: OptionalLongText = None
    research_question: OptionalLongText = None
    pico: Pico | None = None
    status: ProjectStatus | None = None
    settings: ProjectSettingsPatch | None = None

    @model_validator(mode="after")
    def _no_nulls_for_required(self) -> "ProjectUpdate":
        for field in _REQUIRED_WHEN_SENT:
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be empty")
        return self


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str
    # Shown to people who manage members; others see names only.
    email: str | None = None


class MembershipOut(BaseModel):
    role: ProjectRole
    can_resolve_conflicts: bool
    stages: list[ScreeningStage]
    keep_blind: bool


class ProjectOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    review_type: ReviewType
    research_question: str | None
    pico: Pico | None
    status: ProjectStatus
    settings: ProjectSettings
    owner: PersonOut
    membership: MembershipOut
    # What the caller may do here (guide 7). The API enforces it; the UI only reads it.
    permissions: list[Capability]
    member_count: int
    created_at: datetime
    updated_at: datetime


class ProjectSummary(BaseModel):
    id: uuid.UUID
    title: str
    review_type: ReviewType
    status: ProjectStatus
    role: ProjectRole
    member_count: int
    last_activity_at: datetime
    created_at: datetime


class ProjectPage(BaseModel):
    items: list[ProjectSummary]
    next_cursor: str | None


class TransferRequest(BaseModel):
    user_id: uuid.UUID


class DuplicateSetupRequest(BaseModel):
    title: Title


# --- Members ---------------------------------------------------------------------------

AssignableRole = Literal["admin", "reviewer", "viewer"]


class MemberOut(BaseModel):
    user: PersonOut
    role: ProjectRole
    can_resolve_conflicts: bool
    stages: list[ScreeningStage]
    joined_at: datetime


class MemberPage(BaseModel):
    items: list[MemberOut]
    next_cursor: str | None


class MemberUpdate(BaseModel):
    role: AssignableRole | None = None
    can_resolve_conflicts: bool | None = None
    stages: list[ScreeningStage] | None = Field(default=None, max_length=2)

    @model_validator(mode="after")
    def _stages_are_distinct(self) -> "MemberUpdate":
        if self.stages is not None and len(set(self.stages)) != len(self.stages):
            raise ValueError("list each stage once")
        return self


class MembershipUpdate(BaseModel):
    keep_blind: bool


# --- Invitations -----------------------------------------------------------------------


class InviteCreate(BaseModel):
    email: EmailStr = Field(max_length=254)
    role: AssignableRole = "reviewer"


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    role: ProjectRole
    invited_by: str | None
    created_at: datetime
    expires_at: datetime
    expired: bool


class InviteCreated(InviteOut):
    # The link, shown once, for sharing another way when this instance sends no email.
    # It only works for someone signed in with the invited address.
    link: str
    emailed: bool


class InvitePreview(BaseModel):
    project_title: str
    inviter_name: str | None
    role: ProjectRole
    email_hint: str
    expires_at: datetime
    state: Literal["pending", "expired", "accepted"]


class InviteAccepted(BaseModel):
    project_id: uuid.UUID


def settings_from_json(stored: dict[str, Any]) -> ProjectSettings:
    """Stored settings with defaults for any key added since they were saved; unknown
    keys from older versions are dropped rather than rejected."""
    known = {key: value for key, value in stored.items() if key in ProjectSettings.model_fields}
    return ProjectSettings.model_validate(known)

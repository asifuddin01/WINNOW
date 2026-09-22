"""SQLAlchemy models, one module per aggregate. Import every model here so Alembic sees it."""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.project import (
    ALL_STAGES,
    Project,
    ProjectInvite,
    ProjectMember,
    ProjectRole,
    ProjectStatus,
    ReviewType,
    ScreeningStage,
)
from app.models.setup import (
    Criterion,
    CriterionKind,
    ExclusionReason,
    Keyword,
    KeywordGroup,
    KeywordKind,
    Label,
    ReasonStage,
)
from app.models.user import NO_PASSWORD, EmailToken, EmailTokenPurpose, User, UserIdentity

__all__ = [
    "ALL_STAGES",
    "NO_PASSWORD",
    "AuditLog",
    "Base",
    "Criterion",
    "CriterionKind",
    "EmailToken",
    "EmailTokenPurpose",
    "ExclusionReason",
    "Keyword",
    "KeywordGroup",
    "KeywordKind",
    "Label",
    "Project",
    "ProjectInvite",
    "ProjectMember",
    "ProjectRole",
    "ProjectStatus",
    "ReasonStage",
    "ReviewType",
    "ScreeningStage",
    "User",
    "UserIdentity",
]

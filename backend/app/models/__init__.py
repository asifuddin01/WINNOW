"""SQLAlchemy models, one module per aggregate. Import every model here so Alembic sees it."""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.dedup import ClusterStatus, DupCluster, DupClusterMember
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
from app.models.ranking import RankingModel, RecordScore
from app.models.record import (
    COPY_COLUMNS,
    FileFormat,
    FullTextStatus,
    ImportBatch,
    ImportStatus,
    Record,
    TitleAbstractStatus,
)
from app.models.screening import (
    ConflictResolution,
    Decision,
    DecisionValue,
    FinalDecision,
    Note,
    NoteVisibility,
    RecordLabel,
    ResolutionSource,
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
    "COPY_COLUMNS",
    "NO_PASSWORD",
    "AuditLog",
    "Base",
    "ClusterStatus",
    "ConflictResolution",
    "Criterion",
    "CriterionKind",
    "Decision",
    "DecisionValue",
    "DupCluster",
    "DupClusterMember",
    "EmailToken",
    "EmailTokenPurpose",
    "ExclusionReason",
    "FileFormat",
    "FinalDecision",
    "FullTextStatus",
    "ImportBatch",
    "ImportStatus",
    "Keyword",
    "KeywordGroup",
    "KeywordKind",
    "Label",
    "Note",
    "NoteVisibility",
    "Project",
    "ProjectInvite",
    "ProjectMember",
    "ProjectRole",
    "ProjectStatus",
    "RankingModel",
    "ReasonStage",
    "Record",
    "RecordLabel",
    "RecordScore",
    "ResolutionSource",
    "ReviewType",
    "ScreeningStage",
    "TitleAbstractStatus",
    "User",
    "UserIdentity",
]

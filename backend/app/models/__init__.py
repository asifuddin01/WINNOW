"""SQLAlchemy models, one module per aggregate. Import every model here so Alembic sees it."""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.dedup import ClusterStatus, DupCluster, DupClusterMember
from app.models.export import ExportFormat, ExportJob, ExportKind, JobStatus, RestoreJob
from app.models.extraction import (
    EntryStatus,
    ExtractionConsensus,
    ExtractionEntry,
    ExtractionForm,
)
from app.models.fulltext import (
    BatchStatus,
    Fulltext,
    FulltextBatch,
    FulltextSource,
    PdfAnnotation,
    ScanStatus,
    UnretrievableRecord,
)
from app.models.llm import LlmSuggestion
from app.models.notification import Notification, NotificationKind
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
from app.models.reporting import PrismaManual
from app.models.rob import RobAssessment, RobStatus
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
    "BatchStatus",
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
    "EntryStatus",
    "ExclusionReason",
    "ExportFormat",
    "ExportJob",
    "ExportKind",
    "ExtractionConsensus",
    "ExtractionEntry",
    "ExtractionForm",
    "FileFormat",
    "FinalDecision",
    "FullTextStatus",
    "Fulltext",
    "FulltextBatch",
    "FulltextSource",
    "ImportBatch",
    "ImportStatus",
    "JobStatus",
    "Keyword",
    "KeywordGroup",
    "KeywordKind",
    "Label",
    "LlmSuggestion",
    "Note",
    "NoteVisibility",
    "Notification",
    "NotificationKind",
    "PdfAnnotation",
    "PrismaManual",
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
    "RestoreJob",
    "ReviewType",
    "RobAssessment",
    "RobStatus",
    "ScanStatus",
    "ScreeningStage",
    "TitleAbstractStatus",
    "UnretrievableRecord",
    "User",
    "UserIdentity",
]

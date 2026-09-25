"""The backup format (guide 8.16): which tables a review's backup holds, in what order,
and how their rows become JSON and back.

A backup is a ZIP: `manifest.json`, one JSON-lines file per table under `tables/`, the
people referred to in `people.json`, and the files (search exports, cleared PDFs) under
`files/`. Rows are written from their columns, so a column added later is carried
without a change here; they are read back typed by the same columns, and a value of the
wrong type, or a column Winnow does not have, stops the restore.

Every id is replaced on restore: a backup can be restored twice, or next to its source,
and can never write into another review.
"""

import enum
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import ARRAY, Boolean, Date, DateTime, Enum, Float, Integer, Table
from sqlalchemy.dialects.postgresql import INET, JSONB, TSVECTOR
from sqlalchemy.types import TypeEngine

from app.models import (
    AuditLog,
    ConflictResolution,
    Criterion,
    Decision,
    DupCluster,
    DupClusterMember,
    ExclusionReason,
    ExtractionConsensus,
    ExtractionEntry,
    ExtractionForm,
    Fulltext,
    ImportBatch,
    Keyword,
    KeywordGroup,
    Label,
    LlmSuggestion,
    Note,
    PdfAnnotation,
    PrismaManual,
    Record,
    RecordLabel,
    RobAssessment,
    UnretrievableRecord,
)

FORMAT = "winnow-backup"
VERSION = 1


@dataclass(frozen=True)
class TableSpec:
    """One table in a backup.

    `refs` maps a column to the id space it points into ("project", "people", or another
    table's name); `id_arrays` the same for arrays of ids. `own_id` is False for tables
    keyed by another row (a record's "not retrievable" mark).
    """

    table: Table
    refs: dict[str, str] = field(default_factory=dict)
    id_arrays: dict[str, str] = field(default_factory=dict)
    own_id: bool = True

    @property
    def name(self) -> str:
        return self.table.name


def table_of(model: Any) -> Table:
    table: Table = model.__table__
    return table


# In the order they are restored: every table after those it points to.
TABLES: tuple[TableSpec, ...] = (
    TableSpec(table_of(Criterion), {"project_id": "project"}),
    TableSpec(table_of(KeywordGroup), {"project_id": "project"}),
    TableSpec(table_of(Keyword), {"group_id": "keyword_groups"}),
    TableSpec(table_of(ExclusionReason), {"project_id": "project"}),
    TableSpec(table_of(Label), {"project_id": "project"}),
    TableSpec(table_of(ImportBatch), {"project_id": "project", "created_by": "people"}),
    # duplicate_of points into records themselves; it is set once every record exists.
    TableSpec(
        table_of(Record),
        {"project_id": "project", "import_batch_id": "import_batches", "duplicate_of": "records"},
    ),
    TableSpec(table_of(DupCluster), {"project_id": "project", "resolved_by": "people"}),
    TableSpec(table_of(DupClusterMember), {"cluster_id": "dup_clusters", "record_id": "records"}),
    TableSpec(
        table_of(Decision),
        {"project_id": "project", "record_id": "records", "user_id": "people"},
        {"reason_ids": "exclusion_reasons"},
    ),
    TableSpec(
        table_of(ConflictResolution),
        {"project_id": "project", "record_id": "records", "resolved_by": "people"},
        {"reason_ids": "exclusion_reasons"},
    ),
    TableSpec(
        table_of(Note), {"project_id": "project", "record_id": "records", "user_id": "people"}
    ),
    TableSpec(
        table_of(RecordLabel),
        {"record_id": "records", "label_id": "labels", "user_id": "people"},
        own_id=False,
    ),
    TableSpec(
        table_of(LlmSuggestion),
        {"project_id": "project", "record_id": "records", "user_id": "people"},
    ),
    TableSpec(
        table_of(Fulltext),
        {"project_id": "project", "record_id": "records", "uploaded_by": "people"},
    ),
    TableSpec(
        table_of(PdfAnnotation),
        {"project_id": "project", "fulltext_id": "fulltexts", "user_id": "people"},
    ),
    TableSpec(
        table_of(UnretrievableRecord),
        {"record_id": "records", "project_id": "project", "marked_by": "people"},
        own_id=False,
    ),
    TableSpec(
        table_of(PrismaManual), {"project_id": "project", "updated_by": "people"}, own_id=False
    ),
    TableSpec(
        table_of(RobAssessment),
        {"project_id": "project", "record_id": "records", "user_id": "people"},
    ),
    # A form's versions share a family: the first version's id, so it maps like a row.
    TableSpec(
        table_of(ExtractionForm),
        {"project_id": "project", "family_id": "extraction_forms", "created_by": "people"},
    ),
    TableSpec(
        table_of(ExtractionEntry),
        {
            "project_id": "project",
            "form_id": "extraction_forms",
            "record_id": "records",
            "user_id": "people",
        },
    ),
    TableSpec(
        table_of(ExtractionConsensus),
        {
            "project_id": "project",
            "form_id": "extraction_forms",
            "record_id": "records",
            "resolved_by": "people",
        },
    ),
    # The review's history. Its ids are the log's own, so they are not carried.
    TableSpec(table_of(AuditLog), {"project_id": "project", "user_id": "people"}, own_id=False),
)
BY_NAME = {spec.name: spec for spec in TABLES}


def columns(table: Table) -> list[str]:
    """The columns a backup carries: all but those the database works out itself."""
    return [
        column.name
        for column in table.columns
        if column.computed is None and not isinstance(column.type, TSVECTOR)
    ]


def to_json(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, IPv4Address | IPv6Address):
        return str(value)
    if isinstance(value, list | tuple):
        return [to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_json(item) for key, item in value.items()}
    raise TypeError(f"{type(value).__name__} cannot go in a backup")


class BackupFormatError(Exception):
    """The backup does not hold what Winnow expects; the message says where."""


def from_json(type_: TypeEngine[Any], value: Any, where: str) -> Any:
    """A JSON value as the column's own type; anything that does not fit is refused."""
    if value is None:
        return None
    try:
        if isinstance(type_, JSONB):
            return value
        if isinstance(type_, ARRAY):
            if not isinstance(value, list):
                raise BackupFormatError(f"{where} should be a list")
            return [from_json(type_.item_type, item, where) for item in value]
        if isinstance(type_, Enum) and type_.enum_class is not None:
            return type_.enum_class(value)
        if isinstance(type_, Boolean):
            if not isinstance(value, bool):
                raise BackupFormatError(f"{where} should be true or false")
            return value
        if isinstance(type_, Integer):
            if isinstance(value, bool) or not isinstance(value, int):
                raise BackupFormatError(f"{where} should be a whole number")
            return value
        if isinstance(type_, Float):
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise BackupFormatError(f"{where} should be a number")
            return float(value)
        if isinstance(type_, DateTime):
            return datetime.fromisoformat(value)
        if isinstance(type_, Date):
            return date.fromisoformat(value)
        if isinstance(type_, INET):
            return str(value)
        if type_.python_type is uuid.UUID:
            return uuid.UUID(value)
        if not isinstance(value, str):
            raise BackupFormatError(f"{where} should be text")
        return value
    except BackupFormatError:
        raise
    except (TypeError, ValueError, NotImplementedError) as error:
        raise BackupFormatError(f"{where} is not valid: {error}") from error

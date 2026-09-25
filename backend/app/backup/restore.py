"""Restoring a backup as a new review (guide 8.16: "Import project backup to restore on
another Winnow instance").

The backup is untrusted input. The ZIP is checked before anything is read (the same
guards as ZIPs of PDFs); only the tables and columns Winnow knows are accepted, every
value is typed by its column, every id is replaced and every reference must point at a
row of the same backup. The review belongs to whoever restores it and has no other
members: people in the backup are matched to accounts here by email, or kept as
placeholders that cannot sign in (an address under `.invalid`, which no mail reaches),
so a backup can neither create a real account nor give anyone access. PDFs are scanned
again before they can be opened.
"""

import json
import uuid
import zipfile
from collections import defaultdict
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from pydantic import ValidationError
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.backup.spec import (
    FORMAT,
    TABLES,
    VERSION,
    BackupFormatError,
    TableSpec,
    columns,
    from_json,
    table_of,
)
from app.fulltext import zipcheck
from app.models import (
    ALL_STAGES,
    NO_PASSWORD,
    Fulltext,
    Project,
    ProjectMember,
    ProjectRole,
    Record,
    ScanStatus,
    User,
)
from app.models.base import uuid7
from app.schemas.projects import ProjectCreate, settings_from_json
from app.storage import Storage, new_key

INSERT_BATCH = 1_000
MAX_LINE = 64 * 1024 * 1024  # one row; a record's raw export data is the largest
MAX_ENTRIES = 50_000
# JSON lines of similar records pack tightly (tens to one), a bomb by a thousand to one.
MAX_RATIO = 200
DESCRIBED = ("title", "review_type", "description", "research_question", "pico")
FILE_CHUNK = 1024 * 1024


async def restore_backup(
    db: AsyncSession,
    storage: Storage,
    user: User,
    archive_path: Path,
    *,
    max_bytes: int,
    scanning: bool,
) -> tuple[uuid.UUID, dict[str, int]]:
    """The new review's id and how many rows of each kind were restored. Not committed."""
    try:
        entries = zipcheck.inspect(
            archive_path,
            max_entry_bytes=max_bytes,
            max_entries=MAX_ENTRIES,
            max_total_bytes=max_bytes * 10,
            max_ratio=MAX_RATIO,
        )
    except zipcheck.ZipRejectedError as error:
        raise BackupFormatError(str(error)) from error
    names = {entry.path for entry in entries}
    with zipfile.ZipFile(archive_path) as archive:
        manifest = _json(archive, "manifest.json", names)
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
            raise BackupFormatError("This is not a Winnow project backup.")
        if manifest.get("version") != VERSION:
            raise BackupFormatError(
                f"This backup is format version {manifest.get('version')!r}; this Winnow reads "
                f"version {VERSION}."
            )
        restorer = _Restorer(db, storage, archive, names, scanning)
        project_id = await restorer.project(_json(archive, "project.json", names), user)
        await restorer.people(_json(archive, "people.json", names), user)
        counts: dict[str, int] = {}
        for spec in TABLES:
            counts[spec.name] = await restorer.table(spec)
        await restorer.link_duplicates()
        expected = manifest.get("counts", {})
        for name, count in counts.items():
            if isinstance(expected, dict) and expected.get(name, count) != count:
                raise BackupFormatError(
                    f"The backup says it holds {expected[name]} rows of {name} but holds {count}."
                )
    return project_id, counts


def _json(archive: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name not in names:
        raise BackupFormatError(f"The backup has no {name}.")
    try:
        with archive.open(name) as handle:
            return json.loads(handle.read(MAX_LINE))
    except (ValueError, UnicodeDecodeError) as error:
        raise BackupFormatError(f"{name} is not valid JSON.") from error


class _Restorer:
    def __init__(
        self,
        db: AsyncSession,
        storage: Storage,
        archive: zipfile.ZipFile,
        names: set[str],
        scanning: bool,
    ) -> None:
        self._db = db
        self._storage = storage
        self._archive = archive
        self._names = names
        self._scanning = scanning
        # id space → old id → new id
        self.ids: dict[str, dict[uuid.UUID, uuid.UUID]] = defaultdict(dict)
        self._duplicates: list[tuple[uuid.UUID, uuid.UUID]] = []
        self._project_id: uuid.UUID | None = None

    async def project(self, data: Any, owner: User) -> uuid.UUID:
        """The review itself, read through the same rules as a review created here."""
        if not isinstance(data, dict):
            raise BackupFormatError("project.json should describe one review.")
        described = {name: data[name] for name in DESCRIBED if data.get(name) is not None}
        settings = data.get("settings") or {}
        if not isinstance(settings, dict):
            raise BackupFormatError("project.settings should be an object.")
        try:
            body = ProjectCreate.model_validate(described)
            chosen = settings_from_json(settings)
        except ValidationError as error:
            problem = error.errors()[0]
            where = ".".join(str(part) for part in problem["loc"]) or "settings"
            raise BackupFormatError(f"project.{where} is not valid: {problem['msg']}.") from error
        status = from_json(
            table_of(Project).c.status.type, data.get("status", "setup"), "project.status"
        )
        new = uuid7()
        self.ids["project"][_uuid(data.get("id"), "project.id")] = new
        self._project_id = new
        self._db.add(
            Project(
                id=new,
                owner_id=owner.id,
                title=f"{body.title[:280]} (restored)",
                review_type=body.review_type,
                description=body.description,
                research_question=body.research_question,
                pico=None if body.pico is None or body.pico.is_empty() else body.pico.model_dump(),
                status=status,
                settings=chosen.model_dump(mode="json"),
            )
        )
        self._db.add(
            ProjectMember(
                project_id=new,
                user_id=owner.id,
                role=ProjectRole.OWNER,
                stages=list(ALL_STAGES),
            )
        )
        await self._db.flush()
        return new

    async def people(self, data: Any, restorer: User) -> None:
        if not isinstance(data, list):
            raise BackupFormatError("people.json should be a list.")
        for person in data:
            if not isinstance(person, dict):
                raise BackupFormatError("people.json holds something that is not a person.")
            old = _uuid(person.get("id"), "people.id")
            email = person.get("email")
            name = person.get("name")
            if not isinstance(email, str) or not isinstance(name, str):
                raise BackupFormatError("Every person in people.json needs a name and an email.")
            if email.casefold() == restorer.email.casefold():
                self.ids["people"][old] = restorer.id
                continue
            existing = await self._db.scalar(
                select(User.id).where(User.email == email, User.deleted_at.is_(None))
            )
            if existing is not None:
                self.ids["people"][old] = existing
                continue
            placeholder = User(
                id=uuid7(),
                email=f"restored-{uuid.uuid4().hex}@restored.invalid",
                name=f"{name.strip()[:100]} (restored)",
                password_hash=NO_PASSWORD,
                deleted_at=datetime.now(UTC),
            )
            self._db.add(placeholder)
            self.ids["people"][old] = placeholder.id
        await self._db.flush()

    async def table(self, spec: TableSpec) -> int:
        allowed = set(columns(spec.table))
        count = 0
        batch: list[dict[str, Any]] = []
        async for raw in self._rows(spec):
            unknown = set(raw) - allowed
            if unknown:
                raise BackupFormatError(
                    f"{spec.name} has columns this Winnow does not know: {sorted(unknown)}."
                )
            row = {
                name: from_json(spec.table.c[name].type, value, f"{spec.name}.{name}")
                for name, value in raw.items()
            }
            await self._remap(spec, row)
            batch.append(row)
            count += 1
            if len(batch) >= INSERT_BATCH:
                await self._db.execute(insert(spec.table), batch)
                batch = []
        if batch:
            await self._db.execute(insert(spec.table), batch)
        return count

    async def _rows(self, spec: TableSpec) -> AsyncIterator[dict[str, Any]]:
        name = f"tables/{spec.name}.jsonl"
        if name not in self._names:
            return
        with self._archive.open(name) as handle:
            for number, line in enumerate(_lines(handle), start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except (ValueError, UnicodeDecodeError) as error:
                    raise BackupFormatError(f"{name}, line {number}, is not valid JSON.") from error
                if not isinstance(row, dict):
                    raise BackupFormatError(f"{name}, line {number}, is not a row.")
                yield row

    async def _remap(self, spec: TableSpec, row: dict[str, Any]) -> None:
        old: uuid.UUID | None = None
        if spec.own_id:
            old = row.get("id")
            if not isinstance(old, uuid.UUID):
                raise BackupFormatError(f"A row of {spec.name} has no id.")
            if old in self.ids[spec.name]:
                raise BackupFormatError(f"{spec.name} holds the id {old} twice.")
            new = uuid7()
            self.ids[spec.name][old] = new
            row["id"] = new
        else:
            row.pop("id", None)
        for column, target in spec.refs.items():
            value = row.get(column)
            if value is None:
                continue
            if spec.name == "records" and column == "duplicate_of":
                self._duplicates.append((row["id"], value))
                row[column] = None
                continue
            row[column] = self._lookup(target, value, f"{spec.name}.{column}")
        for column, target in spec.id_arrays.items():
            row[column] = [
                self._lookup(target, value, f"{spec.name}.{column}")
                for value in row.get(column) or []
            ]
        if spec.name == "audit_log" and row.get("entity_id") is not None:
            # History may name rows the backup does not hold (a deleted record): kept as is.
            row["entity_id"] = next(
                (
                    space[row["entity_id"]]
                    for space in self.ids.values()
                    if row["entity_id"] in space
                ),
                row["entity_id"],
            )
        if spec.name == "llm_suggestions":
            row["criteria"] = [self._criterion(item) for item in row.get("criteria") or []]
        if spec.name == "import_batches":
            row["file_key"] = await self._file(f"files/imports/{old}", "imports")
        if spec.name == "fulltexts":
            row["file_key"] = await self._file(f"files/pdfs/{old}.pdf", "fulltexts")
            # Scanned again here before anyone can open it.
            row["scan_status"] = ScanStatus.PENDING if self._scanning else ScanStatus.SKIPPED
            row["scan_signature"] = None
            row["scanned_at"] = None

    def _criterion(self, item: Any) -> Any:
        """An AI suggestion's verdict on a criterion names the criterion by id."""
        if not isinstance(item, dict) or not isinstance(item.get("criterion_id"), str):
            return item
        try:
            old = uuid.UUID(item["criterion_id"])
        except ValueError:
            return item
        new = self.ids["criteria"].get(old)
        return item if new is None else {**item, "criterion_id": str(new)}

    def _lookup(self, space: str, old: Any, where: str) -> uuid.UUID:
        if not isinstance(old, uuid.UUID):
            raise BackupFormatError(f"{where} should be an id.")
        new = self.ids[space].get(old)
        if new is None:
            raise BackupFormatError(f"{where} points at {old}, which the backup does not hold.")
        return new

    async def _file(self, name: str, prefix: str) -> str:
        key = new_key(prefix)
        if name not in self._names:
            if f"{name}.missing" in self._names or prefix == "imports":
                await self._storage.save(key, _nothing(), 1)
                return key
            raise BackupFormatError(f"The backup is missing {name}.")
        with self._archive.open(name) as handle:
            await self._storage.save(key, _read(handle), 10 * 1024**3)
        return key

    async def link_duplicates(self) -> None:
        for new, old_target in self._duplicates:
            target = self._lookup("records", old_target, "records.duplicate_of")
            await self._db.execute(
                update(Record).where(Record.id == new).values(duplicate_of=target)
            )


def _uuid(value: Any, where: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as error:
        raise BackupFormatError(f"{where} is not an id.") from error


def _lines(handle: IO[bytes]) -> Iterator[bytes]:
    while line := handle.readline(MAX_LINE + 1):
        if len(line) > MAX_LINE:
            raise BackupFormatError("A row in the backup is too large.")
        yield line


async def _read(handle: IO[bytes]) -> AsyncIterator[bytes]:
    while chunk := handle.read(FILE_CHUNK):
        yield chunk


async def _nothing() -> AsyncIterator[bytes]:
    empty: tuple[bytes, ...] = ()
    for chunk in empty:
        yield chunk


async def pending_scans(db: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    """The restored review's PDFs waiting for the scanner."""
    return list(
        await db.scalars(
            select(Fulltext.id).where(
                Fulltext.project_id == project_id, Fulltext.scan_status == ScanStatus.PENDING
            )
        )
    )

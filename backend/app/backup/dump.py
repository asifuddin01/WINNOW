"""Writing a review's full backup (guide 8.16): everything in the review, and its files.

Run in the worker for the review's owner (`app.workers.exports`). PDFs the virus scanner
has not cleared are left out, row and file: a backup never carries a quarantined file.
"""

import json
import os
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backup.spec import (
    BY_NAME,
    FORMAT,
    TABLES,
    VERSION,
    TableSpec,
    columns,
    table_of,
    to_json,
)
from app.models import Fulltext, Project, ProjectMember, ScanStatus, User
from app.security.permissions import ProjectAccess
from app.storage import Storage

READABLE = (ScanStatus.CLEAN, ScanStatus.SKIPPED)
BATCH = 2_000


def _scope(spec: TableSpec, project_id: uuid.UUID) -> Select[Any]:
    """The table's rows that belong to the review, directly or through their parent."""
    table = spec.table
    statement = select(*(table.c[name] for name in columns(table)))
    if "project_id" in table.c:
        statement = statement.where(table.c.project_id == project_id)
    else:
        column, parent_name = next(
            (column, target)
            for column, target in spec.refs.items()
            if target in BY_NAME and "project_id" in BY_NAME[target].table.c
        )
        parent = BY_NAME[parent_name].table
        statement = statement.where(
            table.c[column].in_(select(parent.c.id).where(parent.c.project_id == project_id))
        )
    if spec.name == "fulltexts":
        statement = statement.where(table.c.scan_status.in_(READABLE))
    if spec.name == "pdf_annotations":
        statement = statement.where(
            table.c.fulltext_id.in_(
                select(Fulltext.id).where(
                    Fulltext.project_id == project_id, Fulltext.scan_status.in_(READABLE)
                )
            )
        )
    order = table.c.id if "id" in table.c else next(iter(table.primary_key.columns))
    return statement.order_by(order)


async def write_backup(
    db: AsyncSession, storage: Storage, access: ProjectAccess
) -> tuple[Path, int]:
    """The backup, as a ZIP in a temporary file, and how many rows it holds."""
    project_id = access.project_id
    descriptor, name = tempfile.mkstemp(prefix="winnow-backup-", suffix=".zip")
    os.close(descriptor)
    path = Path(name)
    counts: dict[str, int] = {}
    people: set[uuid.UUID] = set()
    files: list[str] = []
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        project = await db.get(Project, project_id)
        if project is None:
            raise LookupError("the review is gone")
        people.add(project.owner_id)
        archive.writestr(
            "project.json",
            json.dumps(
                {name: to_json(getattr(project, name)) for name in columns(table_of(Project))}
            ),
        )
        for spec in TABLES:
            refs_to_people = [name for name, target in spec.refs.items() if target == "people"]
            count = 0
            with archive.open(f"tables/{spec.name}.jsonl", "w", force_zip64=True) as out:
                result = await db.stream(
                    _scope(spec, project_id).execution_options(yield_per=BATCH)
                )
                async for partition in result.partitions(BATCH):
                    lines = []
                    for row in partition:
                        values = {name: to_json(value) for name, value in row._mapping.items()}
                        for name in refs_to_people:
                            if values.get(name):
                                people.add(uuid.UUID(values[name]))
                        lines.append(json.dumps(values, ensure_ascii=False))
                        count += 1
                    if lines:
                        out.write(("\n".join(lines) + "\n").encode())
            counts[spec.name] = count
        # The files the rows point to: search exports and cleared PDFs.
        for batch_id, key in await db.execute(
            select(
                BY_NAME["import_batches"].table.c.id, BY_NAME["import_batches"].table.c.file_key
            ).where(BY_NAME["import_batches"].table.c.project_id == project_id)
        ):
            name = f"files/imports/{batch_id}"
            if await _copy(storage, key, archive, name):
                files.append(name)
        for fulltext_id, key in await db.execute(
            select(Fulltext.id, Fulltext.file_key).where(
                Fulltext.project_id == project_id, Fulltext.scan_status.in_(READABLE)
            )
        ):
            name = f"files/pdfs/{fulltext_id}.pdf"
            if await _copy(storage, key, archive, name):
                files.append(name)

        members = {
            member.user_id: member
            for member in await db.scalars(
                select(ProjectMember).where(ProjectMember.project_id == project_id)
            )
        }
        people |= set(members)
        archive.writestr(
            "people.json",
            json.dumps(
                [
                    {
                        "id": str(user.id),
                        "name": user.name,
                        "email": user.email,
                        "role": members[user.id].role.value if user.id in members else None,
                    }
                    for user in await db.scalars(select(User).where(User.id.in_(people)))
                ],
                ensure_ascii=False,
            ),
        )
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": FORMAT,
                    "version": VERSION,
                    "exported_at": datetime.now(UTC).isoformat(),
                    "project": {"id": str(project_id), "title": project.title},
                    "counts": counts,
                    "files": files,
                },
                ensure_ascii=False,
                indent=1,
            ),
        )
    return path, sum(counts.values())


async def _copy(storage: Storage, key: str, archive: zipfile.ZipFile, name: str) -> bool:
    """Copy a stored file into the backup; a file missing from storage is noted instead."""
    try:
        await storage.size(key)
    except FileNotFoundError:
        archive.writestr(f"{name}.missing", "")
        return False
    with archive.open(name, "w", force_zip64=True) as out:
        async for chunk in storage.iter_bytes(key):
            out.write(chunk)
    return True

"""Exports and backups (guide 8.16; Phase 8 acceptance: "backup from one instance restores
into another")."""

import csv
import io
import json
import uuid
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    NO_PASSWORD,
    AuditLog,
    Criterion,
    Decision,
    ExportJob,
    FileFormat,
    Fulltext,
    ImportBatch,
    ImportStatus,
    LlmSuggestion,
    Note,
    Project,
    Record,
    RecordLabel,
    RestoreJob,
    ScanStatus,
    User,
)
from app.models.base import uuid7
from app.parsers import bibtex, ris
from app.workers.exports import run_export, run_restore
from tests.auth_helpers import csrf
from tests.conftest import MemoryMailer
from tests.pdf_helpers import tiny_pdf
from tests.project_helpers import API, OWNER, REVIEWER, api, get, person, post
from tests.screening_helpers import decide, settings, team


async def export(db_app: FastAPI, client: AsyncClient, pid: str, **body: Any) -> dict[str, Any]:
    requested = await post(client, f"/projects/{pid}/exports", body)
    assert requested.status_code == 201, requested.text
    job = requested.json()
    status = await run_export(
        sessionmaker=db_app.state.sessionmaker,
        redis=db_app.state.redis,
        storage=db_app.state.storage,
        export_id=uuid.UUID(job["id"]),
    )
    finished: dict[str, Any] = (await get(client, f"/projects/{pid}/exports/{job['id']}")).json()
    assert status is not None, finished
    return finished


async def download(client: AsyncClient, pid: str, eid: str) -> bytes:
    response = await client.get(f"{API}/projects/{pid}/exports/{eid}/file")
    assert response.status_code == 200, response.text
    return response.content


async def test_records_export_as_csv_with_decisions_and_filters(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=4) as t:
        await settings(t.owner, t.pid, reviewers_per_record_ta=1)
        risky, second, *_ = t.records
        await db.execute(update(Record).where(Record.id == risky).values(title="=HYPERLINK(1)"))
        await db.commit()
        reasons = (await get(t.owner, f"/projects/{t.pid}/exclusion-reasons")).json()
        await decide(t.reviewer, t.pid, risky, "include")
        await decide(t.reviewer, t.pid, second, "exclude", reason_ids=[reasons[0]["id"]])
        job = await export(db_app, t.owner, t.pid, format="csv")
        assert job["status"] == "ready"
        assert job["rows"] == 4
        assert job["filename"].endswith("-records.csv")
        text = (await download(t.owner, t.pid, job["id"])).decode()
        rows = list(csv.DictReader(io.StringIO(text)))
        assert len(rows) == 4
        by_id = {row["Winnow ID"]: row for row in rows}
        assert by_id[str(risky)]["Title"] == "'=HYPERLINK(1)"
        assert by_id[str(risky)]["Title/abstract status"] == "included"
        assert by_id[str(second)]["Title/abstract status"] == "excluded"
        assert by_id[str(second)]["Title/abstract reasons"] == reasons[0]["label"]
        assert "Duplicate of" not in rows[0]

        included = await export(
            db_app, t.owner, t.pid, format="csv", filters={"status": "included"}
        )
        only = list(
            csv.DictReader(io.StringIO((await download(t.owner, t.pid, included["id"])).decode()))
        )
        assert [row["Winnow ID"] for row in only] == [str(risky)]

        # Yours alone: another member cannot see or fetch it.
        assert (await get(t.reviewer, f"/projects/{t.pid}/exports/{job['id']}")).status_code == 404
        mine = (await get(t.owner, f"/projects/{t.pid}/exports")).json()
        assert {row["id"] for row in mine} == {job["id"], included["id"]}
        actions = set(await db.scalars(select(AuditLog.action)))
        assert {"export.requested", "export.downloaded"} <= actions


async def test_xlsx_cells_are_text_never_formulas(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, tmp_path: Path
) -> None:
    async with team(db_app, db, mailer, records=2) as t:
        await db.execute(
            update(Record).where(Record.id == t.records[0]).values(title="=cmd|' /C calc'!A0")
        )
        await db.commit()
        job = await export(db_app, t.owner, t.pid, format="xlsx")
        path = tmp_path / "records.xlsx"
        path.write_bytes(await download(t.owner, t.pid, job["id"]))
        sheet = load_workbook(path).active
        assert sheet is not None
        headers = [cell.value for cell in sheet[1]]
        assert headers[:2] == ["Winnow ID", "Title"]
        titles = {row[1].value: row[1].data_type for row in sheet.iter_rows(min_row=2)}
        assert titles["=cmd|' /C calc'!A0"] == "s"


async def test_a_blinded_reviewer_exports_only_their_own_decisions(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=2) as t:
        await settings(t.owner, t.pid, blind_mode=True, reviewers_per_record_ta=1)
        await decide(t.owner, t.pid, t.records[0], "exclude")
        await decide(t.reviewer, t.pid, t.records[1], "include")
        job = await export(db_app, t.reviewer, t.pid, format="csv")
        rows = list(
            csv.DictReader(io.StringIO((await download(t.reviewer, t.pid, job["id"])).decode()))
        )
        mine = {row["Winnow ID"]: row["My title/abstract decision"] for row in rows}
        assert mine == {str(t.records[0]): "", str(t.records[1]): "include"}
        assert "Title/abstract status" not in rows[0]


async def test_only_the_owner_makes_a_backup_and_downloads_wait_until_ready(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=1) as t:
        refused = await post(t.reviewer, f"/projects/{t.pid}/exports", {"kind": "backup"})
        assert refused.status_code == 403
        queued = (await post(t.owner, f"/projects/{t.pid}/exports", {"format": "csv"})).json()
        early = await t.owner.get(f"{API}/projects/{t.pid}/exports/{queued['id']}/file")
        assert early.status_code == 409
        wrong = await post(t.owner, f"/projects/{t.pid}/exports", {"format": "zip"})
        assert wrong.status_code == 422


async def build_review(db_app: FastAPI, db: AsyncSession, t: Any) -> None:
    """A review with something of everything in it."""
    pid = uuid.UUID(t.pid)
    await settings(t.owner, t.pid, reviewers_per_record_ta=2, reviewers_per_record_ft=1)
    batch = ImportBatch(
        id=uuid7(),
        project_id=pid,
        source_name="PubMed",
        database_name="PubMed",
        file_key="imports/original",
        filename="pubmed.nbib",
        size_bytes=10,
        file_format=FileFormat.NBIB,
        status=ImportStatus.DONE,
        total=6,
        imported=6,
    )
    db.add(batch)
    await db.execute(
        update(Record).where(Record.project_id == pid).values(import_batch_id=batch.id)
    )
    await db.execute(
        update(Record)
        .where(Record.id == t.records[5])
        .values(is_duplicate=True, duplicate_of=t.records[0])
    )
    await db.commit()
    await db_app.state.storage.save("imports/original", _one(b"TI  - search"), 100)
    reasons = (await get(t.owner, f"/projects/{t.pid}/exclusion-reasons")).json()
    for record_id, (a, b) in zip(
        t.records[:5],
        [
            ("include", "include"),
            ("include", "include"),
            ("exclude", "exclude"),
            ("include", "exclude"),
            ("exclude", "exclude"),
        ],
        strict=True,
    ):
        extra = {"reason_ids": [reasons[0]["id"]]} if a == "exclude" else {}
        assert (await decide(t.owner, t.pid, record_id, a, **extra)).status_code == 200
        extra = {"reason_ids": [reasons[1]["id"]]} if b == "exclude" else {}
        assert (await decide(t.reviewer, t.pid, record_id, b, **extra)).status_code == 200
    await post(
        t.owner,
        f"/projects/{t.pid}/records/{t.records[0]}/notes",
        {"body": "Primary study", "visibility": "team"},
    )
    label = (
        await post(t.owner, f"/projects/{t.pid}/labels", {"name": "Key paper", "color": "green"})
    ).json()
    await api(
        t.owner,
        "PUT",
        f"/projects/{t.pid}/records/{t.records[0]}/labels",
        {"label_ids": [label["id"]]},
    )
    # Full text: one included with a PDF, highlights and a risk-of-bias assessment; one not
    # retrievable.
    await decide(t.owner, t.pid, t.records[0], "include", stage="full_text")
    uploaded = await t.owner.post(
        f"{API}/projects/{t.pid}/records/{t.records[0]}/fulltext",
        files={"file": ("study.pdf", tiny_pdf("The included study"), "application/pdf")},
        headers={"X-CSRF-Token": await csrf(t.owner)},
    )
    assert uploaded.status_code == 201, uploaded.text
    await db.execute(update(Fulltext).values(scan_status=ScanStatus.CLEAN))
    await db.commit()
    fid = uploaded.json()["id"]
    await post(
        t.owner,
        f"/projects/{t.pid}/fulltext/{fid}/annotations",
        {"page": 1, "rects": [[0.1, 0.1, 0.5, 0.02]], "comment": "Outcome here"},
    )
    await post(
        t.owner,
        f"/projects/{t.pid}/records/{t.records[1]}/fulltext/not-retrievable",
        {"note": "Asked twice"},
    )
    await api(
        t.owner,
        "PATCH",
        f"/projects/{t.pid}/prisma/manual",
        {"other_sources": [{"name": "Citation searching", "count": 2}]},
    )
    rob = {
        "tool_key": "rob2",
        "variant_key": "parallel_assignment",
        "status": "submitted",
        "judgements": {
            d: {"risk_of_bias": "low"}
            for d in (
                "randomisation_process",
                "deviations_from_intended_interventions",
                "missing_outcome_data",
                "measurement_of_outcome",
                "selection_of_reported_result",
            )
        },
    }
    assert (
        await api(t.owner, "PUT", f"/projects/{t.pid}/rob/{t.records[0]}", rob)
    ).status_code == 200


async def _one(data: bytes) -> Any:
    yield data


async def backup_bytes(db_app: FastAPI, t: Any) -> bytes:
    job = await export(db_app, t.owner, t.pid, kind="backup")
    assert job["status"] == "ready", job
    assert job["filename"].endswith("-backup.zip")
    return await download(t.owner, t.pid, job["id"])


async def restore(db_app: FastAPI, client: AsyncClient, data: bytes) -> dict[str, Any]:
    started = await client.post(
        f"{API}/restores",
        files={"file": ("backup.zip", data, "application/zip")},
        headers={"X-CSRF-Token": await csrf(client)},
    )
    assert started.status_code == 201, started.text
    await run_restore(
        sessionmaker=db_app.state.sessionmaker,
        queue=db_app.state.queue,
        storage=db_app.state.storage,
        settings=db_app.state.settings,
        restore_id=uuid.UUID(started.json()["id"]),
    )
    result: dict[str, Any] = (await get(client, f"/restores/{started.json()['id']}")).json()
    return result


def comparable(flow: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in flow.items() if key != "manual"}


async def test_a_backup_restores_as_a_whole_new_review(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        team(db_app, db, mailer, records=6) as t,
        person(db_app, mailer, "linus@example.org", ip="10.9.0.9") as other,
    ):
        await build_review(db_app, db, t)
        data = await backup_bytes(db_app, t)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["format"] == "winnow-backup"
            assert manifest["counts"]["records"] == 6
            assert manifest["counts"]["decisions"] == 11
            assert len([n for n in archive.namelist() if n.startswith("files/pdfs/")]) == 1

        restored = await restore(db_app, other, data)
        assert restored["status"] == "ready", restored
        new = restored["project_id"]
        assert new != t.pid
        assert restored["restored"]["records"] == 6

        project = (await get(other, f"/projects/{new}")).json()
        assert project["title"].endswith("(restored)")
        assert project["membership"]["role"] == "owner"
        # Like any owner, they start blind; they see the team's work once they choose to.
        assert project["membership"]["keep_blind"] is True
        unblind = await api(other, "PATCH", f"/projects/{new}/membership", {"keep_blind": False})
        assert unblind.status_code == 200, unblind.text
        # The same review: its PRISMA flow, its agreement and its work.
        before = (await get(t.owner, f"/projects/{t.pid}/prisma")).json()
        after = (await get(other, f"/projects/{new}/prisma")).json()
        assert comparable(after) == comparable(before)
        assert after["manual"]["other_sources"] == [{"name": "Citation searching", "count": 2}]
        kappa_before = (await get(t.owner, f"/projects/{t.pid}/stats")).json()["stages"][0][
            "agreement"
        ]
        kappa_after = (await get(other, f"/projects/{new}/stats")).json()["stages"][0]["agreement"]
        assert kappa_before["pairs"][0]["kappa"] is not None
        assert kappa_after["pairs"][0]["kappa"] == kappa_before["pairs"][0]["kappa"]
        records = (await get(other, f"/projects/{new}/records?duplicates=true&limit=50")).json()
        assert records["total"] == 6
        new_pid = uuid.UUID(new)
        assert (
            await db.scalar(
                select(func.count()).select_from(Decision).where(Decision.project_id == new_pid)
            )
            == 11
        )
        note = await db.scalar(select(Note.body).where(Note.project_id == new_pid))
        assert note == "Primary study"
        labelled = await db.scalar(
            select(func.count())
            .select_from(RecordLabel)
            .join(Record, Record.id == RecordLabel.record_id)
            .where(Record.project_id == new_pid)
        )
        assert labelled == 1
        duplicate = await db.scalar(
            select(Record).where(Record.project_id == new_pid, Record.is_duplicate.is_(True))
        )
        assert duplicate is not None
        assert duplicate.duplicate_of is not None
        assert (await db.get(Record, duplicate.duplicate_of)).project_id == new_pid  # type: ignore[union-attr]
        # The PDF, scanned again before it opens; its highlights came too.
        pdf = await db.scalar(select(Fulltext).where(Fulltext.project_id == new_pid))
        assert pdf is not None
        assert pdf.scan_status in (ScanStatus.PENDING, ScanStatus.SKIPPED)
        assert await db_app.state.storage.read_bytes(pdf.file_key) == tiny_pdf("The included study")
        rob = (await get(other, f"/projects/{new}/rob/summary?tool=rob2")).json()
        assert len(rob["variants"][0]["studies"]) == 1
        # Its history came with it, and it says it was restored.
        history = set(
            await db.scalars(select(AuditLog.action).where(AuditLog.project_id == new_pid))
        )
        assert {"decision.made", "project.restored"} <= history
        # People in the backup who have accounts here are those accounts; nobody became a
        # member but the one who restored it.
        owner_id = await db.scalar(select(User.id).where(User.email == OWNER))
        decided_by = set(
            await db.scalars(select(Decision.user_id).where(Decision.project_id == new_pid))
        )
        assert owner_id in decided_by
        members = (await get(other, f"/projects/{new}/members")).json()["items"]
        assert [m["user"]["email"] for m in members] == ["linus@example.org"]
        # The original is untouched.
        assert (await get(t.owner, f"/projects/{t.pid}/records?limit=1")).json()["total"] == 5


async def test_people_unknown_here_become_placeholders_that_cannot_sign_in(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        team(db_app, db, mailer, records=2) as t,
        person(db_app, mailer, "linus@example.org", ip="10.9.0.8") as other,
    ):
        await settings(t.owner, t.pid, reviewers_per_record_ta=1)
        await decide(t.reviewer, t.pid, t.records[0], "include")
        data = await backup_bytes(db_app, t)
        # As if from another instance, whose people are not on this one.
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(buffer, "w") as target:
            for item in source.infolist():
                content = source.read(item)
                if item.filename == "people.json":
                    people = json.loads(content)
                    for index, entry in enumerate(people):
                        entry["email"] = f"elsewhere-{index}@other-instance.org"
                    content = json.dumps(people).encode()
                target.writestr(item, content)
        restored = await restore(db_app, other, buffer.getvalue())
        assert restored["status"] == "ready", restored
        decided_by = await db.scalar(
            select(User)
            .join(Decision, Decision.user_id == User.id)
            .where(Decision.project_id == uuid.UUID(restored["project_id"]))
        )
        assert decided_by is not None
        assert decided_by.email.endswith("@restored.invalid")
        assert decided_by.password_hash == NO_PASSWORD
        assert decided_by.deleted_at is not None
        assert decided_by.name.endswith("(restored)")


def backup_with(files: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(
                name, content if isinstance(content, bytes | str) else json.dumps(content)
            )
    return buffer.getvalue()


MANIFEST = {"format": "winnow-backup", "version": 1, "counts": {}}
PROJECT = {"id": str(uuid.uuid4()), "title": "Hostile"}


@pytest.mark.parametrize(
    ("files", "problem"),
    [
        ({"hello.txt": "hi"}, "no manifest.json"),
        ({"manifest.json": {"format": "other"}}, "not a Winnow project backup"),
        ({"manifest.json": {**MANIFEST, "version": 99}}, "format version 99"),
        (
            {
                "manifest.json": MANIFEST,
                "project.json": PROJECT,
                "people.json": [],
                "tables/criteria.jsonl": json.dumps(
                    {
                        "id": str(uuid.uuid4()),
                        "project_id": PROJECT["id"],
                        "kind": "inclusion",
                        "text": "x",
                        "position": 0,
                        "is_admin": True,
                    }
                ),
            },
            "does not know",
        ),
        (
            {
                "manifest.json": MANIFEST,
                "project.json": PROJECT,
                "people.json": [],
                "tables/criteria.jsonl": json.dumps(
                    {
                        "id": str(uuid.uuid4()),
                        "project_id": str(uuid.uuid4()),
                        "kind": "inclusion",
                        "text": "x",
                        "position": 0,
                    }
                ),
            },
            "does not hold",
        ),
        (
            {
                "manifest.json": MANIFEST,
                "project.json": PROJECT,
                "people.json": [],
                "tables/criteria.jsonl": json.dumps(
                    {
                        "id": str(uuid.uuid4()),
                        "project_id": PROJECT["id"],
                        "kind": "inclusion",
                        "text": "x",
                        "position": "first",
                    }
                ),
            },
            "should be a whole number",
        ),
        ({"../escape.json": "{}", "manifest.json": MANIFEST}, "outside the folder"),
        (
            {
                "manifest.json": MANIFEST,
                "project.json": {**PROJECT, "settings": {"reviewers_per_record_ta": 99}},
            },
            "project.reviewers_per_record_ta is not valid",
        ),
        (
            {"manifest.json": MANIFEST, "project.json": {"id": PROJECT["id"]}},
            "project.title is not valid",
        ),
    ],
)
async def test_a_hostile_or_broken_backup_is_refused_and_leaves_nothing(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, files: dict[str, Any], problem: str
) -> None:
    async with person(db_app, mailer, OWNER, ip="10.9.0.7") as someone:
        projects_before = await db.scalar(select(func.count()).select_from(Project))
        restored = await restore(db_app, someone, backup_with(files))
        assert restored["status"] == "failed"
        assert problem in restored["problem"]
        assert restored["project_id"] is None
        assert await db.scalar(select(func.count()).select_from(Project)) == projects_before
        job = await db.get(RestoreJob, uuid.UUID(restored["id"]))
        assert job is not None
        assert job.zip_key is None  # the upload was removed


async def test_a_zip_bomb_backup_is_refused(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("manifest.json", json.dumps(MANIFEST))
        with archive.open("tables/records.jsonl", "w", force_zip64=True) as entry:
            for _ in range(64):
                entry.write(bytes(1024 * 1024))
    async with person(db_app, mailer, OWNER, ip="10.9.0.6") as someone:
        restored = await restore(db_app, someone, buffer.getvalue())
        assert restored["status"] == "failed"
        assert "ZIP bomb" in restored["problem"]


async def test_exports_expire(db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer) -> None:
    from datetime import UTC, datetime, timedelta

    from app.workers.exports import purge_expired

    async with team(db_app, db, mailer, records=1) as t:
        job = await export(db_app, t.owner, t.pid, format="csv")
        row = await db.get(ExportJob, uuid.UUID(job["id"]))
        assert row is not None
        key = row.file_key
        await db.execute(
            update(ExportJob)
            .where(ExportJob.id == row.id)
            .values(expires_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await db.commit()
        assert (
            await purge_expired(
                sessionmaker=db_app.state.sessionmaker, storage=db_app.state.storage
            )
            >= 1
        )
        assert (await get(t.owner, f"/projects/{t.pid}/exports/{job['id']}")).status_code == 404
        with pytest.raises(FileNotFoundError):
            await db_app.state.storage.size(key)


async def test_records_export_as_ris_and_bibtex_with_their_decisions(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=2) as t:
        await settings(t.owner, t.pid, reviewers_per_record_ta=1)
        reasons = (await get(t.owner, f"/projects/{t.pid}/exclusion-reasons")).json()
        await decide(t.reviewer, t.pid, t.records[0], "include")
        await decide(t.reviewer, t.pid, t.records[1], "exclude", reason_ids=[reasons[0]["id"]])

        ris_job = await export(db_app, t.owner, t.pid, format="ris")
        assert ris_job["filename"].endswith("-records.ris")
        text = (await download(t.owner, t.pid, ris_job["id"])).decode()
        assert text.count("ER  - \r\n") == 2
        assert "N1  - Title/abstract: included\r\n" in text
        assert f"N1  - Title/abstract: excluded ({reasons[0]['label']})\r\n" in text
        assert f"C3  - {reasons[0]['label']}\r\n" in text
        assert [getattr(item, "title", None) for item in ris.parse(text)] == [
            "Night shifts and sleep, study 0",
            "Night shifts and sleep, study 1",
        ]

        bib_job = await export(db_app, t.owner, t.pid, format="bibtex")
        assert bib_job["filename"].endswith("-records.bib")
        entries = (await download(t.owner, t.pid, bib_job["id"])).decode()
        # The same first author and year: keys stay apart.
        assert "@article{smith2015," in entries
        assert "@article{smith2016," in entries
        assert "note = {Title/abstract: included. Full text: pending. Winnow ID:" in entries
        assert "Full text: not eligible" not in entries
        assert len(list(bibtex.parse(entries))) == 2


async def test_an_export_fails_plainly_when_it_cannot_be_made(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=1) as t:
        # Someone who leaves the review before their export is made does not get it.
        queued = (await post(t.reviewer, f"/projects/{t.pid}/exports", {"format": "csv"})).json()
        grace = await db.scalar(select(User.id).where(User.email == REVIEWER))
        left = await api(t.owner, "DELETE", f"/projects/{t.pid}/members/{grace}")
        assert left.status_code == 204, left.text
        status = await run_export(
            sessionmaker=db_app.state.sessionmaker,
            redis=db_app.state.redis,
            storage=db_app.state.storage,
            export_id=uuid.UUID(queued["id"]),
        )
        assert status == "failed"
        row = await db.get(ExportJob, uuid.UUID(queued["id"]))
        assert row is not None
        await db.refresh(row)
        assert row.problem == "You are no longer allowed to export this review."
        assert row.file_key is None


CRITERION = str(uuid.uuid4())
RECORD = str(uuid.uuid4())
PDF = str(uuid.uuid4())
PERSON = {"id": str(uuid.uuid4()), "name": "Ada Lovelace", "email": OWNER}


def jsonl(*rows: Any) -> str:
    return "\n".join(row if isinstance(row, str) else json.dumps(row) for row in rows)


CRITERION_ROW = {
    "id": CRITERION,
    "project_id": PROJECT["id"],
    "kind": "inclusion",
    "text": "x",
    "position": 0,
}


@pytest.mark.parametrize(
    ("files", "problem"),
    [
        ({"manifest.json": "{"}, "manifest.json is not valid JSON"),
        ({"project.json": [PROJECT]}, "should describe one review"),
        ({"project.json": {**PROJECT, "settings": [1]}}, "project.settings should be an object"),
        ({"people.json": {"people": []}}, "people.json should be a list"),
        ({"people.json": [1]}, "not a person"),
        ({"people.json": [{"id": PERSON["id"]}]}, "needs a name and an email"),
        ({"manifest.json": {**MANIFEST, "counts": {"criteria": 2}}}, "holds 2 rows of criteria"),
        ({"tables/criteria.jsonl": "{not json"}, "line 1, is not valid JSON"),
        ({"tables/criteria.jsonl": jsonl("", [1])}, "line 2, is not a row"),
        ({"tables/criteria.jsonl": jsonl({**CRITERION_ROW, "id": None})}, "has no id"),
        ({"tables/criteria.jsonl": jsonl(CRITERION_ROW, CRITERION_ROW)}, "twice"),
        (
            {
                "tables/records.jsonl": jsonl(
                    {"id": RECORD, "project_id": PROJECT["id"], "title": "A study"}
                ),
                "tables/fulltexts.jsonl": jsonl(
                    {"id": PDF, "project_id": PROJECT["id"], "record_id": RECORD}
                ),
            },
            f"missing files/pdfs/{PDF}.pdf",
        ),
    ],
)
async def test_every_part_of_a_backup_is_checked(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, files: dict[str, Any], problem: str
) -> None:
    backup = {
        "manifest.json": MANIFEST,
        "project.json": PROJECT,
        "people.json": [PERSON],
        "tables/criteria.jsonl": jsonl(CRITERION_ROW),
        **files,
    }
    async with person(db_app, mailer, "linus@example.org", ip="10.9.0.5") as someone:
        projects_before = await db.scalar(select(func.count()).select_from(Project))
        restored = await restore(db_app, someone, backup_with(backup))
        assert restored["status"] == "failed"
        assert problem in restored["problem"]
        assert await db.scalar(select(func.count()).select_from(Project)) == projects_before


async def test_restoring_your_own_backup_keeps_your_work_as_yours(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """The common case: moving a review to another instance, as the same person."""
    async with team(db_app, db, mailer, records=1) as t:
        await settings(t.owner, t.pid, reviewers_per_record_ta=1)
        await decide(t.owner, t.pid, t.records[0], "include")
        criterion = (
            await post(t.owner, f"/projects/{t.pid}/criteria", {"kind": "inclusion", "text": "RCT"})
        ).json()
        owner_id = await db.scalar(select(User.id).where(User.email == OWNER))
        db.add(
            LlmSuggestion(
                project_id=uuid.UUID(t.pid),
                record_id=t.records[0],
                user_id=owner_id,
                stage="title_abstract",
                provider="test",
                model="test",
                prompt_version="1",
                decision="include",
                confidence=0.9,
                criteria=[
                    {"criterion_id": criterion["id"], "met": "yes"},
                    {"criterion_id": "not an id", "met": "no"},
                    "free text",
                ],
                rationale="Randomised.",
            )
        )
        await db.commit()
        restored = await restore(db_app, t.owner, await backup_bytes(db_app, t))
        assert restored["status"] == "ready", restored
        new = uuid.UUID(restored["project_id"])
        assert (
            await db.scalar(select(Decision.user_id).where(Decision.project_id == new)) == owner_id
        )
        new_criterion = await db.scalar(select(Criterion.id).where(Criterion.project_id == new))
        suggestion = await db.scalar(select(LlmSuggestion).where(LlmSuggestion.project_id == new))
        assert suggestion is not None
        assert suggestion.criteria == [
            {"criterion_id": str(new_criterion), "met": "yes"},
            {"criterion_id": "not an id", "met": "no"},
            "free text",
        ]

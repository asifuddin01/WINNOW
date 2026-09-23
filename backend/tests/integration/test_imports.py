"""Importing a file end to end: upload, preview, run, read and undo (guide 8.3)."""

import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ImportBatch, Record
from app.workers.imports import run_import
from tests.conftest import MemoryMailer
from tests.project_helpers import OWNER, api, create_project, delete, get, person, post

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "parsers"


async def upload_files(
    client: AsyncClient, pid: str, names: Sequence[str], **fields: Any
) -> dict[str, Any]:
    """Post a drop of files the way the browser does, as multipart form data."""
    from tests.auth_helpers import csrf

    contents: dict[str, bytes] = fields.pop("contents", {})
    parts = [
        (
            "files",
            (
                name,
                contents.get(name) or FIXTURES.joinpath(name).read_bytes(),
                "application/octet-stream",
            ),
        )
        for name in names
    ]
    response = await client.post(
        f"/api/v1/projects/{pid}/imports",
        files=parts,
        data={"database_name": "PubMed", **fields},
        headers={"X-CSRF-Token": await csrf(client)},
    )
    assert response.status_code == 201, response.text
    upload: dict[str, Any] = response.json()
    return upload


async def upload(
    client: AsyncClient, pid: str, name: str, content: bytes | None = None, **fields: str
) -> dict[str, Any]:
    """One file, for the tests that only care about one."""
    result = await upload_files(
        client, pid, [name], contents={name: content} if content is not None else {}, **fields
    )
    batch: dict[str, Any] = result["batches"][0]
    return batch


async def run(db_app: FastAPI, batch_id: str) -> dict[str, int]:
    """What the worker does when the import is confirmed."""
    return await run_import(
        sessionmaker=db_app.state.sessionmaker,
        redis=db_app.state.redis,
        storage=db_app.state.storage,
        batch_id=uuid.UUID(batch_id),
    )


async def test_upload_preview_confirm_and_read(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        batch = await upload(
            owner, pid, "pubmed.nbib", source_name="PubMed 2026-09-23", search_string="nurses"
        )
        assert batch["file_format"] == "nbib"
        assert batch["status"] == "queued"
        assert batch["size_bytes"] > 0

        preview = (await get(owner, f"/projects/{pid}/imports/{batch['id']}/preview")).json()
        assert [record["title"] for record in preview["records"]] == [
            "Rotating night shifts and sleep quality among hospital nurses: a prospective "
            "cohort study."
        ]
        assert preview["records"][0]["doi"] == "10.1111/jan.13894"
        assert preview["columns"] == []  # only CSV needs a mapping

        confirmed = await post(owner, f"/projects/{pid}/imports/{batch['id']}/confirm", {})
        assert confirmed.status_code == 200
        assert confirmed.json()["batch"]["status"] == "parsing"

        assert await run(db_app, batch["id"]) == {"imported": 1, "problems": 0}

        history = (await get(owner, f"/projects/{pid}/imports")).json()
        assert history[0]["status"] == "done"
        assert history[0]["imported"] == 1
        assert history[0]["source_name"] == "PubMed 2026-09-23"

        records = (await get(owner, f"/projects/{pid}/records")).json()
        assert records["total"] == 1
        record = records["items"][0]
        assert record["pmid"] == "31234567"
        assert record["ta_final"] == "pending"
        response = await get(owner, f"/projects/{pid}/records/{record['id']}")
        detail = response.json()
        assert response.status_code == 200, detail
        assert detail["abstract"] is not None
        assert detail["source"] == "PubMed 2026-09-23"
        assert detail["keywords"]
        # The database filled the search vector from the row itself.
        vector = await db.scalar(
            select(Record.search_vector).where(Record.id == uuid.UUID(record["id"]))
        )
        assert vector is not None
        assert "nurs" in vector  # stemmed, weighted A for the title


async def test_a_record_that_cannot_be_read_is_reported_not_fatal(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    """Guide 8.3: the import succeeds partially and says what it could not read."""
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        batch = await upload(owner, pid, "messy.ris")
        await post(owner, f"/projects/{pid}/imports/{batch['id']}/confirm", {})
        assert await run(db_app, batch["id"]) == {"imported": 2, "problems": 1}

        history = (await get(owner, f"/projects/{pid}/imports")).json()[0]
        assert history["status"] == "done"
        assert history["total"] == 3
        assert history["problems"] == [
            {"at": 10, "unit": "line", "reason": "no title, DOI or PubMed id"}
        ]
        titles = [
            r["title"] for r in (await get(owner, f"/projects/{pid}/records")).json()["items"]
        ]
        assert "Café workers & sleep: a pilot study with a wrapped title" in titles


async def test_csv_columns_are_mapped_before_the_import_runs(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        batch = await upload(owner, pid, "scopus.csv")
        preview = (await get(owner, f"/projects/{pid}/imports/{batch['id']}/preview")).json()
        assert "Source title" in preview["columns"]
        assert preview["suggested_mapping"]["Source title"] == "journal"
        assert len(preview["sample_rows"]) == 2

        # The person changes their mind about one column before confirming.
        mapping = {**preview["suggested_mapping"], "Index Keywords": "keywords"}
        await post(
            owner,
            f"/projects/{pid}/imports/{batch['id']}/confirm",
            {"column_mapping": mapping},
        )
        assert await run(db_app, batch["id"]) == {"imported": 2, "problems": 0}
        records = (await get(owner, f"/projects/{pid}/records")).json()["items"]
        assert {r["journal"] for r in records} == {"Journal of Advanced Nursing", "Sleep Health"}


async def test_undoing_an_import_takes_its_records_with_it(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        batch = await upload(owner, pid, "ovid_embase.ris")
        await post(owner, f"/projects/{pid}/imports/{batch['id']}/confirm", {})
        await run(db_app, batch["id"])
        assert (await get(owner, f"/projects/{pid}/records")).json()["total"] == 2

        assert (await delete(owner, f"/projects/{pid}/imports/{batch['id']}")).status_code == 204
        assert (await get(owner, f"/projects/{pid}/records")).json()["total"] == 0
        assert (await get(owner, f"/projects/{pid}/imports")).json() == []
        left = await db.scalar(select(func.count()).select_from(ImportBatch))
        assert left == 0


async def test_a_file_winnow_cannot_read_is_refused(db_app: FastAPI, mailer: MemoryMailer) -> None:
    from tests.auth_helpers import csrf

    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        response = await owner.post(
            f"/api/v1/projects/{project['id']}/imports",
            files={"files": ("holiday.jpg", b"\xff\xd8\xff\xe0 not a search export", "image/jpeg")},
            data={"database_name": "Other"},
            headers={"X-CSRF-Token": await csrf(owner)},
        )
        assert response.status_code == 415
        assert response.json()["code"] == "unknown_format"
        assert (await get(owner, f"/projects/{project['id']}/imports")).json() == []


async def test_only_admins_import(db_app: FastAPI, mailer: MemoryMailer) -> None:
    """Guide 7: importing records is an owner's or admin's job."""
    from tests.project_helpers import REVIEWER, add_member

    async with (
        person(db_app, mailer, OWNER, ip="10.5.0.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.5.0.2") as reviewer,
    ):
        project = await create_project(owner)
        pid = project["id"]
        await add_member(owner, reviewer, pid, REVIEWER)
        batch = await upload(owner, pid, "cochrane.ris")

        refused = await api(reviewer, "POST", f"/projects/{pid}/imports", {})
        assert refused.status_code == 403  # the role is checked before the body
        assert (
            await get(reviewer, f"/projects/{pid}/imports/{batch['id']}/preview")
        ).status_code == 403
        assert (await delete(reviewer, f"/projects/{pid}/imports/{batch['id']}")).status_code == 403
        # But a reviewer sees the history and the records.
        assert (await get(reviewer, f"/projects/{pid}/imports")).json()[0]["id"] == batch["id"]


async def test_a_whole_drop_of_files_arrives_as_separate_imports(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """Guide 8.3: a search leaves a database in several files; they come in together."""
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        result = await upload_files(
            owner,
            pid,
            ["wos.ris", "cinahl.ris", "zotero.bib"],
            databases=["Web of Science", "CINAHL", "arXiv"],
            search_string="kidney AND ct",
        )
        assert result["rejected"] == []
        assert [batch["database_name"] for batch in result["batches"]] == [
            "Web of Science",
            "CINAHL",
            "arXiv",
        ]
        # Each file is its own import, named so the history can tell them apart, and each
        # keeps the search that produced it.
        assert [batch["source_name"] for batch in result["batches"]] == [
            "Web of Science · wos",
            "CINAHL · cinahl",
            "arXiv · zotero",
        ]
        assert {batch["search_string"] for batch in result["batches"]} == {"kidney AND ct"}

        for batch in result["batches"]:
            await post(owner, f"/projects/{pid}/imports/{batch['id']}/confirm", {})
            await run(db_app, batch["id"])
        imported = await db.scalar(
            select(func.count()).select_from(Record).where(Record.project_id == uuid.UUID(pid))
        )
        history = (await get(owner, f"/projects/{pid}/imports")).json()
        assert imported == sum(batch["total"] for batch in history)
        assert (imported or 0) > 3


async def test_one_unreadable_file_does_not_lose_the_others(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        result = await upload_files(
            owner,
            pid,
            ["pubmed.nbib", "holiday.txt"],
            contents={"holiday.txt": b"We went to the seaside and it rained.\n"},
        )
        assert [batch["filename"] for batch in result["batches"]] == ["pubmed.nbib"]
        assert result["rejected"][0]["filename"] == "holiday.txt"
        assert "could not read" in result["rejected"][0]["reason"]


async def test_more_files_than_the_instance_allows_are_refused(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    from tests.auth_helpers import csrf

    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        parts = [
            ("files", (f"copy{index}.ris", b"TY  - JOUR\nTI  - A record\nER  - \n", "text/plain"))
            for index in range(db_app.state.settings.max_upload_files + 1)
        ]
        response = await owner.post(
            f"/api/v1/projects/{project['id']}/imports",
            files=parts,
            data={"database_name": "Other"},
            headers={"X-CSRF-Token": await csrf(owner)},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "too_many_files"
        assert (await get(owner, f"/projects/{project['id']}/imports")).json() == []

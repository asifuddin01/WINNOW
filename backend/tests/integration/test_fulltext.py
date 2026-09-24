"""Full texts end to end (guide 8.8, 12.4): uploading, scanning, quarantine, links,
annotations, free copies, not retrievable, and ZIPs of PDFs."""

import os
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from arq import Retry
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.fulltext import openaccess
from app.models import (
    AuditLog,
    Fulltext,
    FulltextBatch,
    FullTextStatus,
    Record,
    ScanStatus,
    TitleAbstractStatus,
)
from app.security import clamav
from app.workers.fulltext import SCAN_TRIES, discard_stale_batches, run_batch, run_scan
from tests.auth_helpers import csrf
from tests.conftest import MemoryMailer, make_client
from tests.pdf_helpers import EICAR, eicar_pdf, make_zip, tiny_pdf, zip_bomb
from tests.project_helpers import API, add_member, api, delete, get, patch, person, post
from tests.screening_helpers import decide, settings, team

VIEWER = "linus@example.org"


class FakeQueue:
    """Stands in for arq: records what would have been enqueued, and passes anything else
    (the ranking nudge's counters) to the real Redis."""

    def __init__(self, real: Any = None) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self._real = real

    async def enqueue_job(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.jobs.append((name, args, kwargs))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


@pytest.fixture
def queue(db_app: FastAPI) -> FakeQueue:
    fake = FakeQueue(db_app.state.queue)
    db_app.state.queue = fake
    return fake


@pytest.fixture
def scanner(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    """A clamd stand-in that flags EICAR anywhere in the file; returns what it scanned."""
    scanned: list[bytes] = []

    async def scan(host: str, port: int, chunks: AsyncIterator[bytes]) -> clamav.ScanResult:
        data = b"".join([chunk async for chunk in chunks])
        scanned.append(data)
        if EICAR in data or b"eicar.com" in data:
            return clamav.ScanResult(False, "Eicar-Test-Signature")
        return clamav.ScanResult(True)

    monkeypatch.setattr(clamav, "scan", scan)
    return scanned


async def to_full_text(db: AsyncSession, ids: list[uuid.UUID]) -> None:
    await db.execute(
        update(Record).where(Record.id.in_(ids)).values(ta_final=TitleAbstractStatus.INCLUDED)
    )
    await db.commit()


async def upload(
    client: AsyncClient, pid: str, rid: uuid.UUID, data: bytes, name: str = "paper.pdf"
) -> Response:
    return await client.post(
        f"{API}/projects/{pid}/records/{rid}/fulltext",
        files={"file": (name, data, "application/pdf")},
        headers={"X-CSRF-Token": await csrf(client)},
    )


async def upload_zip(client: AsyncClient, pid: str, data: bytes) -> Response:
    return await client.post(
        f"{API}/projects/{pid}/fulltext/bulk",
        files={"file": ("papers.zip", data, "application/zip")},
        headers={"X-CSRF-Token": await csrf(client)},
    )


async def scan(db_app: FastAPI, fulltext_id: str, queue: FakeQueue, attempt: int = 1) -> Any:
    return await run_scan(
        sessionmaker=db_app.state.sessionmaker,
        redis=db_app.state.redis,
        queue=queue,  # type: ignore[arg-type]
        storage=db_app.state.storage,
        settings=db_app.state.settings,
        fulltext_id=uuid.UUID(fulltext_id),
        attempt=attempt,
    )


def stored(db_app: FastAPI, key: str) -> bool:
    return (Path(db_app.state.settings.storage_path) / key).exists()


def zips_on_disk(db_app: FastAPI) -> set[str]:
    folder = Path(db_app.state.settings.storage_path) / "fulltext-zips"
    return {path.name for path in folder.iterdir()} if folder.is_dir() else set()


async def open_pdf(client: AsyncClient, pid: str, rid: uuid.UUID, **params: str) -> Response:
    link = await client.get(f"{API}/projects/{pid}/records/{rid}/fulltext/url", params=params)
    assert link.status_code == 200, link.text
    assert link.json()["expires_in"] == 300
    return await client.get(link.json()["url"])


async def test_upload_scan_and_read(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue, scanner: list[bytes]
) -> None:
    async with team(db_app, db, mailer) as t:
        rid = t.records[0]
        pdf = tiny_pdf("Night shifts and sleep", "Methods")
        response = await upload(t.reviewer, t.pid, rid, pdf, name="Smith 2015 \u2013 sleep.pdf")
        assert response.status_code == 201, response.text
        added = response.json()
        assert added["scan_status"] == "pending"
        assert added["source"] == "upload"
        assert added["size_bytes"] == len(pdf)
        assert queue.jobs == [("scan_fulltext", (added["id"],), {"_job_id": f"scan:{added['id']}"})]

        # Not until the scanner says so.
        waiting = await get(t.owner, f"/projects/{t.pid}/records/{rid}/fulltext/url")
        assert waiting.status_code == 409
        assert waiting.json()["code"] == "not_available"

        outcome = await scan(db_app, added["id"], queue)
        assert outcome.status is ScanStatus.CLEAN
        assert scanner == [pdf]
        row = await db.get(Fulltext, uuid.UUID(added["id"]))
        assert row is not None
        await db.refresh(row)
        assert row.page_count == 2
        assert row.text_extracted == "Night shifts and sleep\nMethods"
        assert len(row.sha256) == 64

        served = await open_pdf(t.owner, t.pid, rid)
        assert served.status_code == 200
        assert served.content == pdf
        assert served.headers["content-type"] == "application/pdf"
        assert served.headers["x-content-type-options"] == "nosniff"
        assert served.headers["cache-control"] == "private, no-store"
        disposition = served.headers["content-disposition"]
        assert disposition.startswith('inline; filename="Smith 2015 _ sleep.pdf"')
        assert "filename*=UTF-8''Smith%202015%20%E2%80%93%20sleep.pdf" in disposition

        download = await open_pdf(t.owner, t.pid, rid, download="true")
        assert download.headers["content-disposition"].startswith("attachment;")

        detail = (await get(t.reviewer, f"/projects/{t.pid}/records/{rid}/fulltext")).json()
        assert detail["fulltext"]["scan_status"] == "clean"
        assert detail["fulltext"]["page_count"] == 2
        assert detail["not_retrievable"] is False


async def test_links_belong_to_whoever_asked_and_expire(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue, scanner: list[bytes]
) -> None:
    async with team(db_app, db, mailer) as t:
        rid = t.records[0]
        added = (await upload(t.owner, t.pid, rid, tiny_pdf())).json()
        await scan(db_app, added["id"], queue)
        link = (await get(t.owner, f"/projects/{t.pid}/records/{rid}/fulltext/url")).json()
        # Another member, even one who could ask for their own link, cannot use this one.
        assert (await t.reviewer.get(link["url"])).status_code == 404
        # Nor can someone signed out.
        async with make_client(db_app) as anonymous:
            assert (await anonymous.get(link["url"])).status_code == 401
        token = link["url"].rsplit("/", 1)[-1]
        await db_app.state.redis.delete(f"ft-link:{token}")
        assert (await t.owner.get(link["url"])).status_code == 404
        # Not something that is not a token at all.
        assert (await t.owner.get(f"{API}/files/..%2F..%2Fetc%2Fpasswd")).status_code in (404, 422)


async def test_a_malicious_pdf_is_quarantined_and_the_managers_are_told(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue, scanner: list[bytes]
) -> None:
    """Guide 12.10: "Malicious PDF (EICAR test file) is quarantined"."""
    async with team(db_app, db, mailer) as t:
        rid = t.records[0]
        added = (await upload(t.reviewer, t.pid, rid, eicar_pdf(), name="innocent.pdf")).json()
        outcome = await scan(db_app, added["id"], queue)
        assert outcome.status is ScanStatus.INFECTED
        await assert_quarantined(db_app, db, t, rid, added["id"], queue)


async def assert_quarantined(
    db_app: FastAPI, db: AsyncSession, t: Any, rid: uuid.UUID, fid: str, queue: FakeQueue
) -> None:
    row = await db.get(Fulltext, uuid.UUID(fid))
    assert row is not None
    await db.refresh(row)
    assert row.scan_status is ScanStatus.INFECTED
    assert "Eicar" in (row.scan_signature or "")
    assert row.file_key.startswith("quarantine/")
    assert row.text_extracted is None
    assert stored(db_app, row.file_key)

    refused = await get(t.owner, f"/projects/{t.pid}/records/{rid}/fulltext/url")
    assert refused.status_code == 409
    detail = (await get(t.owner, f"/projects/{t.pid}/records/{rid}/fulltext")).json()
    assert detail["fulltext"]["scan_status"] == "infected"

    audit = await db.scalar(select(AuditLog).where(AuditLog.action == "fulltext.quarantined"))
    assert audit is not None
    assert audit.entity_id == rid
    emails = [args for name, args, _ in queue.jobs if name == "send_email"]
    assert [to for to, *_ in emails] == ["ada@example.org"]  # the owner; not the reviewer
    assert "quarantined" in emails[0][1]
    assert "innocent.pdf" not in emails[0][2]
    assert f"/p/{t.pid}/screen/ft?view=pdfs" in emails[0][2]

    summary = (await get(t.owner, f"/projects/{t.pid}/fulltext/summary")).json()
    assert summary["quarantined"] == 0  # the record has not reached full text
    # Anyone screening may replace an unusable PDF.
    replaced = await upload(t.reviewer, t.pid, rid, tiny_pdf())
    assert replaced.status_code == 201, replaced.text


@pytest.fixture
async def real_clamd(db_app: FastAPI) -> None:
    """The real scanner: required in CI (WINNOW_REQUIRE_CLAMAV=1), optional elsewhere."""
    settings = db_app.state.settings
    if settings.clamav_host and await clamav.ping(settings.clamav_host, settings.clamav_port):
        return
    if os.environ.get("WINNOW_REQUIRE_CLAMAV"):
        pytest.fail(f"clamd is not reachable at {settings.clamav_host}:{settings.clamav_port}")
    pytest.skip("clamd is not running here")


@pytest.mark.usefixtures("real_clamd")
async def test_clamav_itself_quarantines_the_eicar_pdf(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue
) -> None:
    async with team(db_app, db, mailer) as t:
        rid = t.records[1]
        added = (await upload(t.reviewer, t.pid, rid, eicar_pdf(), name="innocent.pdf")).json()
        assert (await scan(db_app, added["id"], queue)).status is ScanStatus.INFECTED
        await assert_quarantined(db_app, db, t, rid, added["id"], queue)
        clean = (await upload(t.owner, t.pid, t.records[2], tiny_pdf())).json()
        assert (await scan(db_app, clean["id"], queue)).status is ScanStatus.CLEAN


async def test_the_bare_eicar_file_is_not_a_pdf_and_is_never_stored(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue
) -> None:
    async with team(db_app, db, mailer) as t:
        refused = await upload(t.reviewer, t.pid, t.records[0], EICAR, name="eicar.pdf")
        assert refused.status_code == 415
        assert refused.json()["code"] == "not_pdf"
        assert await db.scalar(select(Fulltext.id)) is None
        assert queue.jobs == []


async def test_uploads_that_are_too_large_are_refused(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue
) -> None:
    db_app.state.settings = db_app.state.settings.model_copy(update={"max_pdf_mb": 1})
    async with team(db_app, db, mailer) as t:
        big = tiny_pdf() + bytes(1024 * 1024)
        refused = await upload(t.reviewer, t.pid, t.records[0], big)
        assert refused.status_code == 413
        assert "1 MB" in refused.json()["detail"]


async def test_a_scanner_that_is_down_is_retried_then_the_file_stays_unavailable(
    db_app: FastAPI,
    db: AsyncSession,
    mailer: MemoryMailer,
    queue: FakeQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def down(*args: Any, **kwargs: Any) -> clamav.ScanResult:
        raise clamav.ScannerUnavailableError("connection refused")

    monkeypatch.setattr(clamav, "scan", down)
    async with team(db_app, db, mailer) as t:
        rid = t.records[0]
        added = (await upload(t.reviewer, t.pid, rid, tiny_pdf())).json()
        with pytest.raises(Retry):
            await scan(db_app, added["id"], queue, attempt=1)
        outcome = await scan(db_app, added["id"], queue, attempt=SCAN_TRIES)
        assert outcome.status is ScanStatus.ERROR
        assert (
            await get(t.owner, f"/projects/{t.pid}/records/{rid}/fulltext/url")
        ).status_code == 409


async def test_without_a_scanner_pdfs_are_marked_unscanned_and_readable(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue
) -> None:
    """`make local` runs without ClamAV; the PDF says so rather than claiming it is clean."""
    db_app.state.settings = db_app.state.settings.model_copy(update={"clamav_host": ""})
    async with team(db_app, db, mailer) as t:
        rid = t.records[0]
        added = (await upload(t.reviewer, t.pid, rid, tiny_pdf("unscanned"))).json()
        assert added["scan_status"] == "skipped"
        outcome = await scan(db_app, added["id"], queue)
        assert outcome.status is ScanStatus.SKIPPED
        assert outcome.pages == 1
        assert (await open_pdf(t.owner, t.pid, rid)).status_code == 200
        summary = (await get(t.owner, f"/projects/{t.pid}/fulltext/summary")).json()
        assert summary["scanner"] is False


async def test_who_may_add_replace_and_remove_a_pdf(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue, scanner: list[bytes]
) -> None:
    async with team(db_app, db, mailer, third=True) as t:
        assert t.third is not None
        rid = t.records[0]
        mine = (await upload(t.reviewer, t.pid, rid, tiny_pdf("first"))).json()
        await scan(db_app, mine["id"], queue)
        # Another reviewer may not replace or remove it...
        refused = await upload(t.third, t.pid, rid, tiny_pdf("second"))
        assert refused.status_code == 403
        assert (
            await delete(t.third, f"/projects/{t.pid}/records/{rid}/fulltext")
        ).status_code == 403
        # ...its uploader and the owner may, and the replaced file leaves storage.
        first_key = await db.scalar(select(Fulltext.file_key).where(Fulltext.record_id == rid))
        assert first_key is not None
        again = await upload(t.reviewer, t.pid, rid, tiny_pdf("second"))
        assert again.status_code == 201
        assert await db.get(Fulltext, uuid.UUID(mine["id"])) is None
        assert not stored(db_app, first_key)
        replaced = await upload(t.owner, t.pid, rid, tiny_pdf("third"))
        assert replaced.status_code == 201
        last_key = await db.scalar(select(Fulltext.file_key).where(Fulltext.record_id == rid))
        assert last_key is not None
        assert stored(db_app, last_key)
        removed = await delete(t.owner, f"/projects/{t.pid}/records/{rid}/fulltext")
        assert removed.status_code == 204
        assert not stored(db_app, last_key)
        detail = await get(t.owner, f"/projects/{t.pid}/records/{rid}/fulltext")
        assert detail.json()["fulltext"] is None

        async with person(db_app, mailer, VIEWER, ip="10.9.0.7") as viewer:
            await add_member(t.owner, viewer, t.pid, VIEWER, role="viewer")
            assert (await upload(viewer, t.pid, rid, tiny_pdf())).status_code == 403


async def test_not_retrievable_leaves_the_queue_and_counts_for_prisma(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue, scanner: list[bytes]
) -> None:
    async with team(db_app, db, mailer) as t:
        first, second, *_ = t.records
        path = f"/projects/{t.pid}/records/{first}/fulltext/not-retrievable"
        early = await post(t.reviewer, path, {"note": "No library access"})
        assert early.status_code == 409  # not at full text yet
        await to_full_text(db, [first, second])

        marked = await post(t.reviewer, path, {"note": "Asked the authors twice"})
        assert marked.status_code == 200, marked.text
        assert marked.json()["not_retrievable"] is True
        assert marked.json()["not_retrievable_note"] == "Asked the authors twice"
        record = await db.get(Record, first)
        assert record is not None
        await db.refresh(record)
        assert record.ft_final is FullTextStatus.NOT_RETRIEVABLE

        queue_now = (
            await get(t.reviewer, f"/projects/{t.pid}/screening/queue?stage=full_text&n=10")
        ).json()
        assert [item["id"] for item in queue_now["items"]] == [str(second)]
        refused = await decide(t.reviewer, t.pid, first, "include", stage="full_text")
        assert refused.status_code == 409
        summary = (await get(t.owner, f"/projects/{t.pid}/fulltext/summary")).json()
        assert summary == {
            "records": 2,
            "with_pdf": 0,
            "scanning": 0,
            "quarantined": 0,
            "missing": 1,
            "not_retrievable": 1,
            "scanner": True,
            "open_access": True,
        }

        # A PDF turning up after all clears the mark.
        added = (await upload(t.reviewer, t.pid, first, tiny_pdf())).json()
        await db.refresh(record)
        assert str(record.ft_final) == FullTextStatus.PENDING
        await scan(db_app, added["id"], queue)
        items = (
            await get(t.reviewer, f"/projects/{t.pid}/screening/queue?stage=full_text&n=10")
        ).json()["items"]
        by_id = {item["id"]: item for item in items}
        assert by_id[str(first)]["fulltext"]["scan_status"] == "clean"
        assert by_id[str(second)]["fulltext"] is None

        await post(t.reviewer, f"/projects/{t.pid}/records/{second}/fulltext/not-retrievable", {})
        undone = await delete(
            t.reviewer, f"/projects/{t.pid}/records/{second}/fulltext/not-retrievable"
        )
        assert undone.json()["not_retrievable"] is False
        await db.refresh(record)
        listed = (await get(t.owner, f"/projects/{t.pid}/fulltext/records")).json()
        assert {row["id"] for row in listed} == {str(first), str(second)}
        actions = set(await db.scalars(select(AuditLog.action)))
        assert {"fulltext.not_retrievable", "fulltext.retrievable", "fulltext.added"} <= actions


async def test_full_text_exclusions_need_a_reason_by_default(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue
) -> None:
    async with team(db_app, db, mailer) as t:
        await to_full_text(db, t.records[:1])
        refused = await decide(t.reviewer, t.pid, t.records[0], "exclude", stage="full_text")
        assert refused.status_code == 422
        assert refused.json()["code"] == "reason_required"


async def test_annotations_are_blinded_like_decisions(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue, scanner: list[bytes]
) -> None:
    async with team(db_app, db, mailer) as t:
        rid = t.records[0]
        added = (await upload(t.owner, t.pid, rid, tiny_pdf())).json()
        fid = added["id"]
        path = f"/projects/{t.pid}/fulltext/{fid}/annotations"
        body = {
            "page": 1,
            "rects": [[0.1, 0.2, 0.5, 0.03], [-1, 2, 0.5, 0.03]],
            "color": "green",
            "quote": "Night shifts",
            "comment": "Population matches",
        }
        created = await post(t.reviewer, path, body)
        assert created.status_code == 201, created.text
        note = created.json()
        assert note["mine"] is True
        assert note["rects"][1] == [0.0, 1.0, 0.5, 0.03]  # kept on the page
        await post(t.owner, path, {**body, "comment": "Owner's view"})

        # Blind mode is on by default: each sees only their own.
        await settings(t.owner, t.pid, blind_mode=True)
        reviewer_sees = (await get(t.reviewer, path)).json()
        assert [a["comment"] for a in reviewer_sees] == ["Population matches"]
        owner_sees = (await get(t.owner, path)).json()
        assert {a["comment"] for a in owner_sees} == {"Population matches", "Owner's view"}

        # Nobody edits or deletes someone else's.
        aid = note["id"]
        assert (await patch(t.owner, f"{path}/{aid}", {"comment": "mine now"})).status_code == 404
        assert (await delete(t.owner, f"{path}/{aid}")).status_code == 404
        edited = await patch(t.reviewer, f"{path}/{aid}", {"comment": None, "color": "pink"})
        assert edited.json()["comment"] is None
        assert edited.json()["color"] == "pink"
        assert (await delete(t.reviewer, f"{path}/{aid}")).status_code == 204
        assert (await get(t.reviewer, path)).json() == []

        invalid = await post(t.reviewer, path, {**body, "color": "red"})
        assert invalid.status_code == 422
        # The PDF of another review is not found through this one.
        other = f"/projects/{t.pid}/fulltext/{uuid.uuid4()}/annotations"
        assert (await get(t.reviewer, other)).status_code == 404


async def test_finding_and_fetching_a_free_copy(
    db_app: FastAPI,
    db: AsyncSession,
    mailer: MemoryMailer,
    queue: FakeQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = tiny_pdf("Open access")
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.host)
        if request.url.host == "api.unpaywall.org":
            return httpx.Response(
                200,
                json={
                    "oa_locations": [
                        {
                            "url_for_pdf": "https://repo.example.org/x.pdf",
                            "version": "acceptedVersion",
                        }
                    ]
                },
            )
        if request.url.host == "repo.example.org":
            return httpx.Response(200, content=pdf)
        return httpx.Response(404)

    async def public(host: str, port: int) -> None:
        return None

    monkeypatch.setattr(openaccess, "_require_public", public)
    db_app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    db_app.state.settings = db_app.state.settings.model_copy(
        update={"unpaywall_email": "screening@example.org"}
    )
    async with team(db_app, db, mailer) as t:
        rid, bare = t.records[0], t.records[1]
        await db.execute(update(Record).where(Record.id == rid).values(doi="10.1000/sleep.1"))
        await db.commit()
        base = f"/projects/{t.pid}/records"

        nothing = (await post(t.reviewer, f"{base}/{bare}/fulltext/find-oa")).json()
        assert nothing == {
            "candidates": [],
            "note": "This record has no DOI or PMCID to look it up by.",
        }
        found = (await post(t.reviewer, f"{base}/{rid}/fulltext/find-oa")).json()
        [candidate] = found["candidates"]
        assert candidate["host"] == "repo.example.org"
        assert "url" not in candidate  # the browser picks an id; the server knows the link

        # A candidate id the server did not offer is refused; so is someone else's find.
        made_up = await post(t.reviewer, f"{base}/{rid}/fulltext/fetch-oa", {"candidate": "x" * 12})
        assert made_up.status_code == 404
        theirs = await post(
            t.owner, f"{base}/{rid}/fulltext/fetch-oa", {"candidate": candidate["id"]}
        )
        assert theirs.status_code == 404

        fetched = await post(
            t.reviewer, f"{base}/{rid}/fulltext/fetch-oa", {"candidate": candidate["id"]}
        )
        assert fetched.status_code == 201, fetched.text
        assert fetched.json()["source"] == "open_access"
        assert fetched.json()["source_url"] == "https://repo.example.org/x.pdf"
        assert fetched.json()["filename"] == "10.1000_sleep.1.pdf"
        assert fetched.json()["scan_status"] == "pending"

        db_app.state.settings = db_app.state.settings.model_copy(
            update={"open_access_lookup": False}
        )
        off = (await post(t.reviewer, f"{base}/{rid}/fulltext/find-oa")).json()
        assert off["candidates"] == []
        assert "off" in off["note"]


async def test_a_zip_bomb_is_rejected(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue
) -> None:
    """Guide 17 Phase 7 acceptance: a ZIP bomb is rejected, before anything is unpacked."""
    async with team(db_app, db, mailer) as t:
        before = zips_on_disk(db_app)
        bomb = zip_bomb(64)
        assert len(bomb) < 200_000
        refused = await upload_zip(t.owner, t.pid, bomb)
        assert refused.status_code == 422
        assert refused.json()["code"] == "zip_rejected"
        assert "ZIP bomb" in refused.json()["detail"]
        assert await db.scalar(select(FulltextBatch.id)) is None
        assert queue.jobs == []
        audit = await db.scalar(select(AuditLog).where(AuditLog.action == "fulltext.zip_rejected"))
        assert audit is not None
        assert "ZIP bomb" in (audit.after or {})["reason"]
        assert zips_on_disk(db_app) == before

        escaping = make_zip({"../../etc/cron.d/x.pdf": tiny_pdf()})
        assert (await upload_zip(t.owner, t.pid, escaping)).status_code == 422
        assert (await upload_zip(t.owner, t.pid, b"not a zip")).status_code == 422
        # A reviewer does not upload ZIPs.
        assert (
            await upload_zip(t.reviewer, t.pid, make_zip({"a.pdf": tiny_pdf()}))
        ).status_code == 403


async def test_a_zip_of_pdfs_is_matched_confirmed_and_scanned(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue, scanner: list[bytes]
) -> None:
    async with team(db_app, db, mailer, records=4) as t:
        a, b, c, d = t.records
        await db.execute(update(Record).where(Record.id == a).values(doi="10.1111/jan.13894"))
        await db.execute(
            update(Record).where(Record.id == b).values(authors=["Okafor, Ngozi"], year=2016)
        )
        await db.commit()
        await to_full_text(db, [a, b, c])
        data = make_zip(
            {
                "papers/10.1111_jan.13894.pdf": tiny_pdf("by doi"),
                "papers/Okafor 2016 night shifts.pdf": tiny_pdf("by author"),
                "papers/scan0001.pdf": tiny_pdf("unknown"),
                "papers/fake.pdf": b"MZ not a pdf at all",
                "papers/readme.txt": b"hi",
                "__MACOSX/papers/._scan0001.pdf": b"\0",
            }
        )
        started = await upload_zip(t.owner, t.pid, data)
        assert started.status_code == 201, started.text
        batch = started.json()
        assert batch["status"] == "checking"
        assert [name for name, *_ in queue.jobs] == ["match_fulltext_batch"]

        kept = await run_batch(
            sessionmaker=db_app.state.sessionmaker,
            redis=db_app.state.redis,
            storage=db_app.state.storage,
            settings=db_app.state.settings,
            batch_id=uuid.UUID(batch["id"]),
        )
        assert kept == 3
        ready = (await get(t.owner, f"/projects/{t.pid}/fulltext/bulk/{batch['id']}")).json()
        assert ready["status"] == "ready"
        entries = {entry["name"]: entry for entry in ready["entries"]}
        assert entries["10.1111_jan.13894.pdf"]["match"]["record_id"] == str(a)
        assert entries["10.1111_jan.13894.pdf"]["match"]["by"] == "doi"
        assert entries["10.1111_jan.13894.pdf"]["match"]["confidence"] == "sure"
        assert entries["Okafor 2016 night shifts.pdf"]["match"]["record_id"] == str(b)
        assert entries["Okafor 2016 night shifts.pdf"]["match"]["confidence"] == "likely"
        assert entries["scan0001.pdf"]["match"] is None
        assert entries["fake.pdf"]["skip"] == "not_pdf"
        assert entries["readme.txt"]["skip"] == "not_pdf"
        assert entries["._scan0001.pdf"]["skip"] == "system"
        assert "key" not in entries["scan0001.pdf"]  # storage keys never leave the server

        # Two to their matches, the unknown one to c, and one pointing at another review's
        # record, which is ignored.
        held = await db.scalar(
            select(FulltextBatch).where(FulltextBatch.id == uuid.UUID(batch["id"]))
        )
        assert held is not None
        await db.refresh(held)
        unchosen = next(e["key"] for e in held.entries if e["name"] == "scan0001.pdf")
        assert stored(db_app, unchosen)
        choices = {
            str(entries["10.1111_jan.13894.pdf"]["index"]): str(a),
            str(entries["Okafor 2016 night shifts.pdf"]["index"]): str(b),
            str(entries["scan0001.pdf"]["index"]): str(uuid.uuid4()),
        }
        confirmed = await post(
            t.owner, f"/projects/{t.pid}/fulltext/bulk/{batch['id']}/confirm", {"choices": choices}
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json() == {"attached": 2, "skipped": 1}
        scans = [args[0] for name, args, _ in queue.jobs if name == "scan_fulltext"]
        assert len(scans) == 2
        for fid in scans:
            await scan(db_app, fid, queue)
        served = await open_pdf(t.reviewer, t.pid, a)
        assert served.content == tiny_pdf("by doi")
        assert (await get(t.owner, f"/projects/{t.pid}/fulltext/summary")).json()["with_pdf"] == 2

        again = await post(
            t.owner, f"/projects/{t.pid}/fulltext/bulk/{batch['id']}/confirm", {"choices": {}}
        )
        assert again.status_code == 409
        assert not stored(db_app, unchosen)
        assert d not in {row.record_id for row in await db.scalars(select(Fulltext))}


async def test_an_unconfirmed_zip_can_be_discarded_or_is_tidied_away(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue
) -> None:
    async with team(db_app, db, mailer) as t:
        before = zips_on_disk(db_app)
        ids = []
        for _ in range(2):
            batch = (await upload_zip(t.owner, t.pid, make_zip({"x.pdf": tiny_pdf()}))).json()
            await run_batch(
                sessionmaker=db_app.state.sessionmaker,
                redis=db_app.state.redis,
                storage=db_app.state.storage,
                settings=db_app.state.settings,
                batch_id=uuid.UUID(batch["id"]),
            )
            ids.append(batch["id"])
        assert (
            await delete(t.owner, f"/projects/{t.pid}/fulltext/bulk/{ids[0]}")
        ).status_code == 204
        gone = (await get(t.owner, f"/projects/{t.pid}/fulltext/bulk/{ids[0]}")).json()
        assert gone["status"] == "failed"

        await db.execute(
            update(FulltextBatch)
            .where(FulltextBatch.id == uuid.UUID(ids[1]))
            .values(updated_at=FulltextBatch.updated_at - timedelta(days=2))
        )
        await db.commit()
        tidied = await discard_stale_batches(
            sessionmaker=db_app.state.sessionmaker, storage=db_app.state.storage
        )
        assert tidied == 1
        batches = list(await db.scalars(select(FulltextBatch)))
        for held in batches:
            await db.refresh(held)
        assert {entry.get("key") for held in batches for entry in held.entries} == {None}
        assert zips_on_disk(db_app) == before


async def test_viewers_read_but_do_not_change(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue, scanner: list[bytes]
) -> None:
    async with (
        team(db_app, db, mailer) as t,
        person(db_app, mailer, VIEWER, ip="10.9.0.7") as viewer,
    ):
        await add_member(t.owner, viewer, t.pid, VIEWER, role="viewer")
        rid = t.records[0]
        added = (await upload(t.owner, t.pid, rid, tiny_pdf())).json()
        await scan(db_app, added["id"], queue)
        assert (await open_pdf(viewer, t.pid, rid)).status_code == 200
        path = f"/projects/{t.pid}/fulltext/{added['id']}/annotations"
        assert (await get(viewer, path)).status_code == 200
        body = {"page": 1, "rects": [[0, 0, 1, 1]]}
        assert (await api(viewer, "POST", path, body)).status_code == 403


async def merge(db: AsyncSession, pid: str, kept: uuid.UUID, copies: list[uuid.UUID]) -> None:
    from app.models import DupCluster, DupClusterMember
    from app.services.dedup import merge_cluster

    cluster = DupCluster(project_id=uuid.UUID(pid), score=0.95)
    db.add(cluster)
    await db.flush()
    db.add_all(
        [DupClusterMember(cluster_id=cluster.id, record_id=kept, is_primary=True)]
        + [DupClusterMember(cluster_id=cluster.id, record_id=copy) for copy in copies]
    )
    await db.flush()
    await merge_cluster(db, cluster, kept, resolved_by=None)
    await db.commit()


async def test_a_pdf_follows_its_record_when_duplicates_are_merged(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue, scanner: list[bytes]
) -> None:
    """Merging moves decisions, labels and notes to the record kept (guide 8.4); the PDF
    and its highlights come too, unless the kept record has its own."""
    async with team(db_app, db, mailer, records=4) as t:
        kept, copy, other_kept, other_copy = t.records
        await to_full_text(db, t.records)
        pdf = (await upload(t.reviewer, t.pid, copy, tiny_pdf("the copy's"))).json()
        await scan(db_app, pdf["id"], queue)
        note = {"page": 1, "rects": [[0.1, 0.1, 0.5, 0.02]], "comment": "Primary outcome"}
        await post(t.reviewer, f"/projects/{t.pid}/fulltext/{pdf['id']}/annotations", note)
        await merge(db, t.pid, kept, [copy])

        moved = (await get(t.reviewer, f"/projects/{t.pid}/records/{kept}/fulltext")).json()
        assert moved["fulltext"]["id"] == pdf["id"]
        path = f"/projects/{t.pid}/fulltext/{pdf['id']}/annotations"
        assert [a["comment"] for a in (await get(t.reviewer, path)).json()] == ["Primary outcome"]
        assert (await open_pdf(t.reviewer, t.pid, kept)).content == tiny_pdf("the copy's")

        # The kept record's own PDF stands; a "not retrievable" mark on it gives way to
        # a PDF from the copy.
        own = (await upload(t.reviewer, t.pid, other_kept, tiny_pdf("its own"))).json()
        theirs = (await upload(t.reviewer, t.pid, other_copy, tiny_pdf("the copy's"))).json()
        await merge(db, t.pid, other_kept, [other_copy])
        state = (await get(t.owner, f"/projects/{t.pid}/records/{other_kept}/fulltext")).json()
        assert state["fulltext"]["id"] == own["id"]
        left = await db.get(Fulltext, uuid.UUID(theirs["id"]))
        assert left is not None
        await db.refresh(left)
        assert left.record_id == other_copy


async def test_a_mark_and_a_pdf_meet_in_a_merge(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue, scanner: list[bytes]
) -> None:
    async with team(db_app, db, mailer, records=4) as t:
        kept, copy, bare, marked = t.records
        # Through decisions, as records really reach full text: a merge recomputes both
        # stages from them.
        await settings(t.owner, t.pid, reviewers_per_record_ta=1)
        for record_id in t.records:
            assert (await decide(t.reviewer, t.pid, record_id, "include")).status_code == 200
        await post(t.reviewer, f"/projects/{t.pid}/records/{kept}/fulltext/not-retrievable", {})
        pdf = (await upload(t.reviewer, t.pid, copy, tiny_pdf())).json()
        await merge(db, t.pid, kept, [copy])
        state = (await get(t.owner, f"/projects/{t.pid}/records/{kept}/fulltext")).json()
        assert state["fulltext"]["id"] == pdf["id"]
        assert state["not_retrievable"] is False

        await post(t.reviewer, f"/projects/{t.pid}/records/{marked}/fulltext/not-retrievable", {})
        await merge(db, t.pid, bare, [marked])
        state = (await get(t.owner, f"/projects/{t.pid}/records/{bare}/fulltext")).json()
        assert state == {"fulltext": None, "not_retrievable": True, "not_retrievable_note": None}
        record = await db.get(Record, bare)
        assert record is not None
        await db.refresh(record)
        assert str(record.ft_final) == FullTextStatus.NOT_RETRIEVABLE


async def test_a_zip_entry_for_a_record_merged_since_goes_to_the_record_kept(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, queue: FakeQueue, scanner: list[bytes]
) -> None:
    """Deduplication can finish between matching a ZIP and confirming it."""
    async with team(db_app, db, mailer, records=2) as t:
        kept, copy = t.records
        await db.execute(update(Record).where(Record.id == copy).values(doi="10.1000/copy"))
        await db.commit()
        await to_full_text(db, t.records)
        batch = (
            await upload_zip(t.owner, t.pid, make_zip({"10.1000_copy.pdf": tiny_pdf()}))
        ).json()
        await run_batch(
            sessionmaker=db_app.state.sessionmaker,
            redis=db_app.state.redis,
            storage=db_app.state.storage,
            settings=db_app.state.settings,
            batch_id=uuid.UUID(batch["id"]),
        )
        ready = (await get(t.owner, f"/projects/{t.pid}/fulltext/bulk/{batch['id']}")).json()
        assert ready["entries"][0]["match"]["record_id"] == str(copy)
        await merge(db, t.pid, kept, [copy])

        confirmed = await post(
            t.owner,
            f"/projects/{t.pid}/fulltext/bulk/{batch['id']}/confirm",
            {"choices": {"0": str(copy)}},
        )
        assert confirmed.json() == {"attached": 1, "skipped": 0}
        state = (await get(t.owner, f"/projects/{t.pid}/records/{kept}/fulltext")).json()
        assert state["fulltext"]["source"] == "zip"

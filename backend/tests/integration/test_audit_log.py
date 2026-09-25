"""The audit log viewer (guide 12.8, 8.16): owners and admins, filtered, paged, blinded
where it records others' decisions, and exported as formula-safe CSV."""

import csv
import io
import uuid

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog
from tests.conftest import MemoryMailer
from tests.project_helpers import get
from tests.screening_helpers import decide, settings, team


async def test_owners_read_the_log_newest_first_with_filters_and_pages(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=3) as t:
        for record_id in t.records:
            await decide(t.reviewer, t.pid, record_id, "include")
        log = (await get(t.owner, f"/projects/{t.pid}/audit")).json()
        ids = [entry["id"] for entry in log["items"]]
        assert ids == sorted(ids, reverse=True)
        assert log["items"][0]["action"] == "decision.made"

        decisions = (await get(t.owner, f"/projects/{t.pid}/audit?action=decision&limit=2")).json()
        assert [entry["action"] for entry in decisions["items"]] == ["decision.made"] * 2
        assert decisions["next_cursor"]
        rest = (
            await get(
                t.owner,
                f"/projects/{t.pid}/audit?action=decision&limit=2&cursor={decisions['next_cursor']}",
            )
        ).json()
        assert len(rest["items"]) == 1
        assert rest["next_cursor"] is None
        # The owner is unblinded here, so the decision itself is there.
        assert rest["items"][0]["after"]["decision"] == "include"
        assert rest["items"][0]["actor"] == "Ada Lovelace"

        exact = (await get(t.owner, f"/projects/{t.pid}/audit?action=project.created")).json()
        assert [entry["action"] for entry in exact["items"]] == ["project.created"]
        assert (await get(t.owner, f"/projects/{t.pid}/audit?cursor=nonsense")).status_code == 400
        assert (await get(t.reviewer, f"/projects/{t.pid}/audit")).status_code == 403


async def test_a_blind_owner_does_not_learn_others_decisions_from_the_log(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=1, unblind_owner=False) as t:
        await settings(t.owner, t.pid, blind_mode=True)
        await decide(t.reviewer, t.pid, t.records[0], "exclude")
        await decide(t.owner, t.pid, t.records[0], "include")
        entries = (await get(t.owner, f"/projects/{t.pid}/audit?action=decision")).json()["items"]
        mine, theirs = entries
        assert mine["after"]["decision"] == "include"
        assert mine["withheld"] is False
        assert theirs["after"] is None
        assert theirs["withheld"] is True
        text = (await t.owner.get(f"/api/v1/projects/{t.pid}/audit.csv")).text
        assert "exclude" not in text


async def test_the_log_downloads_as_formula_safe_csv(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=1) as t:
        db.add(
            AuditLog(
                project_id=uuid.UUID(t.pid),
                action="project.renamed",
                user_agent='=HYPERLINK("http://evil")',
                after={"title": "Night shifts"},
            )
        )
        await db.commit()
        response = await t.owner.get(f"/api/v1/projects/{t.pid}/audit.csv")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert response.headers["content-disposition"] == 'attachment; filename="audit-log.csv"'
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert rows[0]["action"] == "project.renamed"
        assert rows[0]["user_agent"] == '\'=HYPERLINK("http://evil")'
        assert {row["action"] for row in rows} >= {"project.created", "project.renamed"}
        only = (
            await t.owner.get(f"/api/v1/projects/{t.pid}/audit.csv?action=project.renamed")
        ).text
        assert len(list(csv.DictReader(io.StringIO(only)))) == 1

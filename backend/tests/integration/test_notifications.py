"""In-app notifications and the daily digest (guide 8.17)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, NotificationKind, User
from app.services.notifications import notify
from app.workers.digests import send_digests
from tests.conftest import MemoryMailer
from tests.integration.test_fulltext import FakeQueue
from tests.integration.test_imports import run, upload
from tests.project_helpers import OWNER, REVIEWER, api, create_project, get, person, post
from tests.screening_helpers import THIRD, decide, settings, team


async def names(db: AsyncSession) -> None:
    """Every test account is called Ada Lovelace; mentions need them told apart."""
    for email, name in (
        (OWNER, "Ada Lovelace"),
        (REVIEWER, "Grace Hopper"),
        (THIRD, "Hedy Lamarr"),
    ):
        await db.execute(update(User).where(User.email == email).values(name=name))
    await db.commit()


async def mine(client: Any, kind: str | None = None) -> list[dict[str, Any]]:
    """My notices, of one kind if given (`team` invites people, so they hold invites)."""
    page = await get(client, "/notifications")
    assert page.status_code == 200, page.text
    items: list[dict[str, Any]] = page.json()["items"]
    return [item for item in items if kind is None or item["kind"] == kind]


async def test_new_conflicts_tell_those_who_resolve_them_counted(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=3, third=True) as t:
        assert t.third is not None
        await settings(t.owner, t.pid, reviewers_per_record_ta=2)
        for record in t.records[:2]:
            await decide(t.reviewer, t.pid, record, "include")
            await decide(t.third, t.pid, record, "exclude")
        # The owner resolves conflicts: one notice, counting both.
        [notice] = await mine(t.owner)
        assert (notice["kind"], notice["count"], notice["read"]) == ("conflicts", 2, False)
        assert notice["data"]["project_title"] == "Sleep and shift work"
        assert (await get(t.owner, "/notifications/unread")).json() == {"unread": 1}
        # Reviewers who cannot resolve are not told.
        assert await mine(t.reviewer, "conflicts") == []
        assert await mine(t.third, "conflicts") == []
        # An agreement makes no conflict; a changed decision that makes one does.
        await decide(t.reviewer, t.pid, t.records[2], "include")
        await decide(t.third, t.pid, t.records[2], "include")
        assert (await mine(t.owner))[0]["count"] == 2
        await decide(t.third, t.pid, t.records[2], "exclude")
        assert (await mine(t.owner))[0]["count"] == 3

        # Read, a new conflict starts a new notice.
        assert (await post(t.owner, f"/notifications/{notice['id']}/read")).status_code == 204
        await decide(t.reviewer, t.pid, t.records[0], "exclude")
        await decide(t.reviewer, t.pid, t.records[0], "include")
        notices = await mine(t.owner)
        assert [(n["count"], n["read"]) for n in notices] == [(1, False), (3, True)]
        assert (await post(t.owner, "/notifications/read-all")).status_code == 204
        assert (await get(t.owner, "/notifications/unread")).json() == {"unread": 0}
        # Nobody can read another person's notice.
        assert (await post(t.reviewer, f"/notifications/{notice['id']}/read")).status_code == 404


async def test_conflict_counts_keep_working_after_postgres_plans_generically(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """PostgreSQL plans a prepared statement for its values five times, then generically. The
    count-up insert must still find its partial index then: at the load test, every new
    conflict after the fifth on a connection failed with a 500."""
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        me = await db.scalar(select(User.id).where(User.email == OWNER))
        assert me is not None
        for _ in range(8):
            await notify(
                db, [me], NotificationKind.CONFLICTS, project_id=uuid.UUID(project["id"])
            )
        await db.commit()
        counts = list(await db.scalars(select(Notification.count).where(Notification.user_id == me)))
        assert counts == [8]


async def test_the_person_who_made_the_conflict_is_not_told(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=1) as t:
        await settings(t.owner, t.pid, reviewers_per_record_ta=2)
        await decide(t.reviewer, t.pid, t.records[0], "include")
        await decide(t.owner, t.pid, t.records[0], "exclude")
        assert await mine(t.owner) == []


async def test_a_mention_in_a_team_note_tells_that_member(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=1, third=True) as t:
        assert t.third is not None
        await names(db)
        record = t.records[0]
        base = f"/projects/{t.pid}/records/{record}/notes"
        added = await post(
            t.reviewer,
            base,
            {"body": "@hedy lamarr could you check the dose?", "visibility": "team"},
        )
        assert added.status_code == 201, added.text
        [notice] = await mine(t.third, "mention")
        assert notice["kind"] == "mention"
        assert notice["data"]["by"] == "Grace Hopper"
        assert notice["data"]["excerpt"] == "@hedy lamarr could you check the dose?"
        assert notice["data"]["record_id"] == str(record)
        assert await mine(t.owner, "mention") == []
        # A private note tells nobody, whoever it names.
        await post(
            t.reviewer, base, {"body": "@Ada Lovelace note to self", "visibility": "private"}
        )
        assert await mine(t.owner) == []


async def test_an_invitation_tells_someone_with_an_account(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=0) as t:
        invited = await post(
            t.owner, f"/projects/{t.pid}/invites", {"email": THIRD, "role": "reviewer"}
        )
        assert invited.status_code == 201, invited.text
        async with person(db_app, mailer, "linus@example.org", ip="10.9.1.1") as stranger:
            assert await mine(stranger) == []
        # Hedy has an account (made by `team`) and is not yet a member: told without the
        # review's id, since she cannot open it until she accepts.
        hedy = await db.scalar(select(User.id).where(User.email == THIRD))
        rows = list(await db.scalars(select(Notification).where(Notification.user_id == hedy)))
        assert [(row.kind, row.project_id, row.data["by"]) for row in rows] == [
            ("invite", None, "Ada Lovelace")
        ]


async def test_the_importer_hears_when_an_import_finishes(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=0) as t:
        batch = await upload(t.owner, t.pid, "pubmed.nbib")
        confirmed = await post(t.owner, f"/projects/{t.pid}/imports/{batch['id']}/confirm", {})
        assert confirmed.status_code in (200, 202), confirmed.text
        await run(db_app, batch["id"])
        [notice] = await mine(t.owner)
        assert notice["kind"] == "import_finished"
        assert notice["data"]["filename"] == "pubmed.nbib"
        assert notice["data"]["imported"] > 0
        assert notice["project_id"] == t.pid


async def test_notices_page_and_leave_with_the_review(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=0) as t:
        owner = await db.scalar(select(User.id).where(User.email == OWNER))
        assert owner is not None
        pid = uuid.UUID(t.pid)
        now = datetime.now(UTC)
        db.add_all(
            Notification(
                user_id=owner,
                project_id=pid if index % 2 else None,
                kind="mention",
                data={"by": "Grace Hopper", "excerpt": str(index)},
                created_at=now - timedelta(minutes=index),
                updated_at=now - timedelta(minutes=index),
            )
            for index in range(25)
        )
        await db.commit()
        first = (await get(t.owner, "/notifications?limit=20")).json()
        assert [n["data"]["excerpt"] for n in first["items"]][:3] == ["0", "1", "2"]
        assert first["unread"] == 25
        second = (
            await get(t.owner, f"/notifications?limit=20&cursor={first['next_cursor']}")
        ).json()
        assert len(second["items"]) == 5
        assert second["next_cursor"] is None
        assert (await get(t.owner, "/notifications?cursor=nonsense")).status_code == 400

        # Someone no longer in a review no longer sees its notices.
        grace = await db.scalar(select(User.id).where(User.email == REVIEWER))
        assert grace is not None
        db.add(Notification(user_id=grace, project_id=pid, kind="conflicts", data={}))
        await db.commit()
        assert len(await mine(t.reviewer, "conflicts")) == 1
        left = await api(t.reviewer, "DELETE", f"/projects/{t.pid}/membership")
        assert left.status_code == 204, left.text
        assert await mine(t.reviewer, "conflicts") == []
        # An invitation is about no review, so it stays.
        assert len(await mine(t.reviewer, "invite")) == 1


async def test_the_daily_digest_is_off_until_asked_for(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=2, third=True) as t:
        assert t.third is not None
        await settings(t.owner, t.pid, reviewers_per_record_ta=2)
        await decide(t.reviewer, t.pid, t.records[0], "include")
        await decide(t.third, t.pid, t.records[0], "exclude")
        queue = FakeQueue()

        async def run_digest(at: datetime) -> int:
            return await send_digests(
                sessionmaker=db_app.state.sessionmaker,
                queue=queue,  # type: ignore[arg-type]
                settings=db_app.state.settings,
                now=at,
            )

        assert await run_digest(datetime.now(UTC)) == 0  # nobody asked

        assert (await get(t.owner, "/notifications/settings")).json() == {"email_digest": False}
        turned = await api(t.owner, "PUT", "/notifications/settings", {"email_digest": True})
        assert turned.json() == {"email_digest": True}
        assert await run_digest(datetime.now(UTC)) == 1
        [(job, (to, subject, body), _)] = queue.jobs
        assert job == "send_email"
        assert to == OWNER
        assert subject == "Winnow: 1 unread notification"
        assert "- 1 new conflict to resolve in Sleep and shift work." in body
        assert "/account" in body
        # Once a day, not every run.
        assert await run_digest(datetime.now(UTC) + timedelta(hours=2)) == 0
        assert await run_digest(datetime.now(UTC) + timedelta(hours=25)) == 0  # nothing new

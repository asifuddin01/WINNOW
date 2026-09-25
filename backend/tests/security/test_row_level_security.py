"""Row-level security (guide 12.2, Phase 8): the database, not only the services, keeps
one review's records, decisions and notes from another review's members."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import _REQUEST, bind_user
from app.models import AuditLog, Decision, Note, Record, User
from tests.conftest import MemoryMailer
from tests.project_helpers import OWNER, REVIEWER, create_project, person, post
from tests.screening_helpers import add_records, decide, settings


@asynccontextmanager
async def request_session(db_app: FastAPI) -> AsyncIterator[AsyncSession]:
    """A session as a request gets it (`app.db.get_session`)."""
    async with db_app.state.sessionmaker() as session:
        session.info[_REQUEST] = True
        yield session


async def user_id(db: AsyncSession, email: str) -> uuid.UUID:
    found = await db.scalar(select(User.id).where(User.email == email))
    assert found is not None
    return found


async def test_a_query_that_forgets_the_review_still_sees_only_the_users_reviews(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.7.0.1") as ada,
        person(db_app, mailer, REVIEWER, ip="10.7.0.2") as grace,
    ):
        mine = (await create_project(ada, "Ada's review"))["id"]
        theirs = (await create_project(grace, "Grace's review"))["id"]
        await settings(ada, mine, reviewers_per_record_ta=1)
        [ada_record] = await add_records(db, mine, 1)
        [grace_record] = await add_records(db, theirs, 1)
        assert (await decide(ada, mine, ada_record, "include")).status_code == 200
        await post(ada, f"/projects/{mine}/records/{ada_record}/notes", {"body": "Mine."})
        ada_id = await user_id(db, OWNER)

        async with request_session(db_app) as session:
            # Not yet bound to a user: nothing at all.
            assert await session.scalar(select(func.count()).select_from(Record)) == 0
            await bind_user(session, ada_id)
            # Every record, decision and note in the database, asked for without a filter.
            seen = set(await session.scalars(select(Record.project_id)))
            assert seen == {uuid.UUID(mine)}
            assert await session.get(Record, grace_record) is None
            assert {d.project_id for d in await session.scalars(select(Decision))} == {
                uuid.UUID(mine)
            }
            assert {n.project_id for n in await session.scalars(select(Note))} == {uuid.UUID(mine)}
            # Writing into another review is refused too, not silently done.
            changed = await session.execute(
                update(Record).where(Record.id == grace_record).values(title="Taken over")
            )
            assert changed.rowcount == 0  # type: ignore[attr-defined]

        # The owner the workers use still sees everything.
        assert await db.get(Record, grace_record) is not None


async def test_rows_cannot_be_moved_into_a_review_the_user_is_not_in(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.7.0.3") as ada,
        person(db_app, mailer, REVIEWER, ip="10.7.0.4") as grace,
    ):
        mine = (await create_project(ada, "Ada's review"))["id"]
        theirs = (await create_project(grace, "Grace's review"))["id"]
        [record] = await add_records(db, mine, 1)
        ada_id = await user_id(db, OWNER)
        async with request_session(db_app) as session:
            await bind_user(session, ada_id)
            with pytest.raises(DBAPIError, match="row-level security"):
                await session.execute(
                    update(Record).where(Record.id == record).values(project_id=uuid.UUID(theirs))
                )
            await session.rollback()


async def test_requests_cannot_change_or_delete_the_audit_trail(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER, ip="10.7.0.5"):
        ada_id = await user_id(db, OWNER)
        row = await db.scalar(select(AuditLog.id).limit(1))
        assert row is not None
        async with request_session(db_app) as session:
            await bind_user(session, ada_id)
            with pytest.raises(DBAPIError, match="permission denied"):
                await session.execute(
                    update(AuditLog).where(AuditLog.id == row).values(action="tampered")
                )
            await session.rollback()


async def test_row_security_is_switched_on_for_the_tables_it_guards(db: AsyncSession) -> None:
    from sqlalchemy import Boolean, column, table

    pg_class = table("pg_class", column("relname"), column("relrowsecurity", Boolean))
    guarded = set(
        await db.scalars(select(pg_class.c.relname).where(pg_class.c.relrowsecurity.is_(True)))
    )
    assert {"records", "decisions", "notes"} <= guarded

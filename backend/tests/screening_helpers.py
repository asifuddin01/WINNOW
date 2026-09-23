"""Setting up a review with records and a team, for the screening tests."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Record
from app.models.base import uuid7
from tests.conftest import MemoryMailer
from tests.project_helpers import OWNER, REVIEWER, add_member, api, create_project, get, person

THIRD = "hedy@example.org"


@dataclass
class Team:
    pid: str
    owner: AsyncClient
    reviewer: AsyncClient
    third: AsyncClient | None
    records: list[uuid.UUID]


async def add_records(db: AsyncSession, pid: str, count: int, **fields: Any) -> list[uuid.UUID]:
    now = datetime.now(UTC)
    ids = [uuid7() for _ in range(count)]
    db.add_all(
        Record(
            id=record_id,
            project_id=uuid.UUID(pid),
            title=fields.get("title", f"Night shifts and sleep, study {index}"),
            title_norm=f"night shifts and sleep study {index}",
            abstract=fields.get("abstract", "AIM: to examine sleep in nurses on night shifts."),
            authors=["Smith, Jane"],
            year=2015 + index % 10,
            journal="Sleep Medicine",
            publication_type=fields.get("publication_type", ["Journal Article"]),
            created_at=now,
            updated_at=now,
        )
        for index, record_id in enumerate(ids)
    )
    await db.commit()
    return ids


async def settings(client: AsyncClient, pid: str, **values: Any) -> None:
    response = await api(client, "PATCH", f"/projects/{pid}", {"settings": values})
    assert response.status_code == 200, response.text


async def decide(
    client: AsyncClient, pid: str, record_id: uuid.UUID, decision: str, **extra: Any
) -> Response:
    return await api(
        client,
        "PUT",
        f"/projects/{pid}/records/{record_id}/decision",
        {"decision": decision, **extra},
    )


async def status_of(owner: AsyncClient, pid: str, record_id: uuid.UUID) -> str:
    """The final status, as someone allowed to see it reads it."""
    detail = await get(owner, f"/projects/{pid}/records/{record_id}")
    status: str = detail.json()["ta_final"]
    return status


@asynccontextmanager
async def team(
    app: FastAPI,
    db: AsyncSession,
    mailer: MemoryMailer,
    *,
    records: int = 4,
    third: bool = False,
    unblind_owner: bool = True,
) -> AsyncIterator[Team]:
    """An owner (who can see everyone's decisions unless told otherwise), a reviewer, and
    optionally a second reviewer, with some records to screen."""
    async with (
        person(app, mailer, OWNER, ip="10.9.0.1") as owner,
        person(app, mailer, REVIEWER, ip="10.9.0.2") as reviewer,
        person(app, mailer, THIRD, ip="10.9.0.3") as hedy,
    ):
        project = await create_project(owner)
        pid = project["id"]
        await add_member(owner, reviewer, pid, REVIEWER)
        if third:
            await add_member(owner, hedy, pid, THIRD)
        if unblind_owner:
            response = await api(
                owner, "PATCH", f"/projects/{pid}/membership", {"keep_blind": False}
            )
            assert response.status_code == 200, response.text
        ids = await add_records(db, pid, records)
        yield Team(
            pid=pid, owner=owner, reviewer=reviewer, third=hedy if third else None, records=ids
        )

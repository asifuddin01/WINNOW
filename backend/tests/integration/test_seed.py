"""`make seed`: a demo review to look around in (guide 16.2)."""

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli import DEMO_CRITERIA, add_demo_review
from app.models import User
from app.services.projects import DEFAULT_EXCLUSION_REASONS
from tests.conftest import MemoryMailer
from tests.project_helpers import OWNER, get, person


async def test_the_demo_review_is_ready_to_look_around(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        user = await db.scalar(select(User).where(User.email == OWNER))
        assert user is not None
        project = await add_demo_review(db, db_app.state.settings, user)

        criteria = (await get(owner, f"/projects/{project.id}/criteria")).json()
        assert len(criteria) == len(DEMO_CRITERIA)
        groups = (await get(owner, f"/projects/{project.id}/keyword-groups")).json()
        assert [group["name"] for group in groups] == ["Population", "Outcome"]
        assert sum(len(group["keywords"]) for group in groups) == 6
        assert len((await get(owner, f"/projects/{project.id}/labels")).json()) == 1
        reasons = (await get(owner, f"/projects/{project.id}/exclusion-reasons")).json()
        assert len(reasons) == len(DEFAULT_EXCLUSION_REASONS)

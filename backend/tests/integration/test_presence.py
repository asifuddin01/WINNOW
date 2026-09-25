"""Who is screening right now (guide 8.17): names and stages, never records."""

import json
import time
import uuid

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import MemoryMailer
from tests.project_helpers import api, get
from tests.screening_helpers import team


async def test_screeners_are_seen_by_the_team_for_a_minute(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=0, third=True) as t:
        assert t.third is not None
        path = f"/projects/{t.pid}/presence"
        assert (await api(t.reviewer, "PUT", path, {"stage": "title_abstract"})).status_code == 204
        assert (await api(t.third, "PUT", path, {"stage": "full_text"})).status_code == 204

        seen = (await get(t.owner, path)).json()
        assert {p["stage"] for p in seen} == {"title_abstract", "full_text"}
        assert set(seen[0]) == {"user_id", "name", "stage"}  # nothing about records
        # Nobody is shown to themselves.
        assert len((await get(t.reviewer, path)).json()) == 1

        # Someone who stops is gone at once; someone silent for a minute, soon after.
        assert (await api(t.third, "DELETE", path)).status_code == 204
        assert len((await get(t.owner, path)).json()) == 1
        redis = db_app.state.redis
        key = f"presence:{t.pid}"
        [(user_id, raw)] = (await redis.hgetall(key)).items()
        entry = json.loads(raw)
        entry["at"] = time.time() - 61
        await redis.hset(key, user_id, json.dumps(entry))
        await redis.hset(key, str(uuid.uuid4()), "not json")
        assert (await get(t.owner, path)).json() == []
        assert await redis.hlen(key) == 0  # stale entries are cleared as they are read


async def test_a_stage_winnow_does_not_know_is_refused(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=0) as t:
        path = f"/projects/{t.pid}/presence"
        refused = await api(t.owner, "PUT", path, {"stage": "sideways"})
        assert refused.status_code == 422
